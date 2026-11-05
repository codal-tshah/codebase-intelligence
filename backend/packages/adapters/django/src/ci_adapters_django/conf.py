"""Static extraction of Django settings and URL configuration from parsed modules."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from ci_parsers import ParseResult, dotted_name

URL_FUNCS = {"path", "re_path", "url"}


# ------------------------------------------------------------------------- settings


@dataclass
class SettingsInfo:
    module: str
    rel: str
    installed_apps: list[str] = field(default_factory=list)
    middleware: list[str] = field(default_factory=list)
    root_urlconf: str | None = None
    auth_user_model: str | None = None


def _string_list(node: ast.AST | None) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return [*_string_list(node.left), *_string_list(node.right)]
    return []


def extract_settings(pr: ParseResult, rel: str) -> SettingsInfo | None:
    if pr.tree is None:
        return None
    info = SettingsInfo(module=pr.module_name, rel=rel)
    found = False
    for node in ast.walk(pr.tree):
        targets: list[ast.expr] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets, value = [node.target], node.value
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "INSTALLED_APPS":
                info.installed_apps.extend(_string_list(value))
                found = True
            elif target.id == "MIDDLEWARE" or target.id == "MIDDLEWARE_CLASSES":
                info.middleware.extend(_string_list(value))
                found = True
            elif target.id == "ROOT_URLCONF" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                info.root_urlconf = value.value
                found = True
            elif target.id == "AUTH_USER_MODEL" and isinstance(value, ast.Constant) and isinstance(value.value, str):
                info.auth_user_model = value.value
                found = True
    return info if found else None


# ---------------------------------------------------------------------------- urls


@dataclass
class UrlEntry:
    line: int
    end_line: int
    route: str  # route relative to this urls module (inline include prefixes already joined)
    kind: str  # "view" | "include"
    ref: str | None  # view reference or include target as written
    name: str | None = None
    router: bool = False


def _clean_segment(route: str) -> str:
    return route.lstrip("^").rstrip("$")


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _view_ref(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Call):
        name = dotted_name(node.func)
        if name and name.endswith(".as_view"):
            name = name[: -len(".as_view")]
        return name
    return dotted_name(node)


def _include_target(call: ast.Call) -> str | None:
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Tuple) and arg.elts:
        arg = arg.elts[0]
    return _const_str(arg) or dotted_name(arg)


def _is_include(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and (dotted_name(node.func) or "").split(".")[-1] == "include"


def _collect_patterns(node: ast.AST | None, prefix: str, out: list[UrlEntry]) -> None:
    if node is None:
        return
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            _collect_patterns(elt, prefix, out)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        _collect_patterns(node.left, prefix, out)
        _collect_patterns(node.right, prefix, out)
        return
    if not isinstance(node, ast.Call):
        return
    func = (dotted_name(node.func) or "").split(".")[-1]
    if func not in URL_FUNCS or not node.args:
        return
    segment = _const_str(node.args[0])
    if segment is None:
        return
    route = prefix + _clean_segment(segment)
    target = node.args[1] if len(node.args) > 1 else None
    name = next((_const_str(kw.value) for kw in node.keywords if kw.arg == "name"), None)
    if _is_include(target):
        assert isinstance(target, ast.Call)
        if target.args and isinstance(target.args[0], (ast.List, ast.Tuple)):
            _collect_patterns(target.args[0], route, out)
            return
        out.append(
            UrlEntry(node.lineno, node.end_lineno or node.lineno, route, "include", _include_target(target), name)
        )
        return
    out.append(UrlEntry(node.lineno, node.end_lineno or node.lineno, route, "view", _view_ref(target), name))


def extract_url_entries(pr: ParseResult) -> list[UrlEntry]:
    if pr.tree is None:
        return []
    entries: list[UrlEntry] = []
    saw_urlpatterns = False
    for node in pr.tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "urlpatterns" for t in node.targets
        ):
            value = node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
            value = node.value
        if value is not None:
            saw_urlpatterns = True
            _collect_patterns(value, "", entries)

    if not saw_urlpatterns:
        for node in ast.walk(pr.tree):
            if isinstance(node, ast.Call):
                _collect_patterns(node, "", entries)

    # DRF routers: router.register(r"items", ItemViewSet)
    for node in ast.walk(pr.tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register"
            and "router" in (dotted_name(node.func.value) or "").lower()
            and len(node.args) >= 2
        ):
            prefix = _const_str(node.args[0])
            if prefix is None:
                continue
            route = _clean_segment(prefix).strip("/") + "/"
            entries.append(
                UrlEntry(node.lineno, node.end_lineno or node.lineno, route, "view", _view_ref(node.args[1]), None, True)
            )
    return entries


def expand_routes(
    entries_by_module: dict[str, list[UrlEntry]],
    resolve_include,
    root_urlconf: str | None,
    *,
    max_depth: int = 8,
) -> list[tuple[str, UrlEntry, str]]:
    """Walk the include() tree and return (module, entry, full_route) for every view route.

    `resolve_include(module, ref)` maps an include() reference to a urls module name.
    Modules that are never included (and are not ROOT_URLCONF) are treated as additional
    roots so that apps analysed in isolation still produce endpoints.
    """
    results: list[tuple[str, UrlEntry, str]] = []
    reached: set[str] = set()
    included: set[str] = set()
    for module, entries in entries_by_module.items():
        for entry in entries:
            if entry.kind == "include" and entry.ref:
                target = resolve_include(module, entry.ref)
                if target:
                    included.add(target)

    def visit(module: str, prefix: str, depth: int, stack: tuple[str, ...]) -> None:
        reached.add(module)
        for entry in entries_by_module.get(module, []):
            if entry.kind == "include":
                if not entry.ref or depth >= max_depth:
                    continue
                target = resolve_include(module, entry.ref)
                if target and target in entries_by_module and target not in stack:
                    visit(target, prefix + entry.route, depth + 1, (*stack, module))
            else:
                results.append((module, entry, prefix + entry.route))

    roots: list[str] = []
    if root_urlconf and root_urlconf in entries_by_module:
        roots.append(root_urlconf)
    roots.extend(sorted(m for m in entries_by_module if m not in included and m not in roots))
    for module in roots:
        visit(module, "", 0, ())
    # Include cycles can leave modules unreached; surface them with a bare prefix.
    for module in sorted(entries_by_module):
        if module not in reached:
            visit(module, "", 0, ())
    return results
