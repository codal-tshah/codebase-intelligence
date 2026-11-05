"""Python source analysis built on the standard-library `ast`.

The parser is framework-neutral: it extracts symbols, imports (with relative
imports resolved to absolute module names), call sites, decorators, and class
attributes. Framework adapters interpret that structure.
"""

from __future__ import annotations

import ast
import hashlib
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


def _decorator(node: ast.expr) -> Decorator | None:
    if isinstance(node, ast.Call):
        name = dotted_name(node.func)
        if not name:
            return None
        return Decorator(
            name=name,
            args=[dotted_name(a) or "" for a in node.args],
            kwargs={kw.arg: (dotted_name(kw.value) or "") for kw in node.keywords if kw.arg},
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


def _call_edge(caller: str, call: ast.Call) -> CallEdge | None:
    callee = dotted_name(call.func)
    if not callee:
        return None
    return CallEdge(
        caller=caller,
        callee=callee,
        line=call.lineno,
        args=[dotted_name(a) or "" for a in call.args],
        kwargs={kw.arg: (dotted_name(kw.value) or "") for kw in call.keywords if kw.arg},
    )


def parse_python_source(
    source: str, module: str, *, is_package: bool = False, filename: str = "<string>"
) -> ParseResult:
    try:
        tree = ast.parse(source, filename=filename)
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
    imports: list[ImportInfo] = []
    calls: list[CallEdge] = []
    aliases: dict[str, str] = {}

    # Imports can appear anywhere (function-local imports are common in Django to avoid cycles).
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else alias.name.split(".")[0]
                aliases.setdefault(local, target)
                imports.append(
                    ImportInfo(module=alias.name, names=[], aliases={local: alias.name}, line=node.lineno)
                )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative(module, is_package, node.level, node.module)
            names = [a.name for a in node.names]
            local_map = {(a.asname or a.name): a.name for a in node.names}
            for local, original in local_map.items():
                if original != "*":
                    aliases.setdefault(local, f"{base}.{original}" if base else original)
            imports.append(
                ImportInfo(module=base, names=names, aliases=local_map, line=node.lineno, level=node.level)
            )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            cls = _class_info(node, module)
            symbols.append(cls)
            for edge_node in _iter_calls(node.body, descend_defs=False):
                edge = _call_edge(cls.qualified_name.removeprefix(module + "."), edge_node)
                if edge:
                    calls.append(edge)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method = _function_info(item, module, cls)
                    symbols.append(method)
                    local = method.qualified_name.removeprefix(module + ".")
                    for call in _iter_calls(list(ast.iter_child_nodes(item)), descend_defs=True):
                        edge = _call_edge(local, call)
                        if edge:
                            calls.append(edge)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = _function_info(node, module, None)
            symbols.append(fn)
            local = fn.qualified_name.removeprefix(module + ".")
            for call in _iter_calls(list(ast.iter_child_nodes(node)), descend_defs=True):
                edge = _call_edge(local, call)
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
