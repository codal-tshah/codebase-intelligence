"""Framework-neutral graph analytics: ranking, search, paths, impact, tours.

Everything here is a pure function over node/edge records so it can run in the
API, the CLI, the agent tools, and unit tests without any storage dependency.
"""

from __future__ import annotations

import difflib
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ci_core.layers import LAYER_BY_ID, layer_order
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType

# "A -> B" with one of these types means A depends on B. When B changes, A may break.
DEPENDENCY_EDGES: frozenset[EdgeType] = frozenset(
    {
        EdgeType.CALLS,
        EdgeType.IMPORTS,
        EdgeType.ROUTES_TO,
        EdgeType.READS_MODEL,
        EdgeType.WRITES_MODEL,
        EdgeType.FK_TO,
        EdgeType.DEPENDS_ON,
        EdgeType.SUBSCRIBES,
        EdgeType.QUERIES,
        EdgeType.RENDERS,
        EdgeType.HTTP_CALLS,
        EdgeType.INJECTS,
    }
)

# Edges that add noise to path finding (containment and the inverse of ROUTES_TO).
PATH_EXCLUDED_EDGES: frozenset[EdgeType] = frozenset({EdgeType.CONTAINS, EdgeType.HANDLES})


@dataclass
class GraphIndex:
    nodes: dict[str, NodeRecord]
    edges: list[EdgeRecord]
    outgoing: dict[str, list[EdgeRecord]] = field(default_factory=dict)
    incoming: dict[str, list[EdgeRecord]] = field(default_factory=dict)

    @classmethod
    def build(cls, nodes: Iterable[NodeRecord], edges: Iterable[EdgeRecord]) -> GraphIndex:
        node_map = {n.id: n for n in nodes}
        edge_list = [e for e in edges if e.source_id in node_map and e.target_id in node_map]
        out: dict[str, list[EdgeRecord]] = {}
        inc: dict[str, list[EdgeRecord]] = {}
        for e in edge_list:
            out.setdefault(e.source_id, []).append(e)
            inc.setdefault(e.target_id, []).append(e)
        return cls(nodes=node_map, edges=edge_list, outgoing=out, incoming=inc)

    def fan_in(self, node_id: str) -> int:
        return sum(1 for e in self.incoming.get(node_id, []) if e.edge_type in DEPENDENCY_EDGES)

    def fan_out(self, node_id: str) -> int:
        return sum(1 for e in self.outgoing.get(node_id, []) if e.edge_type in DEPENDENCY_EDGES)

    def degree(self, node_id: str) -> int:
        return self.fan_in(node_id) + self.fan_out(node_id)

    def layer_of(self, node_id: str) -> str | None:
        node = self.nodes.get(node_id)
        return node.properties.get("layer") if node else None


def classify_complexity(lines: int, fan_out: int) -> str:
    if lines > 80 or fan_out > 10:
        return "complex"
    if lines > 30 or fan_out > 5:
        return "moderate"
    return "simple"


# --------------------------------------------------------------------------- search


