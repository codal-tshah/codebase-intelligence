"""Python source analysis built on the standard-library `ast`.

The parser is framework-neutral: it extracts symbols, imports (with relative
imports resolved to absolute module names), call sites, decorators, and class
attributes. Framework adapters interpret that structure.
"""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from ci_parsers.files import (  # re-exported for backwards compatibility
    clone_git_repo,
    git_head_sha,
    list_python_files,
)

__all__ = [
    "CallEdge",
    "Decorator",
    "ImportInfo",
    "ParseResult",
    "SymbolInfo",
    "clone_git_repo",
    "dotted_name",
    "git_head_sha",
    "list_python_files",
    "module_name_from_path",
    "parse_python_file",
    "parse_python_source",
    "stable_node_id",
    "structural_fingerprint",
]


@dataclass
class Decorator:
    name: str
    args: list[str] = field(default_factory=list)
    kwargs: dict[str, str] = field(default_factory=dict)
    strings: list[str] = field(default_factory=list)


@dataclass
class SymbolInfo:
    name: str
    kind: str  # class | function | method
    qualified_name: str
    start_line: int
    end_line: int
    parent_class: str | None = None  # qualified name of enclosing class for methods
    bases: list[str] = field(default_factory=list)
    decorators: list[Decorator] = field(default_factory=list)
    docstring: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)  # class body `x = Name` assignments
    meta_attrs: dict[str, str] = field(default_factory=dict)  # `class Meta:` assignments
    meta_flags: dict[str, bool] = field(default_factory=dict)  # `class Meta: abstract = True`
    node: ast.AST | None = field(default=None, repr=False)


@dataclass
class ImportInfo:
    module: str  # absolute module (relative imports resolved)
    names: list[str] = field(default_factory=list)  # imported names ("*" allowed)
    aliases: dict[str, str] = field(default_factory=dict)  # local name -> imported name
    line: int = 1
    level: int = 0
    type_only: bool = False  # ``if TYPE_CHECKING:`` — not executed at import time
    lazy: bool = False  # inside a function/async def — deferred until call time


@dataclass
class CallEdge:
    caller: str  # qualified name within the module ("Class.method", "func", "<module>")
    callee: str  # dotted text as written at the call site
    line: int
    args: list[str] = field(default_factory=list)  # dotted names of positional args ("" if other)
    kwargs: dict[str, str] = field(default_factory=dict)


@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    calls: list[CallEdge]
    module_name: str
    aliases: dict[str, str] = field(default_factory=dict)  # local name -> fully qualified target
    docstring: str | None = None
    line_count: int = 0
    error: str | None = None
    tree: ast.Module | None = field(default=None, repr=False)
    source: str = field(default="", repr=False)


