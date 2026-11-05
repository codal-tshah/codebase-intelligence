"""TypeScript / JavaScript analysis built on tree-sitter.

One pass per file extracts symbols (functions, classes, React components, hooks,
object-literal API clients), imports/exports, call sites, JSX usage, HTTP
requests, and route registrations. A second pass resolves names across files
(relative imports, tsconfig `paths`, `@/` aliases, workspace packages, re-exports,
CommonJS) and emits graph nodes/edges. Frontend HTTP calls are returned as
`HttpCall`s so the indexer can link them to backend endpoints from any analyzer.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from ci_core.analysis import AnalysisResult, HttpCall
from ci_core.insights import GraphIndex, classify_complexity
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_parsers import file_sha256, stable_node_id

from ci_adapters_typescript.roles import (
    HTTP_CLIENT_OBJECTS,
    HTTP_VERBS,
    HTTP_WRAPPER_FUNCS,
    NEST_ROUTE_DECORATORS,
    ROLE_LABEL,
    ROUTE_VERBS,
    ROUTER_OBJECTS,
    classify_module,
    framework_for,
    is_component_name,
    is_hook_name,
    layer_for_role,
    package_root,
    sdk_for,
)

ANALYZER_VERSION = "1"
EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
RESOLVE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
MAX_BYTES = 600_000
EXTRACTOR = "ts.analyzer"

_LANG_TS = Language(tsts.language_typescript())
_LANG_TSX = Language(tsts.language_tsx())
FUNCTION_NODES = {"arrow_function", "function_expression", "function", "generator_function"}
CLASS_NODES = {"class_declaration", "abstract_class_declaration", "class"}


# ------------------------------------------------------------------ node helpers


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", "replace") if node is not None and node.text is not None else ""


def _line(node: Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: Node) -> int:
    return node.end_point[0] + 1


def _named(node: Node | None) -> list[Node]:
    return [c for c in node.named_children if c.type != "comment"] if node is not None else []


def _string_value(node: Node | None) -> str | None:
    """Literal text of a string/template; template substitutions become `${x}`."""
    if node is None:
        return None
    if node.type == "string":
        return _text(node)[1:-1]
    if node.type == "template_string":
        raw = node.text or b""
        base = node.start_byte
        pieces: list[str] = []
        cursor = base + 1
        for child in node.children:
            if child.type == "template_substitution":
                pieces.append(raw[cursor - base : child.start_byte - base].decode("utf-8", "replace"))
                pieces.append("${x}")
                cursor = child.end_byte
        pieces.append(raw[cursor - base : node.end_byte - base - 1].decode("utf-8", "replace"))
        return "".join(pieces)
    return None


def _callee_text(node: Node | None) -> str:
    """`a.b.c` for member chains; chained calls keep their shape (`router.route().get`)."""
    if node is None:
        return ""
    t = node.type
    if t in ("identifier", "property_identifier", "type_identifier", "shorthand_property_identifier"):
        return _text(node)
    if t == "this":
        return "this"
    if t == "super":
        return "super"
    if t == "member_expression":
        obj = _callee_text(node.child_by_field_name("object"))
        prop = _text(node.child_by_field_name("property"))
        return f"{obj}.{prop}" if obj else prop
    if t == "call_expression":
        inner = _callee_text(node.child_by_field_name("function"))
        return f"{inner}()" if inner else ""
    if t in ("non_null_expression", "parenthesized_expression", "as_expression", "await_expression"):
        named = _named(node)
        return _callee_text(named[0]) if named else ""
    return ""


def _object_pairs(node: Node | None) -> dict[str, Node]:
    out: dict[str, Node] = {}
    if node is None or node.type != "object":
        return out
    for child in _named(node):
        if child.type == "pair":
            key = child.child_by_field_name("key")
            value = child.child_by_field_name("value")
            if key is not None and value is not None:
                k = _string_value(key) if key.type == "string" else _text(key)
                out[k] = value
    return out


def _function_value(value: Node | None) -> Node | None:
    """The function node for `x = () => ...`, `x = function () {}`, `x = memo(() => ...)`."""
    if value is None:
        return None
    if value.type in FUNCTION_NODES:
        return value
    if value.type == "call_expression":
        callee = _callee_text(value.child_by_field_name("function")).split(".")[-1]
        if callee in ("memo", "forwardRef", "observer", "styled", "withRouter", "lazy", "connect", "defineComponent", "useCallback"):
            for arg in _named(value.child_by_field_name("arguments")):
                if arg.type in FUNCTION_NODES:
                    return arg
    return None


def _contains_jsx(node: Node) -> bool:
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in ("jsx_element", "jsx_self_closing_element", "jsx_fragment"):
            return True
        stack.extend(cur.children)
    return False


def _parse_jsonc(text: str) -> dict[str, Any]:
    """JSON with comments and trailing commas (tsconfig.json)."""
    out: list[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    cleaned = re.sub(r",(\s*[}\]])", r"\1", "".join(out))
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ data classes


@dataclass
class _Sym:
    id: str
    name: str  # display/local key: "App", "UsersService.findAll", "api.getItems"
    kind: str  # function | class | method | object
    node: Node
    start: int
    end: int
    parent: str | None = None  # owning class/object local name
    exported: bool = False
    is_component: bool = False
    is_hook: bool = False
    decorators: list[tuple[str, list[str], Node]] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    ctor_props: dict[str, str] = field(default_factory=dict)  # this.<prop> -> type name
    injects: list[str] = field(default_factory=list)  # constructor parameter types
    params: int = 0
    role: str | None = None


@dataclass
class _Route:
    id: str
    module: _Mod
    verb: str
    path: str
    line: int
    end_line: int
    handlers: list[Node]  # identifiers / member expressions to resolve
    framework: str
    handler_id: str | None = None  # already-known handler (Nest/Next)
    guards: list[str] = field(default_factory=list)
    prefix_mode: str = "module"  # module (express mounts) | nest | absolute


@dataclass
class _Mod:
    rel: str
    path: Path
    tsx: bool
    source: bytes
    tree: Any
    role: str
    id: str
    lines: int
    symbols: dict[str, _Sym] = field(default_factory=dict)
    by_node: dict[tuple[int, int, str], _Sym] = field(default_factory=dict)
    bindings: dict[str, tuple[str, ...]] = field(default_factory=dict)
    exports: dict[str, str] = field(default_factory=dict)  # exported name -> local name
    reexports: list[tuple[str, str, str]] = field(default_factory=list)  # (spec, imported, exported)
    star_exports: list[str] = field(default_factory=list)
    default_export: str | None = None
    import_specs: list[tuple[str, int]] = field(default_factory=list)
    resolved: dict[str, str | None] = field(default_factory=dict)
    calls: list[tuple[str, str, int, _Sym | None]] = field(default_factory=list)  # caller id, callee, line, class ctx
    jsx: list[tuple[str, str, int]] = field(default_factory=list)  # caller id, element name, line
    page_routes: list[tuple[str, str, int]] = field(default_factory=list)  # (path, component expr, line)
    router_vars: set[str] = field(default_factory=set)
    mounts: list[tuple[str, tuple[str, str], int]] = field(default_factory=list)  # prefix, ("ident"|"spec", v), line
    global_prefix: str | None = None
    has_error: bool = False
    packages_used: set[str] = field(default_factory=set)


# -------------------------------------------------------------------- analyzer


class TypeScriptAnalyzer:
    id = "typescript"
    name = "TypeScript / JavaScript (React, Express, NestJS, Next.js)"
    version = ANALYZER_VERSION
    extensions = EXTENSIONS

    def detect(self, root: Path, files: Sequence[Path]) -> bool:
        return bool(files)

    def analyze(self, project_id: str, root: Path, files: Sequence[Path]) -> AnalysisResult:
        return _Analyzer(project_id, root, files).run()


ANALYZER = TypeScriptAnalyzer()


class _Analyzer:
    def __init__(self, project_id: str, root: Path, files: Sequence[Path]):
        self.pid = project_id
        self.root = root
        self.files = sorted(f for f in files if f.stat().st_size <= MAX_BYTES)
        self.mods: dict[str, _Mod] = {}
        self.file_set: set[str] = set()
        self.nodes: dict[str, NodeRecord] = {}
        self.edges: dict[str, EdgeRecord] = {}
        self.routes: list[_Route] = []
        self.result = AnalysisResult(analyzer="typescript")
        self.frameworks: set[str] = set()
        self.project_node_id = stable_node_id(project_id, "project")
        self._tsconfig_cache: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self.package_dirs: dict[str, dict[str, Any]] = {}  # rel dir -> package.json
        self.workspace_names: dict[str, str] = {}  # package name -> rel dir
        self.parser_ts = Parser(_LANG_TS)
        self.parser_tsx = Parser(_LANG_TSX)

    # --------------------------------------------------------------------- run

    def run(self) -> AnalysisResult:
        self._load_package_json()
        for f in self.files:
            self._parse(f)
        for mod in self.mods.values():
            self._collect_top_level(mod)
        for mod in self.mods.values():
            self._walk(mod)
        for mod in self.mods.values():
            mod.resolved = {spec: self._resolve_spec(mod, spec) for spec, _ in mod.import_specs}
            for binding in mod.bindings.values():
                if binding[0] in ("import", "namespace", "require") and binding[1] not in mod.resolved:
                    mod.resolved[binding[1]] = self._resolve_spec(mod, binding[1])
            for spec, _, _ in mod.reexports:
                mod.resolved.setdefault(spec, self._resolve_spec(mod, spec))
            for spec in mod.star_exports:
                mod.resolved.setdefault(spec, self._resolve_spec(mod, spec))

        self._emit_structure()
        self._link_imports()
        self._nest_routes()
        self._next_routes()
        self._emit_routes()  # endpoints first: inline handlers attribute their calls to them
        self._link_calls()
        self._link_jsx()
        self._emit_page_routes()
        self._enrich()

        res = self.result
        res.nodes = list(self.nodes.values())
        res.edges = [e for e in self.edges.values() if e.source_id in self.nodes and e.target_id in self.nodes]
        res.frameworks = sorted(self.frameworks)
        res.stats = {
            "files": len(self.mods),
            "components": sum(1 for n in res.nodes if n.node_type == NodeType.COMPONENT),
            "endpoints": sum(1 for n in res.nodes if n.node_type == NodeType.ENDPOINT),
        }
        return res

    # ------------------------------------------------------------------ inputs

    def _load_package_json(self) -> None:
        for f in self.files:
            for parent in [f.parent, *f.parents]:
                if parent == self.root.parent:
                    break
                rel = "" if parent == self.root else parent.relative_to(self.root).as_posix()
                if rel in self.package_dirs:
                    break
                pj = parent / "package.json"
                if pj.is_file():
                    try:
                        data = json.loads(pj.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        data = {}
                    self.package_dirs[rel] = data if isinstance(data, dict) else {}
                    name = self.package_dirs[rel].get("name")
                    if isinstance(name, str):
                        self.workspace_names[name] = rel
                    deps = {
                        **(self.package_dirs[rel].get("dependencies") or {}),
                        **(self.package_dirs[rel].get("devDependencies") or {}),
                    }
                    for dep in deps:
                        fw = framework_for(dep)
                        if fw:
                            self.frameworks.add(fw)
                if parent == self.root:
                    break

    def _parse(self, path: Path) -> None:
        rel = path.relative_to(self.root).as_posix()
        try:
            source = path.read_bytes()
        except OSError:
            return
        tsx = not rel.endswith(".ts") or rel.endswith(".tsx")
        parser = self.parser_tsx if tsx else self.parser_ts
        tree = parser.parse(source)
        role = classify_module(rel)
        mod = _Mod(
            rel=rel,
            path=path,
            tsx=tsx,
            source=source,
            tree=tree,
            role=role,
            id=stable_node_id(self.pid, "module", rel),
            lines=source.count(b"\n") + 1,
            has_error=tree.root_node.has_error,
        )
        self.mods[rel] = mod
        self.file_set.add(rel)
        if mod.has_error:
            self.result.warnings.append(f"{rel}: syntax errors (partial analysis)")

    # ------------------------------------------------------------ top level

    def _sym_id(self, mod: _Mod, name: str) -> str:
        return stable_node_id(self.pid, "ts-symbol", mod.rel, name)

    def _add_sym(self, mod: _Mod, sym: _Sym) -> _Sym:
        if sym.name in mod.symbols:
            sym.name = f"{sym.name}@{sym.start}"
            sym.id = self._sym_id(mod, sym.name)
        mod.symbols[sym.name] = sym
        mod.by_node[(sym.node.start_byte, sym.node.end_byte, sym.node.type)] = sym
        return sym

    def _collect_top_level(self, mod: _Mod) -> None:
        for stmt in _named(mod.tree.root_node):
            self._statement(mod, stmt, exported=False, default=False, decorators=[])

    def _decorators(self, node: Node) -> list[tuple[str, list[str], Node]]:
        out = []
        for child in node.children:
            if child.type == "decorator":
                out.append(self._decorator(child))
        return out

    def _decorator(self, deco: Node) -> tuple[str, list[str], Node]:
        inner = _named(deco)[0] if _named(deco) else deco
        if inner.type == "call_expression":
            name = _callee_text(inner.child_by_field_name("function")).split(".")[-1]
            args = []
            for arg in _named(inner.child_by_field_name("arguments")):
                value = _string_value(arg)
                if value is not None:
                    args.append(value)
                elif arg.type == "object":
                    path = _string_value(_object_pairs(arg).get("path"))
                    if path is not None:
                        args.append(path)
                else:
                    args.append("@" + _callee_text(arg))
            return name, args, inner
        return _callee_text(inner).split(".")[-1], [], inner

    def _statement(
        self, mod: _Mod, stmt: Node, *, exported: bool, default: bool, decorators: list[tuple[str, list[str], Node]]
    ) -> None:
        t = stmt.type
        if t == "export_statement":
            is_default = any(c.type == "default" for c in stmt.children)
            decos = self._decorators(stmt)
            decl = stmt.child_by_field_name("declaration")
            if decl is not None:
                self._statement(mod, decl, exported=True, default=is_default, decorators=decos)
            value = stmt.child_by_field_name("value")
            if value is not None and is_default:
                self._default_value(mod, value)
            source = _string_value(stmt.child_by_field_name("source"))
            clause = next((c for c in stmt.named_children if c.type == "export_clause"), None)
            if clause is not None:
                for spec in clause.named_children:
                    if spec.type != "export_specifier":
                        continue
                    name = _text(spec.child_by_field_name("name"))
                    alias = _text(spec.child_by_field_name("alias")) or name
                    if source is not None:
                        mod.reexports.append((source, name, alias))
                    elif alias == "default":
                        mod.default_export = name
                    else:
                        mod.exports[alias] = name
            elif source is not None:
                mod.star_exports.append(source)
            if source is not None:
                mod.import_specs.append((source, _line(stmt)))
            return
        if t == "import_statement":
            self._import(mod, stmt)
            return
        if t in ("function_declaration", "generator_function_declaration", "function_signature"):
            name = _text(stmt.child_by_field_name("name")) or ("default" if default else "")
            if name and t != "function_signature":
                sym = self._function_sym(mod, name, stmt, stmt)
                sym.exported = exported
                if default:
                    mod.default_export = sym.name
            return
        if t in CLASS_NODES:
            name = _text(stmt.child_by_field_name("name")) or ("default" if default else "")
            if name:
                cls = self._class_sym(mod, name, stmt, [*decorators, *self._decorators(stmt)])
                cls.exported = exported
                if default:
                    mod.default_export = cls.name
            return
        if t in ("lexical_declaration", "variable_declaration"):
            for decl in stmt.named_children:
                if decl.type == "variable_declarator":
                    self._declarator(mod, decl, exported)
            return
        if t == "expression_statement":
            expr = _named(stmt)[0] if _named(stmt) else None
            if expr is not None and expr.type == "assignment_expression":
                left = _callee_text(expr.child_by_field_name("left"))
                right = expr.child_by_field_name("right")
                if left == "module.exports" and right is not None:
                    if right.type == "identifier":
                        mod.default_export = _text(right)
                    elif right.type == "object":
                        for child in _named(right):
                            if child.type == "shorthand_property_identifier":
                                mod.exports[_text(child)] = _text(child)
                            elif child.type == "pair":
                                key = _text(child.child_by_field_name("key"))
                                val = child.child_by_field_name("value")
                                if val is not None and val.type == "identifier":
                                    mod.exports[key] = _text(val)
                    elif _function_value(right) is not None:
                        sym = self._function_sym(mod, "default", right, _function_value(right))
                        mod.default_export = sym.name
                elif left.startswith("exports.") or left.startswith("module.exports."):
                    key = left.rsplit(".", 1)[-1]
                    fn = _function_value(right)
                    if fn is not None:
                        sym = self._function_sym(mod, key, right, fn)
                        sym.exported = True
                    elif right is not None and right.type == "identifier":
                        mod.exports[key] = _text(right)

    def _default_value(self, mod: _Mod, value: Node) -> None:
        if value.type == "identifier":
            mod.default_export = _text(value)
            return
        fn = _function_value(value)
        if fn is not None:
            stem = Path(mod.rel).name.split(".")[0]
            name = stem[:1].upper() + stem[1:] if _contains_jsx(fn) else "default"
            sym = self._function_sym(mod, name if name not in ("Index", "Page", "Route") else f"{name}Default", value, fn)
            sym.exported = True
            mod.default_export = sym.name
            return
        if value.type == "call_expression":  # export default memo(Foo) / connect(...)(Foo)
            stack = [value]
            while stack:
                cur = stack.pop()
                for arg in _named(cur.child_by_field_name("arguments")):
                    if arg.type == "identifier" and _text(arg) in mod.symbols:
                        mod.default_export = _text(arg)
                        return
                fn_node = cur.child_by_field_name("function")
                if fn_node is not None and fn_node.type == "call_expression":
                    stack.append(fn_node)
        if value.type == "class":
            self._class_sym(mod, "default", value, [])
            mod.default_export = "default"

    def _import(self, mod: _Mod, stmt: Node) -> None:
        spec = _string_value(stmt.child_by_field_name("source"))
        if spec is None:
            return
        mod.import_specs.append((spec, _line(stmt)))
        if not spec.startswith((".", "/", "@/", "~/")):
            mod.packages_used.add(package_root(spec))
        clause = next((c for c in stmt.named_children if c.type == "import_clause"), None)
        if clause is None:
            return
        for part in clause.named_children:
            if part.type == "identifier":
                mod.bindings[_text(part)] = ("import", spec, "default")
            elif part.type == "namespace_import":
                ident = next((c for c in part.named_children if c.type == "identifier"), None)
                if ident is not None:
                    mod.bindings[_text(ident)] = ("namespace", spec)
            elif part.type == "named_imports":
                for item in part.named_children:
                    if item.type != "import_specifier":
                        continue
                    name = _text(item.child_by_field_name("name"))
                    alias = _text(item.child_by_field_name("alias")) or name
                    mod.bindings[alias] = ("import", spec, name)

    def _declarator(self, mod: _Mod, decl: Node, exported: bool) -> None:
        name_node = decl.child_by_field_name("name")
        value = decl.child_by_field_name("value")
        if name_node is None or value is None:
            return
        if name_node.type == "object_pattern" and value.type == "call_expression":
            if _callee_text(value.child_by_field_name("function")) == "require":
                spec = _string_value(_named(value.child_by_field_name("arguments"))[0]) if _named(value.child_by_field_name("arguments")) else None
                if spec:
                    mod.import_specs.append((spec, _line(decl)))
                    for child in _named(name_node):
                        if child.type == "shorthand_property_identifier_pattern":
                            mod.bindings[_text(child)] = ("import", spec, _text(child))
            return
        if name_node.type != "identifier":
            return
        name = _text(name_node)
        fn = _function_value(value)
        if fn is not None:
            sym = self._function_sym(mod, name, value, fn)
            sym.exported = exported
            return
        if value.type in ("class",):
            cls = self._class_sym(mod, name, value, [])
            cls.exported = exported
            return
        if value.type in ("call_expression", "new_expression", "await_expression"):
            call = value if value.type != "await_expression" else (_named(value)[0] if _named(value) else value)
            callee = _callee_text(call.child_by_field_name("function") or call.child_by_field_name("constructor"))
            tail = callee.split(".")[-1]
            if callee == "require":
                args = _named(call.child_by_field_name("arguments"))
                spec = _string_value(args[0]) if args else None
                if spec:
                    mod.import_specs.append((spec, _line(decl)))
                    mod.bindings[name] = ("require", spec)
                    if not spec.startswith((".", "/")):
                        mod.packages_used.add(package_root(spec))
                return
            if tail in ("Router", "express", "Hono", "fastify", "Koa", "createServer") or callee.endswith("Router"):
                mod.router_vars.add(name)
            # stores/contexts are still useful symbols for search and impact
            if tail in ("createContext", "createSlice", "create", "defineStore", "createStore", "configureStore", "atom"):
                sym = _Sym(
                    id=self._sym_id(mod, name), name=name, kind="object", node=value,
                    start=_line(decl), end=_end_line(decl), exported=exported, role="stores",
                )
                self._add_sym(mod, sym)
            return
        if value.type == "object":
            members = []
            for child in _named(value):
                member_name, member_fn = None, None
                if child.type == "method_definition":
                    member_name, member_fn = _text(child.child_by_field_name("name")), child
                elif child.type == "pair":
                    member_fn = _function_value(child.child_by_field_name("value"))
                    member_name = _text(child.child_by_field_name("key")) if member_fn is not None else None
                if member_name and member_fn is not None:
                    members.append((member_name, child, member_fn))
            if members:
                obj = _Sym(
                    id=self._sym_id(mod, name), name=name, kind="object", node=value,
                    start=_line(decl), end=_end_line(decl), exported=exported,
                )
                self._add_sym(mod, obj)
                for member_name, child, member_fn in members:
                    sym = self._function_sym(mod, f"{name}.{member_name}", child, member_fn, kind="method", parent=name)
                    sym.exported = exported

    def _function_sym(
        self, mod: _Mod, name: str, node: Node, fn: Node | None, *, kind: str = "function", parent: str | None = None
    ) -> _Sym:
        fn = fn or node
        params = fn.child_by_field_name("parameters") or fn.child_by_field_name("parameter")
        short = name.split(".")[-1]
        has_jsx = _contains_jsx(fn)
        sym = _Sym(
            id=self._sym_id(mod, name),
            name=name,
            kind=kind,
            node=node,
            start=_line(node),
            end=_end_line(node),
            parent=parent,
            is_component=kind == "function" and is_component_name(short) and (has_jsx or mod.rel.endswith((".tsx", ".jsx"))),
            is_hook=is_hook_name(short),
            params=len(_named(params)) if params is not None and params.type != "identifier" else (1 if params is not None else 0),
        )
        return self._add_sym(mod, sym)

    def _class_sym(self, mod: _Mod, name: str, node: Node, decorators: list[tuple[str, list[str], Node]]) -> _Sym:
        bases: list[str] = []
        for child in node.children:
            if child.type == "class_heritage":
                for clause in child.named_children:
                    if clause.type == "extends_clause":
                        for v in _named(clause):
                            text = _callee_text(v)
                            if text:
                                bases.append(text)
                    elif clause.type in ("identifier", "member_expression"):  # JS grammar: `extends X` directly
                        bases.append(_callee_text(clause))
        cls = _Sym(
            id=self._sym_id(mod, name), name=name, kind="class", node=node,
            start=_line(node), end=_end_line(node), decorators=decorators, bases=bases,
        )
        cls.is_component = any(b.split(".")[-1] in ("Component", "PureComponent") for b in bases)
        self._add_sym(mod, cls)
        body = node.child_by_field_name("body")
        pending: list[tuple[str, list[str], Node]] = []
        for member in body.named_children if body is not None else []:
            if member.type == "decorator":
                pending.append(self._decorator(member))
                continue
            if member.type == "method_definition":
                mname = _text(member.child_by_field_name("name"))
                decos = [*pending, *self._decorators(member)]
                pending = []
                if mname == "constructor":
                    self._constructor(cls, member)
                msym = self._function_sym(mod, f"{name}.{mname}", member, member, kind="method", parent=name)
                msym.decorators = decos
            elif member.type in ("public_field_definition", "field_definition"):
                fn = _function_value(member.child_by_field_name("value"))
                pending = []
                if fn is not None:
                    fname = _text(member.child_by_field_name("name") or member.child_by_field_name("property"))
                    if fname:
                        self._function_sym(mod, f"{name}.{fname}", member, fn, kind="method", parent=name)
            else:
                pending = []
        return cls

    def _constructor(self, cls: _Sym, ctor: Node) -> None:
        params = ctor.child_by_field_name("parameters")
        for p in _named(params):
            if p.type not in ("required_parameter", "optional_parameter"):
                continue
            pattern = p.child_by_field_name("pattern")
            annotation = p.child_by_field_name("type")
            type_name = ""
            if annotation is not None:
                inner = _named(annotation)
                type_name = _callee_text(inner[0]) if inner else ""
                if not type_name and inner:
                    type_name = _text(inner[0]).split("<")[0]
            if not type_name:
                continue
            cls.injects.append(type_name)
            if any(c.type in ("accessibility_modifier", "readonly") or _text(c) == "readonly" for c in p.children):
                cls.ctor_props[_text(pattern)] = type_name

    # ------------------------------------------------------------------- walk

    def _walk(self, mod: _Mod) -> None:
        """Attribute call sites, JSX, HTTP requests and routes to the innermost known symbol."""
        claims: dict[tuple[int, int, str], str] = {}
        stack: list[tuple[Node, str, _Sym | None]] = [(mod.tree.root_node, mod.id, None)]
        while stack:
            node, caller, cls = stack.pop()
            key = (node.start_byte, node.end_byte, node.type)
            sym = mod.by_node.get(key)
            if sym is not None:
                caller = sym.id
                if sym.kind == "class":
                    cls = sym
            elif key in claims:
                caller = claims[key]
            t = node.type
            if t == "call_expression":
                self._on_call(mod, node, caller, cls, claims)
            elif t == "new_expression":
                callee = _callee_text(node.child_by_field_name("constructor"))
                if callee:
                    mod.calls.append((caller, callee, _line(node), cls))
            elif t in ("jsx_opening_element", "jsx_self_closing_element"):
                name = _callee_text(node.child_by_field_name("name")) or _text(node.child_by_field_name("name"))
                if name and name[:1].isupper():
                    mod.jsx.append((caller, name, _line(node)))
                    if name.split(".")[-1] == "Route":
                        self._jsx_route(mod, node)
            elif t == "object":
                pairs = _object_pairs(node)
                path = _string_value(pairs.get("path"))
                target = pairs.get("element") or pairs.get("component") or pairs.get("Component")
                if path is not None and target is not None:
                    mod.page_routes.append((path, self._component_ref(target), _line(node)))
            elif t == "import" and node.parent is not None and node.parent.type == "call_expression":
                pass
            stack.extend((child, caller, cls) for child in reversed(node.children))

    def _component_ref(self, node: Node) -> str:
        if node.type in ("jsx_self_closing_element", "jsx_opening_element"):
            return _callee_text(node.child_by_field_name("name"))
        if node.type == "jsx_element":
            return self._component_ref(node.child_by_field_name("open_tag")) if node.child_by_field_name("open_tag") else ""
        if node.type == "jsx_expression":
            inner = _named(node)
            return self._component_ref(inner[0]) if inner else ""
        return _callee_text(node)

    def _jsx_route(self, mod: _Mod, node: Node) -> None:
        path, target = None, ""
        for attr in node.named_children:
            if attr.type != "jsx_attribute":
                continue
            parts = _named(attr)
            if not parts:
                continue
            key = _text(parts[0])
            value = parts[1] if len(parts) > 1 else None
            if key == "path" and value is not None:
                path = _string_value(value)
                if path is None and value.type == "jsx_expression" and _named(value):
                    path = _string_value(_named(value)[0])
            elif key in ("element", "component", "Component") and value is not None:
                target = self._component_ref(value)
        if path is not None and target:
            mod.page_routes.append((path, target, _line(node)))

    def _on_call(
        self, mod: _Mod, node: Node, caller: str, cls: _Sym | None, claims: dict[tuple[int, int, str], str]
    ) -> None:
        fn = node.child_by_field_name("function")
        args = _named(node.child_by_field_name("arguments"))
        if fn is not None and fn.type == "import":  # dynamic import()
            spec = _string_value(args[0]) if args else None
            if spec:
                mod.import_specs.append((spec, _line(node)))
            return
        callee = _callee_text(fn)
        if not callee:
            return
        tail = callee.rsplit(".", 1)[-1]
        obj = callee.rsplit(".", 1)[0] if "." in callee else ""
        obj_tail = obj.rsplit(".", 1)[-1]
        first = _string_value(args[0]) if args else None

        if callee == "require":
            if first:
                mod.import_specs.append((first, _line(node)))
            return
        if tail == "setGlobalPrefix" and first is not None:
            mod.global_prefix = first
            return

        # Express-style route registration: app.get('/x', mw, handler)
        if (
            tail in ROUTE_VERBS
            and first is not None
            and first.startswith(("/", "*"))
            and len(args) >= 2
            and ROUTER_OBJECTS.match(obj_tail or "")
            and (obj_tail in mod.router_vars or obj_tail in ("app", "router", "server") or any(a.type in FUNCTION_NODES for a in args[1:]))
        ):
            rid = stable_node_id(self.pid, "ts-endpoint", mod.rel, str(_line(node)), tail, first)
            handlers: list[Node] = []
            for arg in args[1:]:
                if arg.type in FUNCTION_NODES:
                    claims[(arg.start_byte, arg.end_byte, arg.type)] = rid
                elif arg.type in ("identifier", "member_expression", "call_expression"):
                    handlers.append(arg)
            self.routes.append(
                _Route(
                    id=rid, module=mod, verb=tail.upper(), path=first, line=_line(node), end_line=_end_line(node),
                    handlers=handlers, framework="express",
                )
            )
            self.frameworks.add("express")
            return
        # app.use('/api', router)
        if tail == "use" and first is not None and first.startswith("/") and len(args) >= 2:
            for arg in args[1:]:
                if arg.type == "identifier":
                    mod.mounts.append((first, ("ident", _text(arg)), _line(node)))
                elif arg.type == "call_expression" and _callee_text(arg.child_by_field_name("function")) == "require":
                    inner = _named(arg.child_by_field_name("arguments"))
                    spec = _string_value(inner[0]) if inner else None
                    if spec:
                        mod.import_specs.append((spec, _line(node)))
                        mod.mounts.append((first, ("spec", spec), _line(node)))
            return

        # Outbound HTTP
        if first is not None:
            url = first[4:] if first.startswith("${x}") else first
            looks_like_url = url.startswith("/") or "://" in url
            method: str | None = None
            is_http = False
            options = args[1] if len(args) > 1 else None
            if looks_like_url:
                if tail == "fetch" and obj in ("", "window", "globalThis", "self"):
                    is_http, method = True, self._method_from_options(options) or "GET"
                elif obj and tail in (*HTTP_VERBS, "request") and HTTP_CLIENT_OBJECTS.search(obj_tail):
                    is_http, method = True, (tail.upper() if tail != "request" else self._method_from_options(options))
                elif callee in ("axios", "ky", "got", "$fetch", "ofetch", "useFetch", "useSWR"):
                    is_http, method = True, self._method_from_options(options) or "GET"
                elif not obj and HTTP_WRAPPER_FUNCS.match(callee):
                    lowered = callee.lower()
                    verb = next((v for v in ("post", "put", "patch", "delete", "get") if lowered.startswith(v)), None)
                    is_http = True
                    method = (verb.upper() if verb else None) or self._method_from_options(options) or "GET"
            if is_http:
                url = url.split("?", 1)[0] or "/"
                self.result.http_calls.append(
                    HttpCall(source_id=caller, url=url, method=method, source_path=mod.rel, line=_line(node))
                )
                return
        mod.calls.append((caller, callee, _line(node), cls))

    @staticmethod
    def _method_from_options(options: Node | None) -> str | None:
        value = _string_value(_object_pairs(options).get("method")) if options is not None else None
        return value.upper() if value else None

    # ------------------------------------------------------------- resolution

    def _tsconfigs(self, rel_dir: str) -> list[tuple[str, dict[str, Any]]]:
        """(config dir, compilerOptions) for tsconfig/jsconfig files at or above `rel_dir`."""
        if rel_dir in self._tsconfig_cache:
            return self._tsconfig_cache[rel_dir]
        found: list[tuple[str, dict[str, Any]]] = []
        cur = rel_dir
        while True:
            base = self.root / cur if cur else self.root
            for name in ("tsconfig.json", "tsconfig.app.json", "jsconfig.json"):
                cfg = base / name
                if cfg.is_file():
                    try:
                        data = _parse_jsonc(cfg.read_text(encoding="utf-8"))
                    except OSError:
                        data = {}
                    opts = data.get("compilerOptions") or {}
                    if isinstance(opts, dict) and (opts.get("paths") or opts.get("baseUrl")):
                        found.append((cur, opts))
            if found or not cur:
                break
            cur = posixpath.dirname(cur)
        self._tsconfig_cache[rel_dir] = found
        return found

    def _package_dir_of(self, rel: str) -> str:
        cur = posixpath.dirname(rel)
        while True:
            if cur in self.package_dirs:
                return cur
            if not cur:
                return ""
            cur = posixpath.dirname(cur)

    def _file_for(self, base: str) -> str | None:
        base = posixpath.normpath(base).lstrip("./") if base not in ("", ".") else ""
        if base.startswith("../"):
            return None
        candidates = [base]
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            candidates += [stem + e for e in (".ts", ".tsx")]
        candidates += [base + e for e in RESOLVE_EXTS]
        candidates += [posixpath.join(base, "index" + e) for e in RESOLVE_EXTS]
        for cand in candidates:
            if cand in self.file_set:
                return cand
        return None

    def _resolve_spec(self, mod: _Mod, spec: str) -> str | None:
        here = posixpath.dirname(mod.rel)
        if spec.startswith("."):
            return self._file_for(posixpath.join(here, spec))
        for cfg_dir, opts in self._tsconfigs(here):
            base_url = posixpath.normpath(posixpath.join(cfg_dir, str(opts.get("baseUrl") or ".")))
            base_url = "" if base_url == "." else base_url
            for pattern, targets in (opts.get("paths") or {}).items():
                if not isinstance(targets, list):
                    continue
                if pattern.endswith("*") and spec.startswith(pattern[:-1]):
                    rest = spec[len(pattern) - 1 :]
                elif pattern == spec:
                    rest = ""
                else:
                    continue
                for target in targets:
                    hit = self._file_for(posixpath.join(base_url, str(target).replace("*", rest)))
                    if hit:
                        return hit
            if opts.get("baseUrl"):
                hit = self._file_for(posixpath.join(base_url, spec))
                if hit:
                    return hit
        if spec.startswith(("@/", "~/")):
            pkg = self._package_dir_of(mod.rel)
            for src in ("src", ""):
                hit = self._file_for(posixpath.join(pkg, src, spec[2:]))
                if hit:
                    return hit
        root = package_root(spec)
        if root in self.workspace_names:
            pkg_dir = self.workspace_names[root]
            rest = spec[len(root) :].lstrip("/")
            data = self.package_dirs.get(pkg_dir, {})
            entries = [rest] if rest else [str(data.get("source") or ""), str(data.get("main") or ""), "src/index", "index"]
            for entry in entries:
                if entry:
                    hit = self._file_for(posixpath.join(pkg_dir, entry)) or self._file_for(posixpath.join(pkg_dir, "src", entry))
                    if hit:
                        return hit
        if spec.startswith("/"):
            return self._file_for(spec.lstrip("/"))
        return None

    def _lookup(self, mod: _Mod, name: str, depth: int = 0) -> tuple[_Mod, _Sym] | None:
        if depth > 6:
            return None
        sym = mod.symbols.get(name)
        if sym is not None:
            return mod, sym
        binding = mod.bindings.get(name)
        if binding is None:
            return None
        target_rel = mod.resolved.get(binding[1])
        target = self.mods.get(target_rel) if target_rel else None
        if target is None:
            return None
        if binding[0] == "import":
            return self._export(target, binding[2], depth + 1)
        if binding[0] == "require":
            return self._export(target, "default", depth + 1)
        return None

    def _export(self, mod: _Mod, name: str, depth: int = 0) -> tuple[_Mod, _Sym] | None:
        if depth > 6:
            return None
        if name == "default":
            if mod.default_export:
                return self._lookup(mod, mod.default_export, depth + 1)
            return None
        local = mod.exports.get(name)
        if local:
            return self._lookup(mod, local, depth + 1)
        sym = mod.symbols.get(name)
        if sym is not None and sym.exported:
            return mod, sym
        for spec, imported, exported in mod.reexports:
            if exported == name:
                target = self.mods.get(mod.resolved.get(spec) or "")
                if target is not None:
                    return self._export(target, imported, depth + 1)
        for spec in mod.star_exports:
            target = self.mods.get(mod.resolved.get(spec) or "")
            if target is not None:
                hit = self._export(target, name, depth + 1)
                if hit:
                    return hit
        if sym is not None:  # CommonJS / non-exported but referenced through a namespace
            return mod, sym
        return None

    def _member(self, owner_mod: _Mod, owner: _Sym, member: str) -> _Sym | None:
        sym = owner_mod.symbols.get(f"{owner.name}.{member}")
        if sym is not None:
            return sym
        for base in owner.bases:  # inherited method
            hit = self._lookup(owner_mod, base.split(".")[-1])
            if hit and hit[1].kind == "class" and hit[1] is not owner:
                found = hit[0].symbols.get(f"{hit[1].name}.{member}")
                if found:
                    return found
        return None

    def _resolve(self, mod: _Mod, dotted: str, cls: _Sym | None = None) -> _Sym | None:
        parts = [p for p in dotted.replace("()", "").split(".") if p]
        if not parts:
            return None
        head = parts[0]
        if head == "this":
            if cls is None or len(parts) < 2:
                return None
            own = self._member(mod, cls, parts[1])
            if own is not None:
                return own
            type_name = cls.ctor_props.get(parts[1])
            if type_name:
                hit = self._lookup(mod, type_name)
                if hit:
                    if len(parts) >= 3:
                        return self._member(hit[0], hit[1], parts[2]) or hit[1]
                    return hit[1]
            return None
        binding = mod.bindings.get(head)
        if binding is not None and binding[0] in ("namespace", "require") and len(parts) >= 2:
            target = self.mods.get(mod.resolved.get(binding[1]) or "")
            if target is not None:
                hit = self._export(target, parts[1])
                if hit is None and binding[0] == "require":
                    default = self._export(target, "default")
                    if default:
                        return self._member(default[0], default[1], parts[1]) or default[1]
                if hit:
                    if len(parts) >= 3 and hit[1].kind in ("class", "object"):
                        return self._member(hit[0], hit[1], parts[2]) or hit[1]
                    return hit[1]
            return None
        hit = self._lookup(mod, head)
        if hit is None:
            return None
        owner_mod, sym = hit
        if len(parts) == 1:
            return sym
        if sym.kind in ("class", "object"):
            return self._member(owner_mod, sym, parts[1]) or (sym if sym.kind == "class" else None)
        return None

    def _sym_by_id(self) -> dict[str, tuple[_Mod, _Sym]]:
        out = {}
        for mod in self.mods.values():
            for sym in mod.symbols.values():
                out[sym.id] = (mod, sym)
        return out

    # ------------------------------------------------------------------ nodes

    def _edge(
        self, edge_type: EdgeType, src: str, tgt: str, *, rel: str | None, line: int | None = None,
        confidence: float = 0.85, extractor: str = EXTRACTOR, **props: Any,
    ) -> None:
        if src == tgt or src not in self.nodes or tgt not in self.nodes:
            return
        eid = stable_node_id(self.pid, "edge", edge_type.value, src, tgt)
        existing = self.edges.get(eid)
        if existing is not None:
            existing.properties["count"] = existing.properties.get("count", 1) + 1
            return
        self.edges[eid] = EdgeRecord(
            id=eid, project_id=self.pid, edge_type=edge_type, source_id=src, target_id=tgt,
            source_path=rel, start_line=line, extractor=extractor, confidence=confidence,
            properties={"count": 1, **props},
        )

    def _package_key(self, rel: str) -> tuple[str, str, str]:
        """(package dir key, sub-package key, display name) for a module path."""
        pkg_dir = self._package_dir_of(rel)
        rest = rel[len(pkg_dir) + 1 :] if pkg_dir else rel
        dirs = rest.split("/")[:-1]
        if len(dirs) >= 2 and dirs[0] in ("src", "app", "lib", "source"):
            sub = "/".join(dirs[:2])
        elif dirs:
            sub = dirs[0]
        else:
            sub = ""
        sub_key = posixpath.join(pkg_dir, sub) if sub else pkg_dir
        return pkg_dir, sub_key, sub.split("/")[-1] if sub else ""

    def _emit_structure(self) -> None:
        self.nodes[self.project_node_id] = NodeRecord(
            id=self.project_node_id, project_id=self.pid, node_type=NodeType.PROJECT,
            name=self.root.name, extractor=EXTRACTOR, properties={},
        )
        multi = len(self.package_dirs) > 1
        pkg_nodes: dict[str, str] = {}

        def package_node(key: str, name: str, parent: str | None, is_root: bool) -> str:
            if key in pkg_nodes:
                return pkg_nodes[key]
            nid = stable_node_id(self.pid, "ts-package", key or ".")
            pkg_nodes[key] = nid
            data = self.package_dirs.get(key, {}) if is_root else {}
            self.nodes[nid] = NodeRecord(
                id=nid, project_id=self.pid, node_type=NodeType.PACKAGE, name=name or self.root.name,
                qualified_name=key or ".", source_path=key or None, extractor=EXTRACTOR, confidence=0.8,
                properties={"language": "typescript", "npm_name": data.get("name") if is_root else None},
            )
            self._edge(EdgeType.CONTAINS, parent or self.project_node_id, nid, rel=None, confidence=1.0)
            return nid

        for mod in self.mods.values():
            pkg_dir, sub_key, sub_name = self._package_key(mod.rel)
            root_name = str(self.package_dirs.get(pkg_dir, {}).get("name") or posixpath.basename(pkg_dir) or self.root.name)
            root_id = package_node(pkg_dir, root_name.split("/")[-1], None, True)
            if sub_key != pkg_dir:
                display = f"{root_name.split('/')[-1]}/{sub_name}" if multi else sub_name
                owner = package_node(sub_key, display, root_id, False)
            else:
                owner = root_id

            self.nodes[mod.id] = NodeRecord(
                id=mod.id, project_id=self.pid, node_type=NodeType.MODULE,
                name=posixpath.splitext(mod.rel)[0], qualified_name=mod.rel, source_path=mod.rel,
                start_line=1, end_line=mod.lines, extractor=EXTRACTOR,
                properties={"role": mod.role, "layer": layer_for_role(mod.role), "line_count": mod.lines, "language": "typescript"},
            )
            self._edge(EdgeType.CONTAINS, owner, mod.id, rel=mod.rel, confidence=1.0)

            for sym in mod.symbols.values():
                self._emit_symbol(mod, sym)

            self.result.files[mod.rel] = {
                "sha": file_sha256(mod.path),
                "structural": self._fingerprint(mod),
                "role": mod.role,
                "lines": mod.lines,
                "language": "typescript",
            }

    def _emit_symbol(self, mod: _Mod, sym: _Sym) -> None:
        deco_names = {d[0] for d in sym.decorators}
        role = sym.role or mod.role
        node_type = NodeType.FUNCTION
        if sym.kind == "class":
            node_type = NodeType.COMPONENT if sym.is_component else NodeType.CLASS
            if "Controller" in deco_names:
                role = "views"
            elif "Injectable" in deco_names:
                role = "permissions" if sym.name.endswith("Guard") else ("middleware" if sym.name.endswith(("Interceptor", "Middleware")) else "services")
            elif "Entity" in deco_names or "Schema" in deco_names:
                role = "models"
                node_type = NodeType.MODEL
            elif "Module" in deco_names:
                role = "settings"
        elif sym.kind == "object":
            node_type = NodeType.CLASS
        elif sym.is_component:
            node_type = NodeType.COMPONENT
            role = "pages" if mod.role == "pages" else "components"
        elif sym.is_hook:
            role = "hooks"
        if node_type == NodeType.COMPONENT and role not in ("pages",):
            role = "components"
        if sym.kind == "method" and sym.parent:
            parent = mod.symbols.get(sym.parent)
            if parent is not None and parent.role:
                role = parent.role
        sym.role = role
        props: dict[str, Any] = {
            "kind": sym.kind,
            "role": role,
            "layer": layer_for_role(role),
            "language": "typescript",
            "exported": sym.exported,
        }
        if sym.bases:
            props["bases"] = sym.bases
        if sym.decorators:
            props["decorators"] = sorted(deco_names)
        if sym.parent:
            props["parent_class"] = sym.parent
        self.nodes[sym.id] = NodeRecord(
            id=sym.id, project_id=self.pid, node_type=node_type, name=sym.name,
            qualified_name=f"{mod.rel}:{sym.name}", source_path=mod.rel,
            start_line=sym.start, end_line=sym.end, extractor=EXTRACTOR,
            confidence=0.9, properties=props,
        )
        parent_id = mod.symbols[sym.parent].id if sym.parent and sym.parent in mod.symbols else mod.id
        self._edge(EdgeType.CONTAINS, parent_id, sym.id, rel=mod.rel, confidence=1.0)

    def _fingerprint(self, mod: _Mod) -> str:
        if mod.has_error:
            return "syntax-error:" + hashlib.sha256(mod.source).hexdigest()[:12]
        parts = [f"S|{s.kind}|{s.name}|{s.params}|{','.join(s.bases)}|{','.join(d[0] for d in s.decorators)}" for s in mod.symbols.values()]
        parts += [f"I|{spec}" for spec, _ in mod.import_specs]
        parts += [f"E|{k}={v}" for k, v in mod.exports.items()] + [f"D|{mod.default_export}"]
        names = {s.id: s.name for s in mod.symbols.values()}
        parts += sorted({f"C|{names.get(c, '<m>')}|{callee}" for c, callee, _, _ in mod.calls})
        parts += sorted({f"J|{names.get(c, '<m>')}|{n}" for c, n, _ in mod.jsx})
        parts += sorted(f"R|{r.verb}|{r.path}" for r in self.routes if r.module is mod)
        parts += sorted(f"H|{h.method}|{h.url}" for h in self.result.http_calls if h.source_path == mod.rel)
        parts += sorted(f"M|{p}|{t}" for p, t, _ in mod.mounts) + sorted(f"P|{p}|{c}" for p, c, _ in mod.page_routes)
        return hashlib.sha256("\n".join(sorted(parts)).encode()).hexdigest()[:24]

    # ------------------------------------------------------------------ edges

    def _external(self, display: str, kind: str) -> str:
        sid = stable_node_id(self.pid, "external", display)
        if sid not in self.nodes:
            self.nodes[sid] = NodeRecord(
                id=sid, project_id=self.pid, node_type=NodeType.EXTERNAL_SERVICE, name=display,
                extractor=EXTRACTOR, confidence=0.9,
                properties={"kind": kind, "layer": "external", "role": "external", "external": True},
            )
        return sid

    def _link_imports(self) -> None:
        for mod in self.mods.values():
            seen: set[str] = set()
            for spec, line in mod.import_specs:
                target = mod.resolved.get(spec)
                if target is None and spec not in mod.resolved:
                    target = self._resolve_spec(mod, spec)
                if target and target != mod.rel and target in self.mods:
                    self._edge(EdgeType.IMPORTS, mod.id, self.mods[target].id, rel=mod.rel, line=line, confidence=0.95)
                elif not spec.startswith((".", "/")):
                    sdk = sdk_for(spec)
                    if sdk and sdk[0] not in seen:
                        seen.add(sdk[0])
                        self._edge(
                            EdgeType.DEPENDS_ON, mod.id, self._external(*sdk), rel=mod.rel, line=line,
                            confidence=0.9, relation="uses",
                        )
                    fw = framework_for(spec)
                    if fw:
                        self.frameworks.add(fw)

    def _link_calls(self) -> None:
        for mod in self.mods.values():
            for caller, callee, line, cls in mod.calls:
                target = self._resolve(mod, callee, cls)
                if target is None or target.id == caller:
                    continue
                self._edge(EdgeType.CALLS, caller, target.id, rel=mod.rel, line=line, confidence=0.8)
            for sym in mod.symbols.values():
                for type_name in sym.injects:  # constructor injection (NestJS/Angular)
                    hit = self._lookup(mod, type_name)
                    if hit is not None:
                        self._edge(
                            EdgeType.INJECTS, sym.id, hit[1].id, rel=mod.rel, line=sym.start,
                            confidence=0.9, relation="constructor",
                        )
                for base in sym.bases:
                    hit = self._lookup(mod, base.split(".")[-1])
                    if hit is not None:
                        self._edge(
                            EdgeType.DEPENDS_ON, sym.id, hit[1].id, rel=mod.rel, line=sym.start,
                            confidence=0.95, relation="inherits",
                        )

    def _link_jsx(self) -> None:
        for mod in self.mods.values():
            for caller, name, line in mod.jsx:
                target = self._resolve(mod, name)
                if target is None or target.id == caller:
                    continue
                if not (target.is_component or target.kind == "class" and target.is_component):
                    continue
                self._edge(EdgeType.RENDERS, caller, target.id, rel=mod.rel, line=line, confidence=0.9)

    # ----------------------------------------------------------------- routes

    def _nest_routes(self) -> None:
        global_prefix = next((m.global_prefix for m in self.mods.values() if m.global_prefix), "") or ""
        for mod in self.mods.values():
            for cls in [s for s in mod.symbols.values() if s.kind == "class"]:
                ctrl = next((d for d in cls.decorators if d[0] == "Controller"), None)
                if ctrl is None:
                    continue
                self.frameworks.add("nestjs")
                prefix = next((a for a in ctrl[1] if not a.startswith("@")), "")
                class_guards = [a[1:] for d in cls.decorators if d[0] == "UseGuards" for a in d[1] if a.startswith("@")]
                for method in [s for s in mod.symbols.values() if s.parent == cls.name and s.kind == "method"]:
                    for name, args, _ in method.decorators:
                        verb = NEST_ROUTE_DECORATORS.get(name)
                        if verb is None:
                            continue
                        path = next((a for a in args if not a.startswith("@")), "")
                        guards = class_guards + [a[1:] for d in method.decorators if d[0] == "UseGuards" for a in d[1] if a.startswith("@")]
                        self.routes.append(
                            _Route(
                                id=stable_node_id(self.pid, "ts-endpoint", mod.rel, str(method.start), verb, path),
                                module=mod, verb=verb, path=_join(global_prefix, prefix, path),
                                line=method.start, end_line=method.end, handlers=[], framework="nestjs",
                                handler_id=method.id, guards=guards, prefix_mode="absolute",
                            )
                        )

    def _next_routes(self) -> None:
        for mod in self.mods.values():
            parts = mod.rel.split("/")
            stem = posixpath.splitext(parts[-1])[0]
            if "pages" in parts and len(parts) > parts.index("pages") + 1 and parts[parts.index("pages") + 1] == "api":
                idx = parts.index("pages")
                segs = [*parts[idx + 1 : -1], stem]
                if segs[-1] == "index":
                    segs = segs[:-1]
                handler = self._export(mod, "default")
                self.routes.append(
                    _Route(
                        id=stable_node_id(self.pid, "ts-endpoint", mod.rel, "next-api"), module=mod, verb="ANY",
                        path="/" + "/".join(segs), line=handler[1].start if handler else 1,
                        end_line=handler[1].end if handler else mod.lines, handlers=[], framework="nextjs",
                        handler_id=handler[1].id if handler else None, prefix_mode="absolute",
                    )
                )
                self.frameworks.add("nextjs")
            elif stem == "route" and "app" in parts:
                idx = len(parts) - 1 - parts[::-1].index("app")
                segs = [p for p in parts[idx + 1 : -1] if not (p.startswith("(") and p.endswith(")")) and not p.startswith("@")]
                for verb in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    sym = mod.symbols.get(verb)
                    if sym is None:
                        continue
                    self.routes.append(
                        _Route(
                            id=stable_node_id(self.pid, "ts-endpoint", mod.rel, verb), module=mod, verb=verb,
                            path="/" + "/".join(segs), line=sym.start, end_line=sym.end, handlers=[],
                            framework="nextjs", handler_id=sym.id, prefix_mode="absolute",
                        )
                    )
                    self.frameworks.add("nextjs")
            elif (stem == "page" and "app" in parts) or ("pages" in parts and mod.role == "pages" and "api" not in parts):
                default = self._export(mod, "default")
                if default is None:
                    continue
                if stem == "page":
                    idx = len(parts) - 1 - parts[::-1].index("app")
                    segs = [p for p in parts[idx + 1 : -1] if not (p.startswith("(") and p.endswith(")"))]
                else:
                    idx = parts.index("pages")
                    segs = [*parts[idx + 1 : -1], stem]
                    if segs and segs[-1] == "index":
                        segs = segs[:-1]
                if stem == "page" or "nextjs" in self.frameworks:
                    self._mark_page(default[1], "/" + "/".join(segs))

    def _mark_page(self, sym: _Sym, route: str) -> None:
        node = self.nodes.get(sym.id)
        if node is None:
            return
        node.properties.setdefault("routes", [])
        if route not in node.properties["routes"]:
            node.properties["routes"].append(route)
        node.properties["route"] = node.properties["routes"][0]
        node.properties["role"] = "pages"
        node.properties["layer"] = "ui"

    def _emit_page_routes(self) -> None:
        for mod in self.mods.values():
            for path, ref, _ in mod.page_routes:
                if not ref:
                    continue
                target = self._resolve(mod, ref)
                if target is not None and target.is_component:
                    self._mark_page(target, path if path.startswith("/") else "/" + path)
                    self.frameworks.add("react-router")

    def _module_prefixes(self) -> dict[str, list[str]]:
        """Express mount prefixes per module: app.use('/api', router) applied to the router's module."""
        parents: dict[str, list[tuple[str, str]]] = {}
        for mod in self.mods.values():
            for prefix, (kind, value), _ in mod.mounts:
                target_rel: str | None = None
                if kind == "spec":
                    target_rel = mod.resolved.get(value) or self._resolve_spec(mod, value)
                else:
                    binding = mod.bindings.get(value)
                    if binding is not None and binding[0] in ("import", "require", "namespace"):
                        target_rel = mod.resolved.get(binding[1])
                if target_rel and target_rel != mod.rel:
                    parents.setdefault(target_rel, []).append((mod.rel, prefix))

        memo: dict[str, list[str]] = {}

        def prefixes(rel: str, depth: int = 0) -> list[str]:
            if rel in memo:
                return memo[rel]
            if rel not in parents or depth > 6:
                return [""]
            out: list[str] = []
            for parent_rel, prefix in parents[rel]:
                for base in prefixes(parent_rel, depth + 1):
                    out.append(_join(base, prefix))
            memo[rel] = list(dict.fromkeys(out)) or [""]
            return memo[rel]

        return {rel: prefixes(rel) for rel in self.mods}

    def _emit_routes(self) -> None:
        mod_prefixes = self._module_prefixes()
        for route in self.routes:
            mod = route.module
            paths = [route.path] if route.prefix_mode == "absolute" else [_join(p, route.path) for p in mod_prefixes.get(mod.rel, [""])]
            handler_ids: list[str] = []
            for h in route.handlers:
                target = self._resolve(mod, _callee_text(h))
                if target is not None:
                    handler_ids.append(target.id)
            main_handler = route.handler_id or (handler_ids[-1] if handler_ids else None)
            middleware = handler_ids[:-1] if not route.handler_id else []
            for i, path in enumerate(paths):
                eid = route.id if i == 0 else stable_node_id(self.pid, "ts-endpoint-alias", route.id, path)
                methods = [] if route.verb == "ANY" else [route.verb]
                props: dict[str, Any] = {
                    "route": path,
                    "methods": methods,
                    "role": "urls",
                    "layer": "api",
                    "framework": route.framework,
                    "language": "typescript",
                }
                if main_handler and main_handler in self.nodes:
                    props["handler"] = self.nodes[main_handler].name
                self.nodes[eid] = NodeRecord(
                    id=eid, project_id=self.pid, node_type=NodeType.ENDPOINT, name=path,
                    qualified_name=f"{mod.rel}:{route.verb} {path}", source_path=mod.rel,
                    start_line=route.line, end_line=route.end_line, extractor=f"{route.framework}.routes",
                    confidence=0.9 if main_handler or route.handlers == [] else 0.7, properties=props,
                )
                self._edge(EdgeType.CONTAINS, mod.id, eid, rel=mod.rel, confidence=1.0)
                if main_handler:
                    self._edge(EdgeType.ROUTES_TO, eid, main_handler, rel=mod.rel, line=route.line, confidence=0.9)
                    self._edge(EdgeType.HANDLES, main_handler, eid, rel=mod.rel, line=route.line, confidence=0.9)
                    handler = self.nodes.get(main_handler)
                    if handler is not None and handler.properties.get("role") not in ("views",):
                        handler.properties["role"] = "views"
                        handler.properties["layer"] = "api"
                for mw in middleware:
                    self._edge(EdgeType.DEPENDS_ON, eid, mw, rel=mod.rel, line=route.line, confidence=0.85, relation="middleware")
                    if mw in self.nodes:
                        self.nodes[mw].properties.update({"role": "middleware", "layer": "middleware"})
                for guard in route.guards:
                    hit = self._lookup(mod, guard)
                    if hit is not None:
                        self._edge(EdgeType.DEPENDS_ON, eid, hit[1].id, rel=mod.rel, line=route.line, confidence=0.85, relation="guard")

    # ----------------------------------------------------------------- enrich

    def _enrich(self) -> None:
        index = GraphIndex.build(self.nodes.values(), self.edges.values())
        out_names: dict[str, dict[str, list[str]]] = {}
        for e in index.edges:
            out_names.setdefault(e.source_id, {}).setdefault(e.edge_type.value, []).append(index.nodes[e.target_id].name)
        http_by_source: dict[str, list[HttpCall]] = {}
        for call in self.result.http_calls:
            http_by_source.setdefault(call.source_id, []).append(call)
        children: dict[str, list[NodeRecord]] = {}
        for e in index.edges:
            if e.edge_type == EdgeType.CONTAINS:
                children.setdefault(e.source_id, []).append(index.nodes[e.target_id])

        def uniq(names: list[str], n: int = 3) -> str:
            names = list(dict.fromkeys(names))
            more = f" +{len(names) - n}" if len(names) > n else ""
            return ", ".join(f"`{x}`" for x in names[:n]) + more

        for node in self.nodes.values():
            props = node.properties
            role = props.get("role")
            if node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.COMPONENT, NodeType.MODULE, NodeType.MODEL):
                lines = props.get("line_count", 0) if node.node_type == NodeType.MODULE else (
                    (node.end_line - node.start_line + 1) if node.start_line and node.end_line else 0
                )
                props["lines"] = lines
                props["complexity"] = classify_complexity(lines, index.fan_out(node.id))
            outs = out_names.get(node.id, {})
            http = http_by_source.get(node.id, [])
            tags: list[str] = [role] if role else []
            if node.node_type == NodeType.COMPONENT:
                tags.append("react")
            if http:
                tags.append("http-client")
            if role == "entry":
                tags.append("entry-point")
            if props.get("route") and node.node_type == NodeType.COMPONENT:
                tags.append("page")
            if props.get("methods"):
                tags.extend(m.lower() for m in props["methods"])
            if props.get("framework") and node.node_type == NodeType.ENDPOINT:
                tags.append(str(props["framework"]))
            if props.get("complexity") == "complex":
                tags.append("complex")

            summary: str | None = None
            requests = uniq([f"{c.method or 'GET'} {c.url}" for c in http]) if http else ""
            if node.node_type == NodeType.MODULE:
                kids = children.get(node.id, [])
                comps = sum(1 for k in kids if k.node_type == NodeType.COMPONENT)
                funcs = sum(1 for k in kids if k.node_type == NodeType.FUNCTION)
                classes = sum(1 for k in kids if k.node_type in (NodeType.CLASS, NodeType.MODEL))
                bits = [f"{n} {label}" for n, label in ((comps, "component(s)"), (classes, "class(es)"), (funcs, "function(s)")) if n]
                summary = ROLE_LABEL.get(role or "", "Module") + (f" with {', '.join(bits)}" if bits else "") + "."
            elif node.node_type == NodeType.PACKAGE:
                mods = sum(1 for k in children.get(node.id, []) if k.node_type == NodeType.MODULE)
                summary = f"Package `{node.name}` containing {mods} module(s)."
            elif node.node_type == NodeType.ENDPOINT:
                verbs = f" [{', '.join(props['methods'])}]" if props.get("methods") else ""
                summary = f"Routes `{props.get('route')}`{verbs} to `{props.get('handler') or 'an inline handler'}`."
            elif node.node_type == NodeType.COMPONENT:
                parts = []
                if props.get("route"):
                    parts.append(f"page at `{props['route']}`")
                if outs.get("RENDERS"):
                    parts.append(f"renders {uniq(outs['RENDERS'])}")
                if requests:
                    parts.append(f"requests {requests}")
                if outs.get("CALLS") and len(parts) < 2:
                    parts.append(f"calls {uniq(outs['CALLS'])}")
                summary = "React component" + (": " + "; ".join(parts) if parts else "") + "."
            elif node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.MODEL):
                parts = []
                if requests:
                    parts.append(f"requests {requests}")
                if outs.get("INJECTS"):
                    parts.append(f"injects {uniq(outs['INJECTS'])}")
                if outs.get("CALLS"):
                    parts.append(f"calls {uniq(outs['CALLS'])}")
                label = {"hooks": "React hook", "views": "Request handler", "services": "Service", "middleware": "Middleware",
                         "permissions": "Guard", "api-client": "API client", "stores": "State store", "models": "Data model"}.get(
                    role or "", "Class" if node.node_type == NodeType.CLASS else "Function")
                summary = label + (": " + "; ".join(parts[:2]) if parts else "") + "."
            elif node.node_type == NodeType.EXTERNAL_SERVICE:
                users = [index.nodes[e.source_id].name for e in index.incoming.get(node.id, [])]
                summary = f"{str(props.get('kind', 'external')).title()} dependency used by {uniq(users) or 'the project'}."
            if summary:
                props["summary"] = summary
            props["tags"] = list(dict.fromkeys(t for t in tags if t))
            if props.get("npm_name") is None:
                props.pop("npm_name", None)


def _join(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)