def search_nodes(
    nodes: Iterable[NodeRecord],
    query: str,
    *,
    types: set[str] | None = None,
    limit: int = 25,
) -> list[tuple[NodeRecord, float]]:
    """Fuzzy search over name, qualified name, path, tags, and summary.

    Scores run 0..1 (higher is better). Substring and prefix matches dominate;
    difflib ratio rescues small typos ("autentication").
    """
    q = query.strip().lower()
    if not q:
        return []
    tokens = [t for t in q.replace("/", " ").replace(".", " ").replace("_", " ").split() if t]
    scored: list[tuple[NodeRecord, float]] = []
    for node in nodes:
        if types and node.node_type.value not in types:
            continue
        name = node.name.lower()
        qualified = (node.qualified_name or "").lower()
        path = (node.source_path or "").lower()
        summary = str(node.properties.get("summary", "")).lower()
        tags = [str(t).lower() for t in node.properties.get("tags", [])]

        score = 0.0
        if name == q:
            score = 1.0
        elif name.startswith(q):
            score = 0.9
        elif q in name:
            score = 0.78
        elif q in qualified:
            score = 0.6
        elif q in path:
            score = 0.5

        if tokens:
            token_score = 0.0
            for tok in tokens:
                token_score += (
                    (0.3 if tok in name else 0)
                    + (0.2 if tok in qualified else 0)
                    + (0.15 if tok in path else 0)
                    + (0.2 if any(tok in t for t in tags) else 0)
                    + (0.1 if tok in summary else 0)
                )
            score = max(score, min(token_score / len(tokens), 0.75))

        if score < 0.45 and len(q) >= 4:
            ratio = difflib.SequenceMatcher(None, name, q).ratio()
            if ratio >= 0.72:
                score = max(score, ratio * 0.6)

        if score <= 0:
            continue
        if node.node_type == NodeType.FIELD:
            score *= 0.7
        elif node.node_type == NodeType.FUNCTION and "." in node.name:
            score *= 0.92  # methods rank just below the classes/functions that own them
        scored.append((node, round(score, 4)))

    scored.sort(key=lambda item: (-item[1], item[0].name))
    return scored[:limit]


# ----------------------------------------------------------------------------- paths


def find_path(index: GraphIndex, source: str, target: str, *, max_hops: int = 12) -> dict[str, Any]:
    """Shortest undirected path between two nodes (ignoring containment noise)."""
    if source not in index.nodes or target not in index.nodes:
        return {"found": False, "node_ids": [], "edges": [], "reason": "unknown node"}
    if source == target:
        return {"found": True, "node_ids": [source], "edges": []}

    parent: dict[str, tuple[str, EdgeRecord]] = {}
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        current, depth = queue.popleft()
        if depth >= max_hops:
            continue
        neighbours: list[tuple[str, EdgeRecord]] = []
        for e in index.outgoing.get(current, []):
            if e.edge_type not in PATH_EXCLUDED_EDGES:
                neighbours.append((e.target_id, e))
        for e in index.incoming.get(current, []):
            if e.edge_type not in PATH_EXCLUDED_EDGES:
                neighbours.append((e.source_id, e))
        for nxt, edge in neighbours:
            if nxt in seen:
                continue
            seen.add(nxt)
            parent[nxt] = (current, edge)
            if nxt == target:
                return _rebuild_path(parent, source, target)
            queue.append((nxt, depth + 1))
    return {"found": False, "node_ids": [], "edges": [], "reason": f"no path within {max_hops} hops"}


def _rebuild_path(
    parent: dict[str, tuple[str, EdgeRecord]], source: str, target: str
) -> dict[str, Any]:
    node_ids = [target]
    edges: list[dict[str, str]] = []
    cur = target
    while cur != source:
        prev, edge = parent[cur]
        edges.append(
            {
                "id": edge.id,
                "source": edge.source_id,
                "target": edge.target_id,
                "edge_type": edge.edge_type.value,
            }
        )
        node_ids.append(prev)
        cur = prev
    node_ids.reverse()
    edges.reverse()
    return {"found": True, "node_ids": node_ids, "edges": edges}


# ---------------------------------------------------------------------------- impact