def module_name_from_path(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def stable_node_id(project_id: str, *parts: str) -> str:
    raw = "|".join([project_id, *parts])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def dotted_name(node: ast.AST | None) -> str | None:
    """`a.b.c` for Name/Attribute chains; unwraps `X.as_view()`-style calls to their func."""
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        if isinstance(cur, ast.Call):
            inner = dotted_name(cur.func)
            if inner:
                parts.append(inner)
                return ".".join(reversed(parts))
    return None


def _strings_in(node: ast.AST) -> list[str]:
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _literal(node: ast.expr) -> str:
    """Short source text for constant/call kwargs (e.g. ``hour=3``, ``crontab(minute=0)``), else ""."""
    if isinstance(node, (ast.Constant, ast.Call)):
        text = ast.unparse(node)
        return text if len(text) <= 80 else ""
    return ""


def _decorator(node: ast.expr) -> Decorator | None:
    if isinstance(node, ast.Call):
        name = dotted_name(node.func)
        if not name:
            return None
        return Decorator(
            name=name,
            args=[dotted_name(a) or "" for a in node.args],
            kwargs={kw.arg: (dotted_name(kw.value) or _literal(kw.value)) for kw in node.keywords if kw.arg},
            strings=[s for a in node.args for s in _strings_in(a)],
        )
    name = dotted_name(node)
    return Decorator(name=name) if name else None


def _resolve_relative(module: str, is_package: bool, level: int, target: str | None) -> str:
    if level == 0:
        return target or ""
    package_parts = module.split(".") if module else []
    if not is_package:
        package_parts = package_parts[:-1]
    keep = len(package_parts) - (level - 1)
    base = package_parts[: max(keep, 0)]
    if target:
        base = [*base, *target.split(".")]
    return ".".join(base)


def _is_type_checking_symbol(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    if isinstance(node, ast.Attribute):
        return node.attr == "TYPE_CHECKING"
    return False


def _type_checking_guard_names(tree: ast.Module) -> set[str]:
    """Module-level names that refer to ``TYPE_CHECKING`` (including aliases)."""
    names = {"TYPE_CHECKING"}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and _is_type_checking_symbol(node.value):
                    names.add(target.id)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "TYPE_CHECKING":
                    names.add(alias.asname or "TYPE_CHECKING")
    return names


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, module: str, is_package: bool, *, tc_names: set[str]) -> None:
        self._module = module
        self._is_package = is_package
        self._tc_names = tc_names
        self.imports: list[ImportInfo] = []
        self.aliases: dict[str, str] = {}
        self._type_checking = 0
        self._func_depth = 0

    def _is_tc_name(self, node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self._tc_names
        if isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING":
            return True
        return False

    def _is_type_only_guard(self, node: ast.expr) -> bool:
        """Whole ``if`` test whose body is not executed at import time under normal runtime."""
        # ``if TYPE_CHECKING or DEBUG:`` can run its body at load time when DEBUG is true.
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            return False
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            return any(self._is_type_only_guard(v) for v in node.values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return False
        if self._is_tc_name(node):
            return True
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = node.ops[0]
            if isinstance(op, (ast.Is, ast.Eq)) and self._is_tc_name(node.left):
                cmp = node.comparators[0]
                return isinstance(cmp, ast.Constant) and cmp.value is True
        return False

    def _if_type_checking_mode(self, test: ast.expr) -> str | None:
        """``body`` if ``if`` body is type-only; ``else`` for ``if not TYPE_CHECKING``."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and self._is_tc_name(test.operand):
            return "else"
        if self._is_type_only_guard(test):
            return "body"
        return None

    def visit_If(self, node: ast.If) -> None:
        mode = self._if_type_checking_mode(node.test)
        if mode == "body":
            self._type_checking += 1
            for stmt in node.body:
                self.visit(stmt)
            self._type_checking -= 1
            for stmt in node.orelse:
                self.visit(stmt)
            return
        if mode == "else":
            for stmt in node.body:
                self.visit(stmt)
            self._type_checking += 1
            for stmt in node.orelse:
                self.visit(stmt)
            self._type_checking -= 1
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        type_only = self._type_checking > 0
        lazy = self._func_depth > 0
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            target = alias.name if alias.asname else alias.name.split(".")[0]
            self.aliases.setdefault(local, target)
            self.imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[],
                    aliases={local: alias.name},
                    line=node.lineno,
                    type_only=type_only,
                    lazy=lazy,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        type_only = self._type_checking > 0
        lazy = self._func_depth > 0
        base = _resolve_relative(self._module, self._is_package, node.level, node.module)
        names = [a.name for a in node.names]
        local_map = {(a.asname or a.name): a.name for a in node.names}
        for local, original in local_map.items():
            if original != "*":
                self.aliases.setdefault(local, f"{base}.{original}" if base else original)
        self.imports.append(
            ImportInfo(
                module=base,
                names=names,
                aliases=local_map,
                line=node.lineno,
                level=node.level,
                type_only=type_only,
                lazy=lazy,
            )
        )


def _first_line(doc: str | None) -> str | None:
    if not doc:
        return None
    for line in doc.strip().splitlines():
        line = line.strip()
        if line:
            return line[:240]
    return None


def _class_info(node: ast.ClassDef, module: str, parent_qn: str | None = None) -> SymbolInfo:
    qn = f"{parent_qn or module}.{node.name}"
    info = SymbolInfo(
        name=node.name,
        kind="class",
        qualified_name=qn,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        bases=[b for b in (dotted_name(b) for b in node.bases) if b],
        decorators=[d for d in (_decorator(d) for d in node.decorator_list) if d],
        docstring=_first_line(ast.get_docstring(node)),
        node=node,
    )
    for item in node.body:
        if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
            ref = dotted_name(item.value)
            if ref:
                info.attrs[item.targets[0].id] = ref
        elif isinstance(item, ast.ClassDef) and item.name == "Meta":
            for meta_item in item.body:
                if isinstance(meta_item, ast.Assign) and len(meta_item.targets) == 1 and isinstance(
                    meta_item.targets[0], ast.Name
                ):
                    key = meta_item.targets[0].id
                    ref = dotted_name(meta_item.value)
                    if ref:
                        info.meta_attrs[key] = ref
                    if isinstance(meta_item.value, ast.Constant) and isinstance(meta_item.value.value, bool):
                        info.meta_flags[key] = meta_item.value.value
    return info


def _function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef, module: str, parent_class: SymbolInfo | None
) -> SymbolInfo:
    if parent_class:
        qn = f"{parent_class.qualified_name}.{node.name}"
        kind = "method"
    else:
        qn = f"{module}.{node.name}"
        kind = "function"
    return SymbolInfo(
        name=node.name,
        kind=kind,
        qualified_name=qn,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        parent_class=parent_class.qualified_name if parent_class else None,
        decorators=[d for d in (_decorator(d) for d in node.decorator_list) if d],
        docstring=_first_line(ast.get_docstring(node)),
        node=node,
    )


def _iter_calls(nodes: list[ast.AST], *, descend_defs: bool):
    """Yield Call nodes, optionally refusing to enter nested function/class definitions."""
    stack: list[ast.AST] = list(reversed(nodes))
    while stack:
        cur = stack.pop()
        if isinstance(cur, ast.Call):
            yield cur
        if not descend_defs and isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(cur))))


# ------------------------------------------------------------------ type hints for call resolution
# `service.list_items()` only resolves when we know `service` is a `ItemService`. Types come from
# parameter annotations (FastAPI `Annotated[T, Depends(...)]` and module-level aliases of it),
# `x = SomeClass(...)`, `x: T = ...`, and for methods `self.attr` assigned/annotated in the class.

_WRAPPERS = {"Annotated", "Optional", "Union", "Final", "ClassVar", "Required", "NotRequired", "ReadOnly"}


def _annotation_type(ann: ast.AST | None, aliases: dict[str, str]) -> str | None:
    """Dotted class name an annotation refers to (unwrapping Annotated/Optional/`X | None`),
    or None for builtins / unknown shapes. Module-level aliases (`Dep = Annotated[T, ...]`) apply."""
    if ann is None:
        return None
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):  # "ForwardRef"
        try:
            return _annotation_type(ast.parse(ann.value, mode="eval").body, aliases)
        except SyntaxError:
            return None
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):  # T | None
        for side in (ann.left, ann.right):
            t = _annotation_type(side, aliases)
            if t:
                return t
        return None
    if isinstance(ann, ast.Subscript):
        base = dotted_name(ann.value) or ""
        if base.split(".")[-1] in _WRAPPERS:
            inner = ann.slice.elts if isinstance(ann.slice, ast.Tuple) else [ann.slice]
            for el in inner:
                t = _annotation_type(el, aliases)
                if t:
                    return t
        return None  # list[T], dict[...]: a container, not T
    name = dotted_name(ann)
    if not name or name == "None":
        return None
    if name in aliases:
        return aliases[name]
    return name if name.split(".")[-1][:1].isupper() else None


def _module_type_aliases(tree: ast.Module) -> dict[str, str]:
    """`XDep = Annotated[XService, Depends(...)]`, `X: TypeAlias = ...`, `type X = ...`."""
    out: dict[str, str] = {}
    for node in tree.body:
        value = None
        name = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
            if not isinstance(value, ast.Subscript):
                continue
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            if (dotted_name(node.annotation) or "").split(".")[-1] != "TypeAlias":
                continue
            name, value = node.target.id, node.value
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias) and isinstance(node.name, ast.Name):
            name, value = node.name.id, node.value
        if name and value is not None:
            t = _annotation_type(value, out)
            if t:
                out[name] = t
    return out


def _constructed_type(value: ast.AST | None, aliases: dict[str, str]) -> str | None:
    """`SomeClass(...)` / `await SomeClass.create(...)` is not inferred; only direct construction."""
    if isinstance(value, ast.Call):
        name = dotted_name(value.func)
        if name and name.split(".")[-1][:1].isupper():
            return aliases.get(name, name)
    return None


def _local_types(fn: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str]) -> dict[str, str]:
    types: dict[str, str] = {}
    args = fn.args
    for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
        t = _annotation_type(a.annotation, aliases)
        if t:
            types[a.arg] = t
    for node in ast.walk(fn):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            t = _annotation_type(node.annotation, aliases) or _constructed_type(node.value, aliases)
            if t:
                types.setdefault(node.target.id, t)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            t = _constructed_type(node.value, aliases)
            if t:
                types.setdefault(node.targets[0].id, t)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    t = _constructed_type(item.context_expr, aliases)
                    if t:
                        types.setdefault(item.optional_vars.id, t)
    types.pop("self", None)
    types.pop("cls", None)
    return types


def _instance_attr_types(cls: ast.ClassDef, aliases: dict[str, str]) -> dict[str, str]:
    """`repo: Repo` in the class body, `self.repo = Repo(...)` / `self.repo: Repo` in methods, and
    `self.repo = repo` where the method parameter `repo` is annotated."""
    out: dict[str, str] = {}
    for item in cls.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            t = _annotation_type(item.annotation, aliases)
            if t:
                out[item.target.id] = t
    for item in cls.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = _local_types(item, aliases)
        for node in ast.walk(item):
            target = value = ann = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value, ann = node.target, node.value, node.annotation
            if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"):
                continue
            t = _annotation_type(ann, aliases) if ann is not None else None
            t = t or _constructed_type(value, aliases)
            if not t and isinstance(value, ast.Name):
                t = params.get(value.id)
            if t:
                out.setdefault(target.attr, t)
    return out


def _typed_callee(callee: str, local: dict[str, str], self_attrs: dict[str, str]) -> str:
    """Rewrite `svc.list` → `ItemService.list` and `self.repo.get` → `ItemRepository.get`."""
    head, _, rest = callee.partition(".")
    if not rest:
        return callee
    if head == "self":
        attr, _, tail = rest.partition(".")
        if tail and attr in self_attrs:
            return f"{self_attrs[attr]}.{tail}"
        return callee
    if head in local:
        return f"{local[head]}.{rest}"
    return callee


def _call_edge(
    caller: str, call: ast.Call, local: dict[str, str] | None = None, self_attrs: dict[str, str] | None = None
) -> CallEdge | None:
    callee = dotted_name(call.func)
    if not callee:
        return None
    if local or self_attrs:
        callee = _typed_callee(callee, local or {}, self_attrs or {})
    return CallEdge(
        caller=caller,
        callee=callee,
        line=call.lineno,
        args=[dotted_name(a) or "" for a in call.args],
        kwargs={kw.arg: (dotted_name(kw.value) or "") for kw in call.keywords if kw.arg},
    )


def parenthesize_bare_except(source: str) -> str | None:
    """Rewrite Python 3.14 (PEP 758) ``except A, B:`` clauses to ``except (A, B):``.

    The analyzer runs on Python 3.12, whose ``ast`` rejects the unparenthesised form, so files
    using it would otherwise drop out of the graph entirely. Only the text between ``except`` and
    its ``:`` is touched (no lines added or removed), so line numbers stay exact. Returns None when
    there is nothing to rewrite or the source cannot be tokenized.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None
    edits: list[tuple[tuple[int, int], tuple[int, int]]] = []  # (open-paren pos, close-paren pos)
    starts = {tokenize.NEWLINE, tokenize.NL, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT}
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string != "except":
            continue
        if i and tokens[i - 1].type not in starts:
            continue
        j = i + 1
        if j < len(tokens) and tokens[j].string == "*":
            j += 1
        if j >= len(tokens) or tokens[j].string == ":":
            continue
        first, depth, comma, has_as, k = tokens[j], 0, False, False, j
        while k < len(tokens):
            t = tokens[k]
            if t.string in "([{" and t.type == tokenize.OP:
                depth += 1
            elif t.string in ")]}" and t.type == tokenize.OP:
                depth -= 1
            elif depth == 0 and t.type == tokenize.OP and t.string == ",":
                comma = True
            elif depth == 0 and t.type == tokenize.NAME and t.string == "as":
                has_as = True
            elif depth == 0 and t.type == tokenize.OP and t.string == ":":
                break
            elif t.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                k = len(tokens)
                break
            k += 1
        if comma and not has_as and k < len(tokens):
            edits.append((first.start, tokens[k - 1].end))
    if not edits:
        return None
    lines = source.splitlines(keepends=True)
    for (orow, ocol), (crow, ccol) in reversed(edits):
        lines[crow - 1] = lines[crow - 1][:ccol] + ")" + lines[crow - 1][ccol:]
        lines[orow - 1] = lines[orow - 1][:ocol] + "(" + lines[orow - 1][ocol:]
    return "".join(lines)


def parse_python_source(
    source: str, module: str, *, is_package: bool = False, filename: str = "<string>"
) -> ParseResult:
    try:
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            fixed = parenthesize_bare_except(source)
            if fixed is None:
                raise
            tree = ast.parse(fixed, filename=filename)
    except (SyntaxError, ValueError) as exc:  # a broken file must never abort the whole index
        return ParseResult(
            symbols=[],
            imports=[],
            calls=[],
            module_name=module,
            line_count=source.count("\n") + 1,
            error=f"{type(exc).__name__}: {exc}",
            source=source,
        )

    symbols: list[SymbolInfo] = []
    calls: list[CallEdge] = []
    imp_col = _ImportCollector(module, is_package, tc_names=_type_checking_guard_names(tree))
    imp_col.visit(tree)
    imports = imp_col.imports
    aliases = imp_col.aliases

    type_aliases = _module_type_aliases(tree)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls = _class_info(node, module)
            symbols.append(cls)
            for edge_node in _iter_calls(node.body, descend_defs=False):
                edge = _call_edge(cls.qualified_name.removeprefix(module + "."), edge_node)
                if edge:
                    calls.append(edge)
            self_attrs = _instance_attr_types(node, type_aliases)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method = _function_info(item, module, cls)
                    symbols.append(method)
                    local = method.qualified_name.removeprefix(module + ".")
                    types = _local_types(item, type_aliases)
                    for call in _iter_calls(list(ast.iter_child_nodes(item)), descend_defs=True):
                        edge = _call_edge(local, call, types, self_attrs)
                        if edge:
                            calls.append(edge)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = _function_info(node, module, None)
            symbols.append(fn)
            local = fn.qualified_name.removeprefix(module + ".")
            types = _local_types(node, type_aliases)
            for call in _iter_calls(list(ast.iter_child_nodes(node)), descend_defs=True):
                edge = _call_edge(local, call, types)
                if edge:
                    calls.append(edge)

    module_level = [
        n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for call in _iter_calls(module_level, descend_defs=False):
        edge = _call_edge("<module>", call)
        if edge:
            calls.append(edge)

    return ParseResult(
        symbols=symbols,
        imports=imports,
        calls=calls,
        module_name=module,
        aliases=aliases,
        docstring=_first_line(ast.get_docstring(tree)),
        line_count=source.count("\n") + 1,
        tree=tree,
        source=source,
    )


def parse_python_file(
    root: Path, file_path: Path, *, module_name: str | None = None
) -> ParseResult:
    source = file_path.read_text(encoding="utf-8", errors="replace")
    module = module_name or module_name_from_path(root, file_path)
    return parse_python_source(
        source,
        module,
        is_package=file_path.name == "__init__.py",
        filename=str(file_path),
    )


def structural_fingerprint(result: ParseResult) -> str:
    """Hash of the *shape* of a module: symbols, signatures, imports, call targets.

    Formatting, comments, docstrings, and logic edits that do not change who is
    called leave this hash unchanged, which is how COSMETIC edits are told apart
    from STRUCTURAL ones.
    """
    if result.error:
        return "syntax-error"
    parts: list[str] = []
    for sym in sorted(result.symbols, key=lambda s: s.qualified_name):
        decos = ",".join(sorted(d.name for d in sym.decorators))
        params = ""
        if isinstance(sym.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = sym.node.args
            params = ",".join(
                x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]
            ) + ("*" if a.vararg else "") + ("**" if a.kwarg else "")
        parts.append(f"S|{sym.kind}|{sym.qualified_name}|{','.join(sym.bases)}|{decos}|{params}")
        for key, value in sorted({**sym.attrs, **{f'Meta.{k}': v for k, v in sym.meta_attrs.items()}}.items()):
            parts.append(f"A|{sym.qualified_name}|{key}={value}")
    for imp in sorted(result.imports, key=lambda i: (i.module, ",".join(i.names))):
        parts.append(f"I|{imp.module}|{','.join(sorted(imp.names))}")
    callee_set = sorted({(c.caller, c.callee) for c in result.calls})
    parts.extend(f"C|{caller}|{callee}" for caller, callee in callee_set)
    if result.tree is not None:
        # Route tables, settings lists, and field declarations are module/class-level
        # assignments; their literal text is architecture, not logic.
        for node in result.tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                parts.append("V|" + ast.dump(node, annotate_fields=False)[:2000])
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:24]
