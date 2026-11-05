"""Django project analysis: files -> architecture graph.

Pipeline: discover + parse every module, build a project-wide symbol table, then
derive nodes (packages, modules, classes, functions, models, fields, endpoints,
middleware, external services) and resolved edges (imports, calls, routing, ORM
access, foreign keys, signals, settings wiring). Every node carries a role,
architectural layer, complexity, summary, and tags so the UI and AI can reason
about it without re-reading source.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ci_core.insights import GraphIndex, classify_complexity
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_parsers import (
    ParseResult,
    SymbolInfo,
    dotted_name,
    file_sha256,
    list_python_files,
    parse_python_file,
    stable_node_id,
    structural_fingerprint,
)

from ci_adapters_django.conf import (
    SettingsInfo,
    UrlEntry,
    expand_routes,
    extract_settings,
    extract_url_entries,
)
from ci_adapters_django.roles import (
    BASE_MODEL_NAMES,
    EXTERNAL_SDKS,
    HTTP_METHODS,
    ROLE_LABEL,
    VIEWSET_ACTIONS,
    WRITE_ORM_METHODS,
    class_role,
    classify_module,
    layer_for_role,
)

ADAPTER_VERSION = "3"

RELATION_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}
FIELD_KWARGS = ("max_length", "null", "blank", "unique", "primary_key", "db_index", "related_name", "on_delete")
MIDDLEWARE_METHODS = {"__call__", "process_request", "process_response", "process_view", "process_exception"}
SIGNAL_NAMES = {"pre_save", "post_save", "pre_delete", "post_delete", "m2m_changed", "pre_init", "post_init"}

# FastAPI / Flask / Starlette / django-ninja style decorator routing
WEB_APP_FACTORIES = {
    "FastAPI": "fastapi",
    "APIRouter": "fastapi",
    "Flask": "flask",
    "Blueprint": "flask",
    "Starlette": "starlette",
    "NinjaAPI": "django-ninja",
    "Router": "django-ninja",
}
ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options", "route", "api_route", "websocket"}
ROUTER_NAME_HINTS = ("app", "router", "api", "bp", "blueprint", "routes")
MOUNT_METHODS = {"include_router", "register_blueprint", "add_router"}
DI_FUNCTIONS = {"Depends", "Security"}

# SQLAlchemy / SQLModel
SQLA_COLUMN_FUNCS = {"Column", "mapped_column", "relationship", "Field"}
SQLA_READ_FUNCS = {"query", "select", "get", "get_one", "scalars", "scalar"}
SQLA_WRITE_FUNCS = {"delete", "update", "insert", "merge", "add", "add_all", "bulk_save_objects"}


@dataclass
class DjangoAnalysisResult:
    nodes: list[NodeRecord] = field(default_factory=list)
    edges: list[EdgeRecord] = field(default_factory=list)
    installed_apps: list[str] = field(default_factory=list)
    is_django: bool = False
    warnings: list[str] = field(default_factory=list)
    root_urlconf: str | None = None
    middleware: list[str] = field(default_factory=list)
    # rel path -> {"sha": content hash, "structural": shape hash, "role": role, "lines": n}
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)


def detect_django(root: Path) -> bool:
    if (root / "manage.py").exists():
        return True
    for path in list_python_files(root):
        if path.name == "manage.py":
            return True
        if path.name == "settings.py" or path.parent.name == "settings":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "INSTALLED_APPS" in text and "django" in text.lower():
                return True
    return False


_NOT_PLURAL = {"Middleware", "Project settings", "Business logic", "Admin configuration", "App configuration"}


def _singular(label: str) -> str:
    if label == "Utilities":
        return "Utility"
    if label in _NOT_PLURAL or not label.endswith("s") or label.endswith("ss"):
        return label
    return label[:-1]


def analyze_django_project(
    project_id: str, root: Path, files: list[Path] | None = None
) -> DjangoAnalysisResult:
    """Analyse the Python code under `root` (Django-aware; also FastAPI, Flask, SQLAlchemy).

    `files` restricts analysis to those paths (defaults to every `.py` file under `root`).
    """
    analyzer = _Analyzer(project_id, root, files)
    return analyzer.run()


# --------------------------------------------------------------------------------------


@dataclass
class _Module:
    rel: str
    name: str
    pr: ParseResult
    role: str
    is_package: bool
    node_id: str = ""


class _Analyzer:
    def __init__(self, project_id: str, root: Path, files: list[Path] | None = None):
        self.pid = project_id
        self.root = root
        self.files = files
        self.frameworks: set[str] = set()
        self.tablenames: dict[str, str] = {}  # sqlalchemy __tablename__ -> model qn
        self.web_apps: dict[tuple[str, str], dict[str, Any]] = {}
        self.web_mounts: dict[tuple[str, str], list[tuple[tuple[str, str] | None, str]]] = {}
        self.nodes: dict[str, NodeRecord] = {}
        self.edges: dict[str, EdgeRecord] = {}
        self.modules: dict[str, _Module] = {}  # module name -> module
        self.symbols: dict[str, str] = {}  # qualified name -> node id
        self.sym_info: dict[str, SymbolInfo] = {}
        self.sym_module: dict[str, _Module] = {}
        self.class_bases: dict[str, list[str]] = {}
        self.class_methods: dict[str, list[SymbolInfo]] = {}
        self.model_qns: set[str] = set()
        self.settings: list[SettingsInfo] = []
        self.packages: dict[str, str] = {}  # package module name -> node id
        self.result = DjangoAnalysisResult()
        self.project_node_id = stable_node_id(project_id, "project")

    # ----------------------------------------------------------------- helpers

    def _add_node(self, node: NodeRecord) -> NodeRecord:
        self.nodes[node.id] = node
        return node

    def _edge(
        self,
        edge_type: EdgeType,
        src: str,
        tgt: str,
        *,
        rel: str | None,
        line: int | None = None,
        extractor: str = "django.adapter",
        confidence: float = 0.9,
        **props: Any,
    ) -> None:
        if src == tgt or src not in self.nodes or tgt not in self.nodes:
            return
        eid = stable_node_id(self.pid, "edge", edge_type.value, src, tgt)
        existing = self.edges.get(eid)
        if existing:
            existing.properties["count"] = existing.properties.get("count", 1) + 1
            existing.confidence = max(existing.confidence, confidence)
            for k, v in props.items():
                existing.properties.setdefault(k, v)
            return
        self.edges[eid] = EdgeRecord(
            id=eid,
            project_id=self.pid,
            edge_type=edge_type,
            source_id=src,
            target_id=tgt,
            source_path=rel,
            start_line=line,
            extractor=extractor,
            confidence=confidence,
            properties={"count": 1, **props},
        )

    # --------------------------------------------------------------------- run

    def run(self) -> DjangoAnalysisResult:
        res = self.result
        res.is_django = detect_django(self.root)
        self._load_modules()
        self._load_settings()
        self._build_packages()
        self._build_modules_and_symbols()
        self._build_model_fields()
        self._link_imports()
        self._link_calls()
        self._link_class_attrs()
        self._link_decorators()
        self._link_settings()
        self._build_endpoints()
        self._build_decorator_endpoints()
        self._link_dependency_injection()
        self._enrich()
        res.nodes = list(self.nodes.values())
        res.edges = list(self.edges.values())
        if res.is_django:
            self.frameworks.add("django")
        res.frameworks = sorted(self.frameworks)
        res.stats = {
            "files": len(self.modules),
            "nodes": len(res.nodes),
            "edges": len(res.edges),
            "endpoints": sum(1 for n in res.nodes if n.node_type == NodeType.ENDPOINT),
            "models": sum(1 for n in res.nodes if n.node_type == NodeType.MODEL and not n.properties.get("inferred")),
        }
        return res

    # --------------------------------------------------------------- discovery

    def _source_roots(self, files: list[Path]) -> list[Path]:
        """Import roots: the repo, `src/` layouts, Python project dirs, and Django `manage.py` dirs.

        Deepest roots win, so `pkg/src/mylib/x.py` is module `mylib.x` (what imports use)."""
        roots = {self.root}
        if (self.root / "src").is_dir():
            roots.add(self.root / "src")
        checked: set[Path] = set()
        markers = ("pyproject.toml", "setup.py", "setup.cfg")
        for f in files:
            if f.name == "manage.py":
                roots.add(f.parent)
            for parent in f.parents:
                if parent in checked or parent == self.root:
                    break
                checked.add(parent)
                if parent.name == "src":
                    roots.add(parent)
                elif any((parent / m).is_file() for m in markers):
                    roots.add(parent)
                    if (parent / "src").is_dir():
                        roots.add(parent / "src")
        return sorted(roots, key=lambda p: len(p.parts), reverse=True)

    def _module_name(self, source_roots: list[Path], file: Path) -> str:
        for sr in source_roots:
            try:
                rel = file.relative_to(sr).with_suffix("")
            except ValueError:
                continue
            parts = list(rel.parts)
            if parts and parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(parts) or sr.name
        return file.stem

    def _load_modules(self) -> None:
        files = sorted(self.files) if self.files is not None else list_python_files(self.root)
        source_roots = self._source_roots(files)
        for f in files:
            rel = f.relative_to(self.root).as_posix()
            name = self._module_name(source_roots, f)
            if name in self.modules:  # duplicate module names across roots: first wins
                name = f"{name}@{rel}"
            role = classify_module(rel)
            if f.name == "__init__.py":
                role = "apps" if role == "services" else role
            pr = parse_python_file(self.root, f, module_name=name)
            if pr.error:
                self.result.warnings.append(f"{rel}: {pr.error}")
            mod = _Module(rel=rel, name=name, pr=pr, role=role, is_package=f.name == "__init__.py")
            mod.node_id = stable_node_id(self.pid, "module", rel)
            self.modules[name] = mod
            self.result.files[rel] = {
                "sha": file_sha256(f),
                "structural": structural_fingerprint(pr),
                "role": role,
                "lines": pr.line_count,
                "language": "python",
            }

    def _load_settings(self) -> None:
        for mod in self.modules.values():
            if mod.role != "settings":
                continue
            info = extract_settings(mod.pr, mod.rel)
            if info:
                self.settings.append(info)
        res = self.result
        for s in self.settings:
            res.installed_apps.extend(s.installed_apps)
            res.middleware.extend(s.middleware)
            res.root_urlconf = res.root_urlconf or s.root_urlconf
        res.installed_apps = list(dict.fromkeys(res.installed_apps))
        res.middleware = list(dict.fromkeys(res.middleware))

    # ---------------------------------------------------------------- packages

    def _known_dirs(self) -> set[str]:
        dirs: set[str] = set()
        for mod in self.modules.values():
            parts = mod.name.split(".")
            upto = len(parts) if mod.is_package else len(parts) - 1
            for i in range(1, upto + 1):
                dirs.add(".".join(parts[:i]))
        return dirs

    def _app_package(self, app: str, known_dirs: set[str]) -> str | None:
        parts = app.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in known_dirs:
                return cand
        return None

    def _build_packages(self) -> None:
        known = self._known_dirs()
        local: dict[str, str] = {}  # package -> origin
        for app in self.result.installed_apps:
            pkg = self._app_package(app, known)
            if pkg:
                local[pkg] = "installed_apps"
        markers = {"models", "views", "apps", "urls", "admin", "serializers", "settings"}
        for mod in self.modules.values():
            leaf = mod.name.rsplit(".", 1)[-1]
            if leaf in markers and "." in mod.name:
                pkg = mod.name.rsplit(".", 1)[0]
                local.setdefault(pkg, "layout")
            elif mod.role == "settings" and "." in mod.name:
                local.setdefault(mod.name.rsplit(".", 1)[0], "layout")
        # Non-Django layouts (FastAPI services, libraries): every top-level Python package.
        for mod in self.modules.values():
            top = mod.name.split(".")[0]
            if "." in mod.name and "@" not in mod.name and top in self.modules and self.modules[top].is_package:
                local.setdefault(top, "layout")

        project_name = self.root.name
        self._add_node(
            NodeRecord(
                id=self.project_node_id,
                project_id=self.pid,
                node_type=NodeType.PROJECT,
                name=project_name,
                extractor="django.adapter",
                properties={"framework": "django" if self.result.is_django else "python"},
            )
        )
        for pkg, origin in sorted(local.items()):
            nid = stable_node_id(self.pid, "package", pkg)
            self.packages[pkg] = nid
            rel_dir = pkg.replace(".", "/")
            self._add_node(
                NodeRecord(
                    id=nid,
                    project_id=self.pid,
                    node_type=NodeType.PACKAGE,
                    name=pkg.split(".")[-1],
                    qualified_name=pkg,
                    source_path=rel_dir,
                    extractor="django.installed_apps" if origin == "installed_apps" else "django.layout",
                    confidence=0.95 if origin == "installed_apps" else 0.8,
                    properties={"installed": origin == "installed_apps"},
                )
            )
        for pkg, nid in self.packages.items():
            parent = self._owning_package(pkg, exclude_self=True)
            self._edge(
                EdgeType.CONTAINS,
                self.packages[parent] if parent else self.project_node_id,
                nid,
                rel=None,
                extractor="django.layout",
                confidence=1.0,
            )

    def _owning_package(self, module_name: str, exclude_self: bool = False) -> str | None:
        best: str | None = None
        for pkg in self.packages:
            if module_name == pkg and not exclude_self:
                return pkg
            if module_name.startswith(pkg + ".") and (best is None or len(pkg) > len(best)):
                best = pkg
        return best

    # ---------------------------------------------------- modules and symbols

    def _build_modules_and_symbols(self) -> None:
        settings_mw = set(self.result.middleware)
        for mod in self.modules.values():
            pr = mod.pr
            is_migration = mod.role == "migration"
            layer = layer_for_role(mod.role)
            self._add_node(
                NodeRecord(
                    id=mod.node_id,
                    project_id=self.pid,
                    node_type=NodeType.MIGRATION if is_migration else NodeType.MODULE,
                    name=mod.rel[:-3],
                    qualified_name=mod.name,
                    source_path=mod.rel,
                    start_line=1,
                    end_line=pr.line_count,
                    extractor="python.parser",
                    properties={
                        "role": mod.role,
                        "layer": layer,
                        "line_count": pr.line_count,
                        "docstring": pr.docstring,
                        "parse_error": pr.error,
                    },
                )
            )
            owner = self._owning_package(mod.name)
            self._edge(
                EdgeType.CONTAINS,
                self.packages[owner] if owner else self.project_node_id,
                mod.node_id,
                rel=mod.rel,
                extractor="django.layout",
                confidence=1.0,
            )
            if is_migration:
                continue  # migrations contribute one node; their internals are generated noise

            for sym in pr.symbols:
                self.symbols[sym.qualified_name] = stable_node_id(self.pid, "symbol", sym.qualified_name)
                self.sym_info[sym.qualified_name] = sym
                self.sym_module[sym.qualified_name] = mod
                if sym.kind == "method" and sym.parent_class:
                    self.class_methods.setdefault(sym.parent_class, []).append(sym)

        # classes first: model/middleware classification needs the bases resolved
        self._resolve_class_bases()
        for mod in self.modules.values():
            if mod.role == "migration":
                continue
            for sym in mod.pr.symbols:
                self._emit_symbol(mod, sym, settings_mw)

    def _resolve_class_bases(self) -> None:
        for qn, sym in self.sym_info.items():
            if sym.kind != "class":
                continue
            mod = self.sym_module[qn]
            resolved: list[str] = []
            for base in sym.bases:
                hit = self.resolve(mod.pr, base)
                if hit and not hit[1] and self.sym_info.get(hit[0], None) and self.sym_info[hit[0]].kind == "class":
                    resolved.append(hit[0])
            self.class_bases[qn] = resolved
        # model detection to a fixed point (subclass of a project model is a model)
        changed = True
        while changed:
            changed = False
            for qn, sym in self.sym_info.items():
                if sym.kind != "class" or qn in self.model_qns:
                    continue
                direct = any(b.split(".")[-1] in BASE_MODEL_NAMES for b in sym.bases)
                inherited = any(b in self.model_qns for b in self.class_bases.get(qn, []))
                table = _sqlalchemy_table(sym)
                if table:
                    self.tablenames[table] = qn
                    self.frameworks.add("sqlalchemy")
                if direct or inherited or table:
                    self.model_qns.add(qn)
                    changed = True

    def _emit_symbol(self, mod: _Module, sym: SymbolInfo, settings_mw: set[str]) -> None:
        sid = self.symbols[sym.qualified_name]
        role = mod.role
        node_type = NodeType.CLASS if sym.kind == "class" else NodeType.FUNCTION
        props: dict[str, Any] = {"kind": sym.kind, "docstring": sym.docstring}
        if sym.bases:
            props["bases"] = sym.bases

        if sym.kind == "class":
            role = class_role(sym.bases, role)
            method_names = {m.name for m in self.class_methods.get(sym.qualified_name, [])}
            if sym.qualified_name in self.model_qns:
                node_type = NodeType.MODEL
                role = "models"
                props["abstract"] = bool(sym.meta_flags.get("abstract"))
                app_label = (self._owning_package(mod.name) or mod.name).split(".")[-1]
                props["app_label"] = app_label
                props["table_guess"] = f"{app_label}_{sym.name.lower()}"
                table = _sqlalchemy_table(sym)
                if table:
                    props["table"] = table
                    props["orm"] = "sqlalchemy"
            elif sym.qualified_name in settings_mw or (
                role == "middleware"
                and (sym.name.endswith("Middleware") or bool(method_names & MIDDLEWARE_METHODS))
            ):
                node_type = NodeType.MIDDLEWARE
                role = "middleware"
        else:
            if sym.parent_class:
                parent_role = self.nodes.get(self.symbols.get(sym.parent_class, ""), None)
                if parent_role is not None:
                    role = parent_role.properties.get("role", role)
                props["parent_class"] = sym.parent_class
            if any(d.name.split(".")[-1] == "receiver" for d in sym.decorators):
                role = "signals"
            if mod.role in ("tasks",) or any(d.name.split(".")[-1] in ("shared_task", "task") for d in sym.decorators):
                role = "tasks"

        props["role"] = role
        props["layer"] = layer_for_role(role)
        self._add_node(
            NodeRecord(
                id=sid,
                project_id=self.pid,
                node_type=node_type,
                name=sym.name if sym.kind != "method" else f"{sym.qualified_name.split('.')[-2]}.{sym.name}",
                qualified_name=sym.qualified_name,
                source_path=mod.rel,
                start_line=sym.start_line,
                end_line=sym.end_line,
                extractor="django.models" if node_type == NodeType.MODEL else "python.parser",
                confidence=0.95 if node_type != NodeType.CLASS else 1.0,
                properties=props,
            )
        )
        parent_id = self.symbols.get(sym.parent_class) if sym.parent_class else mod.node_id
        self._edge(
            EdgeType.CONTAINS, parent_id or mod.node_id, sid, rel=mod.rel, extractor="python.parser", confidence=1.0
        )

    # ------------------------------------------------------------- resolution

    def _follow(self, cand: str) -> str:
        """Follow package re-exports (`from .views import X` inside __init__.py)."""
        for _ in range(3):
            if cand in self.symbols or "." not in cand:
                return cand
            mod_name, _, name = cand.rpartition(".")
            mod = self.modules.get(mod_name)
            if mod and name in mod.pr.aliases and mod.pr.aliases[name] != cand:
                cand = mod.pr.aliases[name]
            else:
                return cand
        return cand

    def resolve(self, pr: ParseResult, dotted: str, class_qn: str | None = None) -> tuple[str, list[str]] | None:
        """Resolve a dotted reference used in `pr` to (qualified symbol name, unresolved suffix)."""
        parts = dotted.split(".")
        head = parts[0]
        if head in ("self", "cls"):
            if class_qn and len(parts) >= 2:
                member = self.find_member(class_qn, parts[1])
                if member:
                    return member, parts[2:]
            return None
        bases: list[str] = []
        local = f"{pr.module_name}.{head}"
        if local in self.symbols:
            bases.append(local)
        if head in pr.aliases:
            bases.append(pr.aliases[head])
        for base in bases:
            for k in range(len(parts), 0, -1):
                cand = self._follow(".".join([base, *parts[1:k]]))
                if cand in self.symbols:
                    return cand, parts[k:]
        return None

    def resolve_module(self, pr: ParseResult, dotted: str) -> str | None:
        if dotted in self.modules:
            return dotted
        head, _, rest = dotted.partition(".")
        target = pr.aliases.get(head)
        if target:
            full = f"{target}.{rest}" if rest else target
            if full in self.modules:
                return full
        return None

    def find_member(self, class_qn: str, name: str, depth: int = 0) -> str | None:
        cand = f"{class_qn}.{name}"
        if cand in self.symbols:
            return cand
        if depth > 5:
            return None
        for base in self.class_bases.get(class_qn, []):
            hit = self.find_member(base, name, depth + 1)
            if hit:
                return hit
        return None

    def _node(self, qn: str) -> NodeRecord | None:
        return self.nodes.get(self.symbols.get(qn, ""))

    # ------------------------------------------------------------------ models

    def _model_lookup(self, name: str, label: str | None, near_module: str) -> str | None:
        candidates = [qn for qn in self.model_qns if qn.split(".")[-1] == name]
        if label:
            labelled = [
                qn
                for qn in candidates
                if (self._owning_package(self.sym_module[qn].name) or "").split(".")[-1] == label
                or self.sym_module[qn].name.split(".")[0] == label
            ]
            if labelled:
                return sorted(labelled)[0]
            return None
        near = self._owning_package(near_module)
        for qn in sorted(candidates):
            if near and self.sym_module[qn].name.startswith(near):
                return qn
        return sorted(candidates)[0] if len(candidates) == 1 else None

    def _stub_model(self, label: str, name: str) -> str:
        sid = stable_node_id(self.pid, "model-stub", label, name)
        if sid not in self.nodes:
            self._add_node(
                NodeRecord(
                    id=sid,
                    project_id=self.pid,
                    node_type=NodeType.MODEL,
                    name=name,
                    qualified_name=f"{label}.{name}",
                    extractor="django.models",
                    confidence=0.5,
                    properties={"inferred": True, "external": True, "layer": "data", "role": "models", "app_label": label},
                )
            )
        return sid

    def _relation_target(self, value: ast.Call, owner_qn: str, mod: _Module) -> str | None:
        arg: ast.AST | None = value.args[0] if value.args else None
        if arg is None:
            arg = next((kw.value for kw in value.keywords if kw.arg == "to"), None)
        if arg is None:
            return None
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            text = arg.value
            if text == "self":
                return self.symbols[owner_qn]
            label, _, name = text.rpartition(".")
            qn = self._model_lookup(name, label or None, mod.name)
            if qn:
                return self.symbols[qn]
            return self._stub_model(label or "unknown", name) if label else None
        dotted = dotted_name(arg)
        if not dotted:
            return None
        if dotted.endswith("AUTH_USER_MODEL"):
            setting = next((s.auth_user_model for s in self.settings if s.auth_user_model), None)
            if setting:
                label, _, name = setting.rpartition(".")
                qn = self._model_lookup(name, label or None, mod.name)
                return self.symbols[qn] if qn else self._stub_model(label or "auth", name)
            return self._stub_model("auth", "User")
        hit = self.resolve(mod.pr, dotted)
        if hit and hit[0] in self.model_qns and not hit[1]:
            return self.symbols[hit[0]]
        return None

    def _build_model_fields(self) -> None:
        for qn in sorted(self.model_qns):
            sym = self.sym_info[qn]
            mod = self.sym_module[qn]
            model_id = self.symbols[qn]
            if not isinstance(sym.node, ast.ClassDef):
                continue
            order = 0
            for item in sym.node.body:
                if isinstance(item, ast.Assign) and len(item.targets) == 1 and isinstance(item.targets[0], ast.Name):
                    fname, value = item.targets[0].id, item.value
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.value is not None:
                    fname, value = item.target.id, item.value
                else:
                    continue
                if not isinstance(value, ast.Call):
                    continue
                callee = dotted_name(value.func) or ""
                ftype = callee.split(".")[-1]
                if ftype in SQLA_COLUMN_FUNCS and ftype != "Field":
                    self._add_sqlalchemy_field(qn, mod, model_id, fname, item, value, ftype, order + 1)
                    order += 1
                    continue
                if not (ftype.endswith("Field") or ftype in RELATION_FIELDS or ftype in ("GenericForeignKey", "GenericRelation")):
                    continue
                order += 1
                props: dict[str, Any] = {"field_type": ftype, "order": order, "layer": "data", "role": "models"}
                for kw in value.keywords:
                    if kw.arg in FIELD_KWARGS:
                        if isinstance(kw.value, ast.Constant):
                            props[kw.arg] = kw.value.value
                        else:
                            props[kw.arg] = dotted_name(kw.value) or "…"
                fid = stable_node_id(self.pid, "field", model_id, fname)
                target_id = self._relation_target(value, qn, mod) if ftype in RELATION_FIELDS else None
                if target_id:
                    props["relation_to"] = self.nodes[target_id].name
                    props["relation"] = {"ForeignKey": "many-to-one", "OneToOneField": "one-to-one", "ManyToManyField": "many-to-many"}[ftype]
                props["summary"] = f"{ftype}" + (f" → {props['relation_to']}" if target_id else "")
                self._add_node(
                    NodeRecord(
                        id=fid,
                        project_id=self.pid,
                        node_type=NodeType.FIELD,
                        name=fname,
                        qualified_name=f"{qn}.{fname}",
                        source_path=mod.rel,
                        start_line=item.lineno,
                        end_line=item.end_lineno or item.lineno,
                        extractor="django.models",
                        confidence=0.9,
                        properties=props,
                    )
                )
                self._edge(EdgeType.CONTAINS, model_id, fid, rel=mod.rel, extractor="django.models", confidence=1.0)
                if target_id:
                    self._edge(
                        EdgeType.FK_TO,
                        model_id,
                        target_id,
                        rel=mod.rel,
                        line=item.lineno,
                        extractor="django.models",
                        confidence=0.9,
                        field=fname,
                        relation=props["relation"],
                    )

    # ----------------------------------------------------------------- imports

    def _link_imports(self) -> None:
        for mod in self.modules.values():
            if mod.role == "migration":
                continue
            external_seen: set[str] = set()
            for imp in mod.pr.imports:
                targets: list[str] = []
                submodules = [
                    f"{imp.module}.{name}" if imp.module else name
                    for name in imp.names
                    if (f"{imp.module}.{name}" if imp.module else name) in self.modules
                ]
                targets.extend(submodules)
                if imp.module in self.modules and (not submodules or len(submodules) < len(imp.names)):
                    targets.append(imp.module)
                for alias_target in imp.aliases.values():  # `import shop.models as m`
                    if alias_target in self.modules:
                        targets.append(alias_target)
                if not targets and imp.module:
                    # re-export through a package __init__
                    for name in imp.names:
                        followed = self._follow(f"{imp.module}.{name}")
                        if followed in self.symbols:
                            targets.append(self.sym_module[followed].name)
                for t in dict.fromkeys(targets):
                    target_mod = self.modules[t]
                    self._edge(
                        EdgeType.IMPORTS,
                        mod.node_id,
                        target_mod.node_id,
                        rel=mod.rel,
                        line=imp.line,
                        extractor="python.parser",
                        confidence=0.95,
                        names=imp.names[:8],
                    )
                root_name = (imp.module or "").split(".")[0]
                if root_name in EXTERNAL_SDKS and root_name not in external_seen:
                    external_seen.add(root_name)
                    display, kind = EXTERNAL_SDKS[root_name]
                    svc = self._external_service(display, kind)
                    self._edge(
                        EdgeType.DEPENDS_ON,
                        mod.node_id,
                        svc,
                        rel=mod.rel,
                        line=imp.line,
                        extractor="python.parser",
                        confidence=0.9,
                        relation="uses",
                    )

    def _external_service(self, display: str, kind: str) -> str:
        sid = stable_node_id(self.pid, "external", display)
        if sid not in self.nodes:
            self._add_node(
                NodeRecord(
                    id=sid,
                    project_id=self.pid,
                    node_type=NodeType.EXTERNAL_SERVICE,
                    name=display,
                    extractor="python.parser",
                    confidence=0.9,
                    properties={"kind": kind, "layer": "external", "role": "external", "external": True},
                )
            )
        return sid

    # ------------------------------------------------------------------- calls

    def _link_calls(self) -> None:
        for mod in self.modules.values():
            if mod.role == "migration":
                continue
            pr = mod.pr
            for call in pr.calls:
                if call.caller == "<module>":
                    if mod.role == "urls":
                        continue  # routing is captured by endpoint nodes
                    src_id, class_qn = mod.node_id, None
                else:
                    caller_qn = f"{mod.name}.{call.caller}"
                    src_id = self.symbols.get(caller_qn)
                    if not src_id:
                        continue
                    info = self.sym_info[caller_qn]
                    class_qn = caller_qn if info.kind == "class" else info.parent_class

                tail = call.callee.split(".")[-1]
                if tail in ("get_object_or_404", "get_list_or_404") and call.args and call.args[0]:
                    hit = self.resolve(pr, call.args[0], class_qn)
                    if hit and hit[0] in self.model_qns:
                        self._edge(
                            EdgeType.READS_MODEL, src_id, self.symbols[hit[0]],
                            rel=mod.rel, line=call.line, extractor="django.orm", confidence=0.9,
                        )
                    continue
                if tail == "connect" and call.args and call.args[0]:
                    self._link_signal_connect(mod, call, src_id, class_qn)
                    continue
                if call.callee.endswith("site.register") and call.args and call.args[0]:
                    self._link_admin_register(mod, call, src_id, class_qn)
                    continue

                if tail in SQLA_READ_FUNCS or tail in SQLA_WRITE_FUNCS:
                    for arg in call.args:
                        arg_hit = self.resolve(pr, arg, class_qn) if arg else None
                        if arg_hit and not arg_hit[1] and arg_hit[0] in self.model_qns:
                            self._edge(
                                EdgeType.WRITES_MODEL if tail in SQLA_WRITE_FUNCS else EdgeType.READS_MODEL,
                                src_id, self.symbols[arg_hit[0]],
                                rel=mod.rel, line=call.line, extractor="sqlalchemy.orm", confidence=0.8,
                            )

                hit = self.resolve(pr, call.callee, class_qn)
                if not hit:
                    continue
                qn, rest = hit
                node = self._node(qn)
                if node is None:
                    continue
                if node.node_type == NodeType.MODEL and rest and rest[0] in ("objects", "_default_manager"):
                    writes = any(part in WRITE_ORM_METHODS for part in rest[1:])
                    self._edge(
                        EdgeType.WRITES_MODEL if writes else EdgeType.READS_MODEL,
                        src_id, node.id,
                        rel=mod.rel, line=call.line, extractor="django.orm", confidence=0.9,
                    )
                    continue
                target_id = node.id
                if rest and node.node_type in (NodeType.CLASS, NodeType.MODEL, NodeType.MIDDLEWARE):
                    member = self.find_member(qn, rest[0])
                    if member:
                        target_id = self.symbols[member]
                if node.node_type == NodeType.MODEL and not rest and call.caller != "<module>":
                    # instantiating a model in a handler implies persisting it
                    self._edge(
                        EdgeType.WRITES_MODEL, src_id, node.id,
                        rel=mod.rel, line=call.line, extractor="django.orm", confidence=0.6,
                    )
                self._edge(
                    EdgeType.CALLS, src_id, target_id,
                    rel=mod.rel, line=call.line, extractor="python.parser", confidence=0.85,
                )

    def _link_signal_connect(self, mod: _Module, call, src_id: str, class_qn: str | None) -> None:
        handler = self.resolve(mod.pr, call.args[0], class_qn)
        sender = call.kwargs.get("sender")
        sender_hit = self.resolve(mod.pr, sender, class_qn) if sender else None
        if not handler:
            return
        handler_id = self.symbols[handler[0]]
        signal = call.callee.rsplit(".", 1)[0].split(".")[-1]
        if handler_id in self.nodes:
            self.nodes[handler_id].properties["role"] = "signals"
            self.nodes[handler_id].properties["layer"] = "service"
            self.nodes[handler_id].properties["signal"] = signal
        if sender_hit and sender_hit[0] in self.model_qns:
            self._edge(
                EdgeType.SUBSCRIBES, handler_id, self.symbols[sender_hit[0]],
                rel=mod.rel, line=call.line, extractor="django.signals", confidence=0.9, signal=signal,
            )

    def _link_admin_register(self, mod: _Module, call, src_id: str, class_qn: str | None) -> None:
        model = self.resolve(mod.pr, call.args[0], class_qn)
        if not model or model[0] not in self.model_qns:
            return
        admin_cls = self.resolve(mod.pr, call.args[1], class_qn) if len(call.args) > 1 and call.args[1] else None
        source = self.symbols[admin_cls[0]] if admin_cls else src_id
        self._edge(
            EdgeType.DEPENDS_ON, source, self.symbols[model[0]],
            rel=mod.rel, line=call.line, extractor="django.admin", confidence=0.9, relation="admin",
        )

    # ------------------------------------------------- class attrs + decorators

    def _link_class_attrs(self) -> None:
        for qn, sym in self.sym_info.items():
            if sym.kind != "class":
                continue
            mod = self.sym_module[qn]
            cid = self.symbols[qn]
            node = self.nodes.get(cid)
            if node is None:
                continue
            for attr, ref in sym.attrs.items():
                if attr not in ("model", "serializer_class", "form_class", "queryset", "permission_classes"):
                    continue
                hit = self.resolve(mod.pr, ref)
                if not hit or hit[1]:
                    continue
                target = self._node(hit[0])
                if target is None:
                    continue
                if attr == "model" and target.node_type == NodeType.MODEL:
                    self._edge(
                        EdgeType.READS_MODEL, cid, target.id,
                        rel=mod.rel, line=sym.start_line, extractor="django.cbv", confidence=0.85,
                    )
                elif attr in ("serializer_class", "form_class"):
                    self._edge(
                        EdgeType.DEPENDS_ON, cid, target.id,
                        rel=mod.rel, line=sym.start_line, extractor="django.cbv", confidence=0.9, relation=attr,
                    )
            meta_model = sym.meta_attrs.get("model")
            if meta_model:
                hit = self.resolve(mod.pr, meta_model)
                if hit and hit[0] in self.model_qns and node.node_type != NodeType.MODEL:
                    relation = "serializes" if node.properties.get("role") == "serializers" else "binds"
                    self._edge(
                        EdgeType.DEPENDS_ON, cid, self.symbols[hit[0]],
                        rel=mod.rel, line=sym.start_line, extractor="django.meta", confidence=0.9, relation=relation,
                    )
            for base_qn in self.class_bases.get(qn, []):
                self._edge(
                    EdgeType.DEPENDS_ON, cid, self.symbols[base_qn],
                    rel=mod.rel, line=sym.start_line, extractor="python.parser", confidence=0.95, relation="inherits",
                )

    def _link_decorators(self) -> None:
        for qn, sym in self.sym_info.items():
            mod = self.sym_module[qn]
            sid = self.symbols[qn]
            for deco in sym.decorators:
                tail = deco.name.split(".")[-1]
                if tail == "receiver":
                    signal = deco.args[0].split(".")[-1] if deco.args and deco.args[0] else "signal"
                    node = self.nodes.get(sid)
                    if node:
                        node.properties.update({"role": "signals", "layer": "service", "signal": signal})
                    sender = deco.kwargs.get("sender")
                    hit = self.resolve(mod.pr, sender) if sender else None
                    if hit and hit[0] in self.model_qns:
                        self._edge(
                            EdgeType.SUBSCRIBES, sid, self.symbols[hit[0]],
                            rel=mod.rel, line=sym.start_line, extractor="django.signals", confidence=0.95, signal=signal,
                        )
                elif tail == "register" and deco.name.startswith("admin") and deco.args:
                    for arg in deco.args:
                        hit = self.resolve(mod.pr, arg) if arg else None
                        if hit and hit[0] in self.model_qns:
                            self._edge(
                                EdgeType.DEPENDS_ON, sid, self.symbols[hit[0]],
                                rel=mod.rel, line=sym.start_line, extractor="django.admin", confidence=0.95,
                                relation="admin",
                            )

    # ------------------------------------------------------- settings wiring

    def _link_settings(self) -> None:
        project_props = self.nodes[self.project_node_id].properties
        project_props["installed_apps"] = self.result.installed_apps
        project_props["middleware_chain"] = self.result.middleware
        project_props["root_urlconf"] = self.result.root_urlconf

        known_dirs = self._known_dirs()
        for s in self.settings:
            mod = self.modules.get(s.module)
            if not mod:
                continue
            for order, dotted in enumerate(s.middleware):
                if dotted in self.symbols and self.nodes[self.symbols[dotted]].node_type == NodeType.MIDDLEWARE:
                    target = self.nodes[self.symbols[dotted]]
                    target.properties["order"] = order
                    self._edge(
                        EdgeType.MIDDLEWARE, mod.node_id, target.id,
                        rel=mod.rel, extractor="django.settings", confidence=0.95, order=order,
                    )
            for app in s.installed_apps:
                if self._app_package(app, known_dirs):
                    continue
                if app.startswith("django.contrib") or app.startswith("django."):
                    continue
                root_name = app.split(".")[0]
                display, kind = EXTERNAL_SDKS.get(root_name, (app, "django-app"))
                svc = self._external_service(display, kind)
                self._edge(
                    EdgeType.DEPENDS_ON, mod.node_id, svc,
                    rel=mod.rel, extractor="django.settings", confidence=0.9, relation="installed_app",
                )
            node = self.nodes[mod.node_id]
            node.properties["settings"] = {
                "installed_apps": len(s.installed_apps),
                "middleware": len(s.middleware),
                "root_urlconf": s.root_urlconf,
            }

    # --------------------------------------------------------------- endpoints

    def _http_methods(self, qn: str) -> list[str]:
        sym = self.sym_info.get(qn)
        if sym is None:
            return []
        if sym.kind == "class":
            names = {m.name for m in self.class_methods.get(qn, [])}
            methods = [m.upper() for m in HTTP_METHODS if m in names]
            for action, verb in VIEWSET_ACTIONS.items():
                if action in names and verb not in methods:
                    methods.append(verb)
            if any(b.endswith("ModelViewSet") for b in sym.bases):
                methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
            elif any(b.endswith("ReadOnlyModelViewSet") for b in sym.bases):
                methods = ["GET"]
            return methods
        methods: list[str] = []
        for deco in sym.decorators:
            tail = deco.name.split(".")[-1]
            if tail in ("api_view", "require_http_methods", "action"):
                methods += [s.upper() for s in deco.strings if s.upper() in {m.upper() for m in HTTP_METHODS}]
            elif tail.startswith("require_") and tail[8:].upper() in {m.upper() for m in HTTP_METHODS}:
                methods.append(tail[8:].upper())
        return list(dict.fromkeys(methods))

    def _build_endpoints(self) -> None:
        entries: dict[str, list[UrlEntry]] = {}
        for mod in self.modules.values():
            if mod.role == "migration" or mod.pr.tree is None:
                continue
            if mod.role == "urls" or "urlpatterns" in mod.pr.source:
                found = extract_url_entries(mod.pr)
                if found:
                    entries[mod.name] = found

        def resolve_include(module: str, ref: str) -> str | None:
            return self.resolve_module(self.modules[module].pr, ref)

        for module_name, entry, full_route in expand_routes(entries, resolve_include, self.result.root_urlconf):
            mod = self.modules[module_name]
            eid = stable_node_id(self.pid, "endpoint", mod.rel, str(entry.line), full_route)
            props: dict[str, Any] = {
                "route": full_route,
                "segment": entry.route,
                "view_ref": entry.ref,
                "url_name": entry.name,
                "router": entry.router,
                "role": "urls",
                "layer": "api",
            }
            handler_qn: str | None = None
            hit = self.resolve(mod.pr, entry.ref) if entry.ref else None
            if hit:
                handler_qn = hit[0]
                methods = self._http_methods(handler_qn)
                if methods:
                    props["methods"] = methods
                props["handler"] = handler_qn
            self._add_node(
                NodeRecord(
                    id=eid,
                    project_id=self.pid,
                    node_type=NodeType.ENDPOINT,
                    name=full_route or "/",
                    qualified_name=f"{mod.name}:{full_route}",
                    source_path=mod.rel,
                    start_line=entry.line,
                    end_line=entry.end_line,
                    extractor="django.urls",
                    confidence=0.9 if handler_qn else 0.6,
                    properties=props,
                )
            )
            self._edge(EdgeType.CONTAINS, mod.node_id, eid, rel=mod.rel, extractor="django.urls", confidence=1.0)
            if handler_qn and handler_qn in self.symbols:
                view_id = self.symbols[handler_qn]
                self._edge(
                    EdgeType.ROUTES_TO, eid, view_id,
                    rel=mod.rel, line=entry.line, extractor="django.urls", confidence=0.95,
                )
                self._edge(
                    EdgeType.HANDLES, view_id, eid,
                    rel=mod.rel, line=entry.line, extractor="django.urls", confidence=0.95,
                )
                view_node = self.nodes[view_id]
                if view_node.properties.get("role") not in ("views",):
                    view_node.properties["role"] = "views"
                    view_node.properties["layer"] = "api"

    # --------------------------------------------- decorator routing (FastAPI/Flask)

    def _collect_web_apps(self) -> None:
        for mod in self.modules.values():
            tree = mod.pr.tree
            if mod.role == "migration" or tree is None:
                continue
            for stmt in tree.body:
                target, value = None, None
                if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                    target, value = stmt.targets[0].id, stmt.value
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    target, value = stmt.target.id, stmt.value
                if not target or not isinstance(value, ast.Call):
                    continue
                factory = (dotted_name(value.func) or "").split(".")[-1]
                if factory not in WEB_APP_FACTORIES:
                    continue
                framework = WEB_APP_FACTORIES[factory]
                if factory == "Router" and "ninja" not in str(mod.pr.aliases.get("Router", "")):
                    continue
                self.web_apps[(mod.name, target)] = {
                    "framework": framework,
                    "prefix": _kw_str(value, "prefix", "url_prefix") or "",
                    "line": stmt.lineno,
                    "factory": factory,
                }
                if factory in ("FastAPI", "Flask", "Starlette", "NinjaAPI"):
                    self.nodes[mod.node_id].properties["entry_point"] = True
        for mod in self.modules.values():
            tree = mod.pr.tree
            if mod.role == "migration" or tree is None:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr not in MOUNT_METHODS or not node.args:
                    continue
                child = self._web_ref(mod, dotted_name(node.args[0]))
                if child is None:
                    continue
                parent = self._web_ref(mod, dotted_name(node.func.value))
                self.web_mounts.setdefault(child, []).append((parent, _kw_str(node, "prefix", "url_prefix") or ""))

    def _web_ref(self, mod: _Module, dotted: str | None) -> tuple[str, str] | None:
        """Resolve `router`, `users.router`, or an imported name to a (module, variable) app key."""
        if not dotted:
            return None
        if (mod.name, dotted) in self.web_apps:
            return (mod.name, dotted)
        head, _, rest = dotted.partition(".")
        target = mod.pr.aliases.get(head)
        if not target:
            return None
        full = f"{target}.{rest}" if rest else target
        for _ in range(3):
            module_name, _, var = full.rpartition(".")
            if (module_name, var) in self.web_apps:
                return (module_name, var)
            owner = self.modules.get(module_name)
            if owner and var in owner.pr.aliases and owner.pr.aliases[var] != full:
                full = owner.pr.aliases[var]  # re-exported through a package __init__
                continue
            break
        return None

    def _route_prefixes(self, key: tuple[str, str] | None, depth: int = 0) -> list[str]:
        if key is None or key not in self.web_apps:
            return [""]
        own = self.web_apps[key]["prefix"]
        parents = self.web_mounts.get(key, [])
        if not parents or depth > 6:
            return [own]
        out: list[str] = []
        for parent, mount_prefix in parents:
            for base in self._route_prefixes(parent, depth + 1):
                out.append(_join_route(base, mount_prefix, own))
        return list(dict.fromkeys(out))

    def _build_decorator_endpoints(self) -> None:
        self._collect_web_apps()
        for qn, sym in self.sym_info.items():
            if sym.kind == "class" or not isinstance(sym.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            mod = self.sym_module[qn]
            for deco in sym.node.decorator_list:
                if not (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)):
                    continue
                verb = deco.func.attr
                if verb not in ROUTE_DECORATORS:
                    continue
                base = dotted_name(deco.func.value) or ""
                key = self._web_ref(mod, base)
                if key is None and not base.split(".")[-1].lower().endswith(ROUTER_NAME_HINTS):
                    continue
                path = _const_arg(deco, 0) or _kw_str(deco, "path", "rule")
                if path is None:
                    continue
                framework = self.web_apps[key]["framework"] if key else ("flask" if verb == "route" else "fastapi")
                if verb in ("route", "api_route"):
                    methods = _kw_str_list(deco, "methods") or ["GET"]
                elif verb == "websocket":
                    methods = ["WS"]
                else:
                    methods = [verb.upper()]
                self.frameworks.add(framework)
                for prefix in self._route_prefixes(key):
                    self._add_endpoint(
                        mod,
                        route=_join_route(prefix, path),
                        line=deco.lineno,
                        end_line=sym.end_line,
                        handler_qn=qn,
                        methods=[m.upper() for m in methods],
                        extractor=f"{framework}.routes",
                        confidence=0.95 if key else 0.7,
                        framework=framework,
                    )

    def _add_endpoint(
        self,
        mod: _Module,
        *,
        route: str,
        line: int,
        end_line: int | None,
        handler_qn: str | None,
        methods: list[str],
        extractor: str,
        confidence: float,
        framework: str,
    ) -> None:
        verb_key = ",".join(methods)
        eid = stable_node_id(self.pid, "endpoint", mod.rel, str(line), route, verb_key)
        props: dict[str, Any] = {
            "route": route,
            "methods": methods,
            "role": "urls",
            "layer": "api",
            "framework": framework,
        }
        if handler_qn:
            props["handler"] = handler_qn
        self._add_node(
            NodeRecord(
                id=eid,
                project_id=self.pid,
                node_type=NodeType.ENDPOINT,
                name=route or "/",
                qualified_name=f"{mod.name}:{verb_key} {route}",
                source_path=mod.rel,
                start_line=line,
                end_line=end_line,
                extractor=extractor,
                confidence=confidence,
                properties=props,
            )
        )
        self._edge(EdgeType.CONTAINS, mod.node_id, eid, rel=mod.rel, extractor=extractor, confidence=1.0)
        if handler_qn and handler_qn in self.symbols:
            view_id = self.symbols[handler_qn]
            self._edge(EdgeType.ROUTES_TO, eid, view_id, rel=mod.rel, line=line, extractor=extractor, confidence=0.95)
            self._edge(EdgeType.HANDLES, view_id, eid, rel=mod.rel, line=line, extractor=extractor, confidence=0.95)
            view_node = self.nodes.get(view_id)
            if view_node is not None:
                view_node.properties["role"] = "views"
                view_node.properties["layer"] = "api"

    def _link_dependency_injection(self) -> None:
        """FastAPI `Depends(fn)` / `Security(fn)` parameters become INJECTS edges."""
        for qn, sym in self.sym_info.items():
            if not isinstance(sym.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            mod = self.sym_module[qn]
            sid = self.symbols[qn]
            class_qn = sym.parent_class
            for sub in ast.walk(sym.node.args):
                if not isinstance(sub, ast.Call) or not sub.args:
                    continue
                if (dotted_name(sub.func) or "").split(".")[-1] not in DI_FUNCTIONS:
                    continue
                hit = self.resolve(mod.pr, dotted_name(sub.args[0]) or "", class_qn)
                if not hit or hit[1] or hit[0] not in self.symbols:
                    continue
                self.frameworks.add("fastapi")
                self._edge(
                    EdgeType.INJECTS, sid, self.symbols[hit[0]],
                    rel=mod.rel, line=getattr(sub, "lineno", sym.start_line), extractor="fastapi.depends",
                    confidence=0.9, relation="depends",
                )

    # ---------------------------------------------------------------- sqlalchemy

    def _add_sqlalchemy_field(
        self, model_qn: str, mod: _Module, model_id: str, fname: str, item: ast.stmt, value: ast.Call,
        ftype: str, order: int,
    ) -> None:
        props: dict[str, Any] = {"order": order, "layer": "data", "role": "models"}
        type_name = None
        for arg in value.args:
            if isinstance(arg, ast.Call):
                continue
            type_name = dotted_name(arg)
            if type_name:
                break
        if type_name is None and isinstance(item, ast.AnnAssign):
            type_name = ast.unparse(item.annotation)[:60]
        props["field_type"] = (type_name or ftype).split(".")[-1]
        for kw in value.keywords:
            if kw.arg in ("nullable", "primary_key", "unique", "index", "default") and isinstance(kw.value, ast.Constant):
                props[kw.arg] = kw.value.value
        target_qn: str | None = None
        relation = None
        for sub in ast.walk(value):
            if isinstance(sub, ast.Call) and (dotted_name(sub.func) or "").split(".")[-1] == "ForeignKey" and sub.args:
                ref = _const_arg(sub, 0) or dotted_name(sub.args[0]) or ""
                table = ref.split(".")[0]
                target_qn = self.tablenames.get(table)
                relation = "many-to-one"
                props["foreign_key"] = ref
                break
        if ftype == "relationship":
            ref = _const_arg(value, 0) or dotted_name(value.args[0]) if value.args else None
            if ref:
                target_qn = next((q for q in self.model_qns if q.split(".")[-1] == ref.split(".")[-1]), None)
                relation = "relationship"
        if target_qn:
            props["relation_to"] = self.sym_info[target_qn].name
            props["relation"] = relation
        props["summary"] = props["field_type"] + (f" → {props['relation_to']}" if target_qn else "")
        fid = stable_node_id(self.pid, "field", model_id, fname)
        self._add_node(
            NodeRecord(
                id=fid,
                project_id=self.pid,
                node_type=NodeType.FIELD,
                name=fname,
                qualified_name=f"{model_qn}.{fname}",
                source_path=mod.rel,
                start_line=item.lineno,
                end_line=item.end_lineno or item.lineno,
                extractor="sqlalchemy.models",
                confidence=0.9,
                properties=props,
            )
        )
        self._edge(EdgeType.CONTAINS, model_id, fid, rel=mod.rel, extractor="sqlalchemy.models", confidence=1.0)
        if target_qn and target_qn in self.symbols and self.symbols[target_qn] != model_id:
            self._edge(
                EdgeType.FK_TO, model_id, self.symbols[target_qn],
                rel=mod.rel, line=item.lineno, extractor="sqlalchemy.models", confidence=0.85,
                field=fname, relation=relation,
            )

    # ------------------------------------------------------------------ enrich

    def _enrich(self) -> None:
        index = GraphIndex.build(self.nodes.values(), self.edges.values())
        out_names: dict[str, dict[str, list[str]]] = {}
        for e in index.edges:
            tgt = index.nodes[e.target_id]
            out_names.setdefault(e.source_id, {}).setdefault(e.edge_type.value, []).append(tgt.name)

        pkg_modules: dict[str, int] = {}
        for e in index.edges:
            if e.edge_type == EdgeType.CONTAINS and index.nodes[e.source_id].node_type == NodeType.PACKAGE:
                if index.nodes[e.target_id].node_type == NodeType.MODULE:
                    pkg_modules[e.source_id] = pkg_modules.get(e.source_id, 0) + 1

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
            if node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.MODEL, NodeType.MIDDLEWARE, NodeType.MODULE):
                if node.node_type == NodeType.MODULE:
                    lines = props.get("line_count", 0)
                elif node.start_line and node.end_line:
                    lines = node.end_line - node.start_line + 1
                else:
                    lines = 0
                props["lines"] = lines
                props["complexity"] = classify_complexity(lines, index.fan_out(node.id))

            outs = out_names.get(node.id, {})
            reads, writes = outs.get("READS_MODEL", []), outs.get("WRITES_MODEL", [])
            tags: list[str] = []
            if role:
                tags.append(role)
            if reads or writes:
                tags.append("orm")
            if props.get("signal"):
                tags.append("signal")
            if props.get("methods"):
                tags.extend(m.lower() for m in props["methods"])
            if role in ("manage", "wsgi", "asgi") or props.get("entry_point"):
                tags.append("entry-point")
            if props.get("framework") and node.node_type == NodeType.ENDPOINT:
                tags.append(str(props["framework"]))
            if props.get("complexity") == "complex":
                tags.append("complex")
            if node.node_type == NodeType.MODEL and index.fan_in(node.id) >= 3:
                tags.append("core-model")

            doc = props.get("docstring")
            summary = props.get("summary")
            if node.node_type == NodeType.PROJECT:
                kind = "Django project" if self.result.is_django else "Python project"
                routes = sum(1 for n in self.nodes.values() if n.node_type == NodeType.ENDPOINT)
                summary = f"{kind} with {len(self.packages)} package(s) and {routes} route(s)."
            elif node.node_type == NodeType.PACKAGE:
                summary = f"App `{node.name}` containing {pkg_modules.get(node.id, 0)} module(s)."
            elif node.node_type in (NodeType.MODULE, NodeType.MIGRATION):
                label = ROLE_LABEL.get(role or "", "Module")
                kids = children.get(node.id, [])
                classes = sum(1 for k in kids if k.node_type in (NodeType.CLASS, NodeType.MODEL, NodeType.MIDDLEWARE))
                funcs = sum(1 for k in kids if k.node_type == NodeType.FUNCTION)
                counted = f" with {classes} class(es) and {funcs} function(s)" if (classes or funcs) else ""
                summary = doc or f"{label}{counted}."
            elif node.node_type == NodeType.ENDPOINT:
                handler = props.get("handler", "").split(".")[-1] or props.get("view_ref") or "an unresolved handler"
                verbs = f" [{', '.join(props['methods'])}]" if props.get("methods") else ""
                summary = f"Routes `{props.get('route')}`{verbs} to `{handler}`."
            elif node.node_type == NodeType.MODEL and props.get("inferred"):
                summary = f"Model `{node.qualified_name}` defined outside the analysed code; referenced by foreign keys."
            elif node.node_type == NodeType.MODEL:
                fields = [k for k in children.get(node.id, []) if k.node_type == NodeType.FIELD]
                rel = outs.get("FK_TO", [])
                summary = doc or f"ORM model with {len(fields)} field(s)" + (f", related to {uniq(rel)}" if rel else "") + "."
            elif node.node_type == NodeType.MIDDLEWARE:
                summary = doc or "Middleware that wraps each request/response" + (
                    f" (position {props['order'] + 1} in the chain)" if "order" in props else ""
                ) + "."
            elif node.node_type in (NodeType.FUNCTION, NodeType.CLASS):
                parts: list[str] = []
                if reads:
                    parts.append(f"reads {uniq(reads)}")
                if writes:
                    parts.append(f"writes {uniq(writes)}")
                if props.get("signal"):
                    subs = outs.get("SUBSCRIBES", [])
                    parts.append(f"reacts to `{props['signal']}`" + (f" on {uniq(subs)}" if subs else ""))
                calls = outs.get("CALLS", [])
                if calls and not parts:
                    parts.append(f"calls {uniq(calls)}")
                role_label = _singular(ROLE_LABEL.get(role or "", "Code"))
                what = "Class" if node.node_type == NodeType.CLASS else "Function"
                summary = doc or (f"{role_label} {what.lower()}" + (": " + "; ".join(parts) if parts else "") + ".")
            elif node.node_type == NodeType.EXTERNAL_SERVICE:
                users = [index.nodes[e.source_id].name for e in index.incoming.get(node.id, [])]
                summary = f"{props.get('kind', 'external').title()} dependency used by {uniq(users) or 'the project'}."
            if summary:
                props["summary"] = summary
            props["tags"] = list(dict.fromkeys(tags))
            if "layer" not in props and node.node_type in (NodeType.PACKAGE, NodeType.PROJECT):
                continue
            props.setdefault("layer", layer_for_role(role) if role else None)
        # drop empty docstring/None noise
        for node in self.nodes.values():
            for key in ("docstring", "parse_error"):
                if node.properties.get(key) is None:
                    node.properties.pop(key, None)
            if node.properties.get("layer") is None:
                node.properties.pop("layer", None)


# ------------------------------------------------------------------ ast helpers


def _const_arg(call: ast.Call, index: int) -> str | None:
    if len(call.args) > index and isinstance(call.args[index], ast.Constant) and isinstance(call.args[index].value, str):
        return call.args[index].value
    return None


def _kw_str(call: ast.Call, *names: str) -> str | None:
    for kw in call.keywords:
        if kw.arg in names and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _kw_str_list(call: ast.Call, name: str) -> list[str]:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
            return [e.value for e in kw.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return []


def _join_route(*parts: str) -> str:
    segs = [p.strip("/") for p in parts if p and p.strip("/")]
    return "/" + "/".join(segs)


def _sqlalchemy_table(sym: SymbolInfo) -> str | None:
    """`__tablename__ = "x"` (SQLAlchemy) or `class X(SQLModel, table=True)`."""
    node = sym.node
    if not isinstance(node, ast.ClassDef):
        return None
    for item in node.body:
        if (
            isinstance(item, ast.Assign)
            and len(item.targets) == 1
            and isinstance(item.targets[0], ast.Name)
            and item.targets[0].id == "__tablename__"
            and isinstance(item.value, ast.Constant)
            and isinstance(item.value.value, str)
        ):
            return item.value.value
    for kw in node.keywords:
        if kw.arg == "table" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return node.name.lower()
    return None