def compute_impact(
    index: GraphIndex,
    seed_ids: Iterable[str],
    *,
    changed_files: list[str] | None = None,
    depth: int = 3,
    max_affected: int = 400,
) -> dict[str, Any]:
    """Reverse-dependency blast radius from a set of changed nodes."""
    seeds = [s for s in dict.fromkeys(seed_ids) if s in index.nodes]
    seed_set = set(seeds)
    hops: dict[str, int] = {}
    via: dict[str, str] = {}
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    while queue and len(hops) < max_affected:
        current, d = queue.popleft()
        if d >= depth:
            continue
        for e in index.incoming.get(current, []):
            if e.edge_type not in DEPENDENCY_EDGES:
                continue
            dependant = e.source_id
            if dependant in seed_set or dependant in hops:
                continue
            hops[dependant] = d + 1
            via[dependant] = current
            queue.append((dependant, d + 1))

    changed_nodes = [index.nodes[s] for s in seeds]
    affected_nodes = [index.nodes[i] for i in hops]

    def brief(node: NodeRecord) -> dict[str, Any]:
        return {
            "id": node.id,
            "name": node.name,
            "node_type": node.node_type.value,
            "source_path": node.source_path,
            "layer": node.properties.get("layer"),
            "complexity": node.properties.get("complexity"),
        }

    affected_payload = [
        {**brief(n), "hops": hops[n.id], "via": via[n.id], "via_name": index.nodes[via[n.id]].name}
        for n in sorted(affected_nodes, key=lambda x: (hops[x.id], x.name))
    ]

    structural = [
        n
        for n in changed_nodes
        if n.node_type not in (NodeType.FIELD, NodeType.MODULE, NodeType.PACKAGE)
    ]
    endpoints = [n for n in affected_nodes if n.node_type == NodeType.ENDPOINT]
    endpoints += [n for n in changed_nodes if n.node_type == NodeType.ENDPOINT]
    models_changed = [n for n in changed_nodes if n.node_type == NodeType.MODEL]
    complex_changed = [n for n in structural if n.properties.get("complexity") == "complex"]

    layer_counts: dict[str, int] = {}
    for n in [*changed_nodes, *affected_nodes]:
        layer = n.properties.get("layer")
        if layer:
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
    layers_touched = sorted(layer_counts, key=layer_order)

    hotspots = sorted(structural, key=lambda n: index.fan_in(n.id), reverse=True)[:5]
    hotspots_payload = [
        {**brief(n), "fan_in": index.fan_in(n.id)} for n in hotspots if index.fan_in(n.id) > 0
    ]

    score = (
        len(complex_changed) * 8
        + len(affected_nodes) * 1.2
        + len({n.id for n in endpoints}) * 5
        + (22 if models_changed else 0)
        + max(len(layers_touched) - 1, 0) * 4
    )
    score = min(100, round(score))
    risk = "low" if score < 25 else "medium" if score < 55 else "high"

    notes: list[str] = []
    if models_changed:
        names = ", ".join(sorted({n.name for n in models_changed})[:4])
        notes.append(f"Model change ({names}): check whether a database migration is required.")
    roles = {n.properties.get("role") for n in changed_nodes}
    if "settings" in roles:
        notes.append("Settings changed: effects are global (installed apps, middleware, databases).")
    if "urls" in roles:
        notes.append("URL configuration changed: verify routes still resolve to the intended views.")
    if "middleware" in roles:
        notes.append("Middleware changed: every request passes through it.")
    if len(layers_touched) >= 3:
        notes.append(f"Cross-layer change touching {len(layers_touched)} layers; review integration points.")
    if hotspots_payload:
        notes.append(
            f"High fan-in change: {hotspots_payload[0]['name']} is depended on by "
            f"{hotspots_payload[0]['fan_in']} node(s)."
        )
    if not seeds:
        notes.append("No indexed nodes matched the changed files; the index may be stale or the files are not analyzed.")

    involved = {*seed_set, *hops}
    graph_edges = [
        {"id": e.id, "source": e.source_id, "target": e.target_id, "edge_type": e.edge_type.value}
        for e in index.edges
        if e.edge_type in DEPENDENCY_EDGES and e.source_id in involved and e.target_id in involved
    ]

    return {
        "edges": graph_edges,
        "changed_files": changed_files or sorted({n.source_path for n in changed_nodes if n.source_path}),
        "changed": [brief(n) for n in changed_nodes if n.node_type != NodeType.FIELD],
        "affected": affected_payload,
        "affected_endpoints": [brief(n) for n in {e.id: e for e in endpoints}.values()],
        "layers": [
            {"id": lid, "name": LAYER_BY_ID[lid].name if lid in LAYER_BY_ID else lid, "count": layer_counts[lid]}
            for lid in layers_touched
        ],
        "hotspots": hotspots_payload,
        "risk": {"level": risk, "score": score},
        "notes": notes,
        "depth": depth,
    }


