"""Optimization and reuse suggestions derived from the graph (deterministic, no LLM).

Each rule is a cheap structural heuristic. Suggestions are leads for a reviewer, not verdicts:
static, name-based call resolution can miss dynamic callers, so "possibly unused" is low severity.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ci_core.graph_algo import dependency_cycles
from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, NodeRecord, NodeType

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_CALLABLE = (NodeType.FUNCTION, NodeType.CLASS)
# Names that are conventionally repeated across modules (framework hooks), not duplication.
_COMMON_NAMES = {
    "main",
    "handle",
    "handler",
    "index",
    "default",
    "render",
    "setup",
    "run",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "list",
    "create",
    "update",
    "retrieve",
    "destroy",
    "save",
    "clean",
    "validate",
    "init",
    "app",
    "router",
    "config",
    "test",
    "helper",
    "utils",
    "middleware",
    "dispatch",
    "execute",
}
_ENTRY_ROLES = {
    "views",
    "tasks",
    "signals",
    "pages",
    "components",
    "hooks",
    "middleware",
    "permissions",
    "settings",
    "urls",
    "admin",
    "migrations",
    "tests",
    "manage",
    "wsgi",
    "asgi",
    "commands",
}


def _ref(n: NodeRecord) -> dict[str, Any]:
    return {"id": n.id, "name": n.name, "type": n.node_type.value, "source_path": n.source_path, "line": n.start_line}


def _item(kind: str, severity: str, title: str, detail: str, nodes: list[NodeRecord]) -> dict[str, Any]:
    return {"kind": kind, "severity": severity, "title": title, "detail": detail, "nodes": [_ref(n) for n in nodes]}


_NON_RUNTIME_IMPORT = frozenset({"type_only", "lazy"})


def _runtime_import_index(index: GraphIndex) -> GraphIndex:
    """Load-time import subgraph for cycle suggestions only (not for fan-in/out or other metrics).

    Omits package ``__init__`` barrels and edges tagged ``import_kind`` ``type_only`` / ``lazy``.
    """
    skip = {
        nid
        for nid, n in index.nodes.items()
        if n.node_type == NodeType.MODULE and (n.source_path or "").endswith("__init__.py")
    }
    edges = [
        e
        for e in index.edges
        if e.edge_type == EdgeType.IMPORTS
        and e.source_id not in skip
        and e.target_id not in skip
        and not (e.properties.get("import_kind") in _NON_RUNTIME_IMPORT and not e.properties.get("has_runtime_import"))
    ]
    all_imp = [e for e in index.edges if e.edge_type == EdgeType.IMPORTS]
    if not skip and len(edges) == len(all_imp):
        return index
    nodes = [n for n in index.nodes.values() if n.id not in skip]
    return GraphIndex.build(nodes, edges)


def _is_test(n: NodeRecord) -> bool:
    path = (n.source_path or "").lower()
    # `test_` must start a path segment: a plain substring match also hid latest_*.py, contest_*.py, ...
    test_segment = any(seg.startswith("test_") for seg in path.split("/"))
    return (
        n.properties.get("layer") == "test"
        or "/tests/" in f"/{path}"
        or test_segment
        or ".test." in path
        or ".spec." in path
    )


def suggest(index: GraphIndex, *, limit: int = 40) -> list[dict[str, Any]]:
    """Ranked suggestions: high-risk hubs, large functions, duplicated helpers, scattered model
    writes, import cycles and possibly-unused code."""
    out: list[dict[str, Any]] = []
    nodes = [n for n in index.nodes.values() if not _is_test(n)]

    # 1. Hubs: many dependants -> stable interface + tests before changing.
    for n in nodes:
        if n.node_type in (*_CALLABLE, NodeType.MODULE) and (fan_in := index.fan_in(n.id)) >= 10:
            out.append(
                _item(
                    "hotspot",
                    "high" if fan_in >= 25 else "medium",
                    f"{n.name} has {fan_in} dependants",
                    "Changes here ripple widely. Keep its interface stable, cover it with tests, "
                    "and consider splitting responsibilities if it keeps growing.",
                    [n],
                )
            )

    # 2. Large/branchy functions -> split.
    for n in nodes:
        if n.node_type == NodeType.FUNCTION and n.properties.get("complexity") == "complex":
            lines = n.properties.get("lines") or ((n.end_line or 0) - (n.start_line or 0) + 1)
            fan_out = index.fan_out(n.id)
            out.append(
                _item(
                    "complexity",
                    "medium",
                    f"{n.name} is large ({lines} lines, calls {fan_out})",
                    "Extract cohesive steps into helpers to make it testable and reusable.",
                    [n],
                )
            )

    # 3. Same helper name defined in several modules -> shared utility.
    by_name: dict[str, list[NodeRecord]] = defaultdict(list)
    for n in nodes:
        if n.node_type == NodeType.FUNCTION and "." not in n.name and not n.properties.get("parent_class"):
            name = n.name.lower()
            if len(name) >= 6 and name not in _COMMON_NAMES and not name.startswith("_"):
                by_name[n.name].append(n)
    for name, defs in by_name.items():
        modules = {d.source_path for d in defs}
        if len(modules) >= 2:
            out.append(
                _item(
                    "duplication",
                    "medium" if len(modules) >= 3 else "low",
                    f"{name} is defined in {len(modules)} files",
                    "Likely copy-pasted logic. Consolidate into one shared helper if the bodies match.",
                    defs,
                )
            )

    # 4. A model written from many places -> repository/service.
    for m in nodes:
        if m.node_type != NodeType.MODEL:
            continue
        writers = [
            index.nodes[e.source_id]
            for e in index.incoming.get(m.id, [])
            if e.edge_type == EdgeType.WRITES_MODEL and e.source_id in index.nodes
        ]
        if len({w.source_path for w in writers}) >= 4:
            out.append(
                _item(
                    "data-access",
                    "medium",
                    f"{m.name} is written from {len(writers)} places",
                    "Centralise writes in one service/repository so validation, transactions and "
                    "side effects live in one place.",
                    [m, *writers[:8]],
                )
            )

    # 5. Import cycles (strongly connected sets of modules) -> break the loop.
    for cyc in dependency_cycles(_runtime_import_index(index), {EdgeType.IMPORTS}):
        members = [index.nodes[i] for i in cyc["node_ids"]]
        if len(members) == 2:
            title = f"{members[0].name} and {members[1].name} import each other"
        else:
            path = [index.nodes[i].name for i in cyc["cycle"]]
            shown = " -> ".join([*path[:6], "..."] if len(path) > 6 else path) + f" -> {path[0]}"
            title = f"{len(members)} modules are tied in import cycles, e.g. {shown}"
        out.append(
            _item(
                "cycle",
                "high" if len(members) >= 5 else "medium",
                title,
                "Circular imports make load order fragile. Move the shared part into a "
                "separate module, or import lazily at the call site.",
                members[:10],
            )
        )

    # 6. Possibly unused functions (no callers; not an entry point by role/type).
    unused = [
        n
        for n in nodes
        if n.node_type == NodeType.FUNCTION
        and not n.properties.get("job")
        and n.properties.get("role") not in _ENTRY_ROLES
        and not n.name.startswith(("_", "test"))
        and not any(e.edge_type == EdgeType.HANDLES for e in index.outgoing.get(n.id, []))
        # only CONTAINS (or nothing) points here: no calls, routes, imports, injections
        and all(e.edge_type == EdgeType.CONTAINS for e in index.incoming.get(n.id, []))
    ]
    if unused:
        out.append(
            _item(
                "unused",
                "low",
                f"{len(unused)} function(s) have no detected callers",
                "Possibly dead code. Static analysis can miss dynamic calls, reflection and external "
                "entry points, so confirm before deleting.",
                unused[:15],
            )
        )

    return _balanced(out, limit)


def _balanced(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Top `limit` items, ranked by severity, without one kind crowding out the rest.

    On large repos there are hundreds of hotspots; a plain severity sort would return only those.
    Each kind first gets an equal share (its most severe items), then leftovers fill by severity.
    """
    rank = lambda s: (SEVERITY_ORDER[s["severity"]], s["kind"], s["title"])  # noqa: E731
    items = sorted(items, key=rank)
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        by_kind[it["kind"]].append(it)
    share = max(1, limit // max(1, len(by_kind)))
    picked = [it for group in by_kind.values() for it in group[:share]]
    chosen = {id(it) for it in picked}
    picked += [it for it in items if id(it) not in chosen][: max(0, limit - len(picked))]
    return sorted(picked, key=rank)[:limit]