# ------------------------------------------------------------------------------ tour


def build_tour(index: GraphIndex, *, max_nodes_per_step: int = 8) -> list[dict[str, Any]]:
    """Deterministic guided tour ordered the way a newcomer should read the code."""

    def by_role(*roles: str, modules_only: bool = False) -> list[NodeRecord]:
        return [
            n
            for n in index.nodes.values()
            if n.properties.get("role") in roles and (not modules_only or n.node_type == NodeType.MODULE)
        ]

    def top(nodes: Iterable[NodeRecord], key=None, n: int | None = None) -> list[NodeRecord]:
        ranked = sorted(
            nodes,
            key=key or (lambda x: (-index.degree(x.id), x.source_path or "", x.name)),
        )
        return ranked[: n or max_nodes_per_step]

    steps: list[dict[str, Any]] = []
    is_django = any(n.properties.get("role") in ("settings", "manage") and (n.source_path or "").endswith(".py") for n in index.nodes.values())
    entry_points = [n for n in index.nodes.values() if n.node_type == NodeType.MODULE and (n.properties.get("entry_point") or n.properties.get("role") == "entry")]

    def add(title: str, description: str, nodes: list[NodeRecord], view: str, lesson: str | None = None) -> None:
        if not nodes:
            return
        steps.append(
            {
                "order": len(steps) + 1,
                "title": title,
                "description": description,
                "node_ids": [n.id for n in nodes],
                "view": view,
                "lesson": lesson,
            }
        )

    entry_priority = {"manage": 0, "wsgi": 1, "asgi": 2, "settings": 3}
    entries = sorted(by_role("manage", "wsgi", "asgi", "settings", modules_only=True), key=lambda n: (entry_priority.get(n.properties.get("role"), 9), n.source_path or ""))
    entries = [*entries, *[e for e in entry_points if e not in entries]]
    add(
        "Entry points and configuration",
        "Start where the process starts: app factories and `main` modules create the server or mount the UI; settings/config wire apps, middleware, and databases together."
        if not is_django
        else "Start where the process starts: `manage.py` drives development commands, `wsgi`/`asgi` serve production traffic, and `settings` wires apps, middleware, and databases together.",
        entries[:max_nodes_per_step],
        "layers",
        "Django reads `DJANGO_SETTINGS_MODULE` at startup; everything else is discovered from INSTALLED_APPS and ROOT_URLCONF."
        if is_django
        else "Follow the imports out of each entry point to see which packages make up each deployable.",
    )

    apps = [n for n in index.nodes.values() if n.node_type == NodeType.PACKAGE and not n.properties.get("external")]
    add(
        "Packages and services",
        f"The codebase is split into {len(apps)} package(s). Dependencies between them show the architecture and where the boundaries are.",
        top(apps, key=lambda n: (-index.degree(n.id), n.name)),
        "architecture",
        "A Django app is a Python package registered in INSTALLED_APPS. Apps should be loosely coupled and reusable."
        if is_django
        else "Edges are weighted by how many imports/calls cross the boundary; heavy two-way edges hint at tight coupling.",
    )

    url_modules = by_role("urls", modules_only=True)
    endpoints = [n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT]
    add(
        "URL routing",
        f"{len(endpoints)} route(s) map request paths to handlers. Read the root URL configuration first, then follow `include()` into each app.",
        [*top(url_modules, n=3), *top(endpoints, key=lambda n: (n.source_path or "", n.start_line or 0), n=max_nodes_per_step - 3)],
        "api-flow",
        "Django tries each `urlpatterns` entry top to bottom and uses the first match."
        if is_django
        else "Routes are registered with decorators or router calls; mount prefixes (include_router, app.use) are already applied.",
    )

    views = [
        n
        for n in index.nodes.values()
        if n.properties.get("role") == "views" and n.node_type in (NodeType.FUNCTION, NodeType.CLASS)
        and index.fan_in(n.id) + index.fan_out(n.id) > 0
    ]
    add(
        "Request handlers (views)",
        "Views receive the request, call into models or services, and build the response. The busiest views below show the main application behaviour.",
        top(views),
        "api-flow",
        "Function-based views take `request`; class-based views route HTTP verbs to methods like `get` and `post`.",
    )

    serializers = by_role("serializers")
    serializer_nodes = [n for n in serializers if n.node_type == NodeType.CLASS]
    add(
        "Serialization and validation",
        "Serializers convert models to and from JSON and validate incoming data before it reaches the database.",
        top(serializer_nodes),
        "api-flow",
        "A DRF serializer's `Meta.model` declares which model it represents.",
    )

    models = [n for n in index.nodes.values() if n.node_type == NodeType.MODEL and not n.properties.get("inferred")]
    add(
        "Data models",
        f"{len(models)} ORM model(s) define the database schema. Foreign keys show how entities relate; models with many dependants are the core domain objects.",
        top(models),
        "er",
        "Each Django model maps to one table; `ForeignKey` creates a many-to-one relation.",
    )

    middleware = [n for n in index.nodes.values() if n.node_type == NodeType.MIDDLEWARE and not n.properties.get("external")]
    add(
        "Middleware and cross-cutting concerns",
        "Middleware wraps every request. Local middleware and permission classes often implement authentication, tenancy, or logging.",
        [*middleware[:max_nodes_per_step], *top(by_role("permissions"), n=3)][:max_nodes_per_step],
        "api-flow",
        "Middleware runs in order on the way in and in reverse on the way out.",
    )

    service_nodes = [n for n in by_role("signals", "tasks") if n.node_type in (NodeType.FUNCTION, NodeType.CLASS)]
    add(
        "Signals and background work",
        "Signals and tasks run side effects outside the request path (emails, cache invalidation, async jobs).",
        top(service_nodes),
        "call-graph",
        "A `post_save` receiver fires whenever the model is saved, even from the admin or shell.",
    )

    pages = [n for n in index.nodes.values() if n.node_type == NodeType.COMPONENT and n.properties.get("route")]
    components = [n for n in index.nodes.values() if n.node_type == NodeType.COMPONENT]
    add(
        "UI pages and components",
        f"{len(components)} UI component(s){f', {len(pages)} routed page(s)' if pages else ''}. Start from pages and the root component, then follow what each renders.",
        top([*pages, *[c for c in components if c not in pages]], key=lambda n: (0 if n.properties.get("route") else 1, -index.degree(n.id), n.name)),
        "components",
        "Render edges show composition; hooks and API-client calls show where data comes from.",
    )
    callers = {e.source_id for e in index.edges if e.edge_type == EdgeType.HTTP_CALLS}
    add(
        "Frontend → backend calls",
        f"{len(callers)} client function(s)/component(s) call backend endpoints. These links connect the UI to the API layer above.",
        top([index.nodes[c] for c in callers]),
        "components",
        "Request URLs are matched to backend routes statically; dynamic URLs or base URLs from config can be missed.",
    )

    services = [n for n in index.nodes.values() if n.node_type == NodeType.EXTERNAL_SERVICE]
    add(
        "External integrations",
        "Third-party services and SDKs this project depends on, with the modules that use them.",
        top(services),
        "integrations",
        None,
    )

    tests = [n for n in by_role("tests") if n.node_type == NodeType.MODULE]
    add(
        "Tests",
        "Finish with the tests: they document expected behaviour and show how each component is exercised.",
        top(tests, key=lambda n: n.source_path or ""),
        "layers",
        None,
    )
    return steps


def top_ranked(index: GraphIndex, node_types: set[NodeType], n: int = 10, *, by: str = "fan_in") -> list[dict[str, Any]]:
    scorer = index.fan_in if by == "fan_in" else index.fan_out
    ranked = sorted(
        (node for node in index.nodes.values() if node.node_type in node_types),
        key=lambda node: (-scorer(node.id), node.name),
    )
    return [
        {"id": node.id, "name": node.name, "node_type": node.node_type.value, "score": scorer(node.id)}
        for node in ranked[:n]
        if scorer(node.id) > 0
    ]


# -------------------------------------------------------------------------- endpoints

_HANDLER_FOLLOW = frozenset({EdgeType.CALLS, EdgeType.INJECTS})
_DATA_ACCESS = {EdgeType.READS_MODEL: "read", EdgeType.WRITES_MODEL: "write", EdgeType.QUERIES: "read"}


def describe_endpoint(index: GraphIndex, ep: NodeRecord, *, depth: int = 3) -> dict[str, Any]:
    """Handler, guards/auth dependencies, frontend callers, and models touched by one route."""
    def ref(n: NodeRecord) -> dict[str, Any]:
        return {"id": n.id, "name": n.name, "node_type": n.node_type.value, "source_path": n.source_path, "line": n.start_line}

    handlers = [index.nodes[e.target_id] for e in index.outgoing.get(ep.id, []) if e.edge_type == EdgeType.ROUTES_TO]
    guards = [
        index.nodes[e.target_id]
        for e in index.outgoing.get(ep.id, [])
        if e.edge_type == EdgeType.DEPENDS_ON and e.properties.get("relation") in ("middleware", "guard")
    ]
    injected: list[NodeRecord] = []
    for h in handlers:
        injected += [index.nodes[e.target_id] for e in index.outgoing.get(h.id, []) if e.edge_type == EdgeType.INJECTS]
    callers = [index.nodes[e.source_id] for e in index.incoming.get(ep.id, []) if e.edge_type == EdgeType.HTTP_CALLS]

    models: dict[str, dict[str, Any]] = {}
    services: dict[str, NodeRecord] = {}
    seen = {ep.id}
    frontier = [(h.id, 0) for h in handlers]
    while frontier:
        cur, d = frontier.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for e in index.outgoing.get(cur, []):
            target = index.nodes[e.target_id]
            if e.edge_type in _DATA_ACCESS:
                entry = models.setdefault(target.id, {**ref(target), "access": set()})
                entry["access"].add(_DATA_ACCESS[e.edge_type])
            elif target.node_type == NodeType.EXTERNAL_SERVICE:
                services[target.id] = target
            elif e.edge_type in _HANDLER_FOLLOW and d < depth:
                frontier.append((e.target_id, d + 1))
    return {
        **ref(ep),
        "route": ep.properties.get("route") or ep.name,
        "methods": ep.properties.get("methods") or [],
        "framework": ep.properties.get("framework"),
        "handler": ref(handlers[0]) if handlers else None,
        "guards": [ref(g) for g in guards],
        "dependencies": [ref(i) for i in injected],
        "callers": [ref(c) for c in callers],
        "models": [{**m, "access": sorted(m["access"])} for m in models.values()],
        "external": [ref(s) for s in services.values()],
        "confidence": ep.confidence,
    }


def list_endpoints(index: GraphIndex, *, query: str | None = None) -> list[dict[str, Any]]:
    eps = [n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT]
    if query:
        q = query.lower().strip()
        eps = [n for n in eps if q in n.name.lower() or q in str(n.properties.get("handler", "")).lower()]
    eps.sort(key=lambda n: (str(n.properties.get("route") or n.name), ",".join(n.properties.get("methods") or [])))
    return [describe_endpoint(index, ep) for ep in eps]


def seeds_for_files(index: GraphIndex, files: Iterable[str]) -> list[str]:
    """Node ids defined in the given project-relative files."""
    wanted = {f.replace("\\", "/") for f in files}
    return [n.id for n in index.nodes.values() if n.source_path in wanted]


def impact_for_request(
    index: GraphIndex, *, files: Iterable[str] = (), node_ids: Iterable[str] = (), depth: int = 3
) -> dict[str, Any]:
    """Single entry point for "what does this change affect?" (API, CLI and MCP all use it)."""
    files = [f.replace("\\", "/") for f in files]
    seeds = [*seeds_for_files(index, files), *node_ids]
    return compute_impact(index, seeds, changed_files=files or None, depth=depth)
