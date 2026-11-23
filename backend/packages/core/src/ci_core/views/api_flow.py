"""API flow: how one request travels through the code, left to right.

    Client/UI  →  Endpoint  →  Guards  →  Handler  →  Service  →  Data access  →  Model / External

Focused on an endpoint (the dashboard always focuses one; the list of endpoints lives beside the
canvas), the view follows:
  * upstream:  HTTP_CALLS into the endpoint, then CALLS/RENDERS back to hooks and components
  * the route: ROUTES_TO the handler; MIDDLEWARE / INJECTS (FastAPI ``Depends``) as guards
  * downstream: CALLS from the handler through services and repositories (depth-limited),
    READS_MODEL / WRITES_MODEL / QUERIES to models, DEPENDS_ON to external services

Every node gets ``properties.column`` (one of COLUMNS) and ``properties.column_rank`` (hops from
the endpoint inside that column), so the client lays the chain out as columns without guessing.
Constructing response schemas, model base classes and test code are left out: they are real
edges, but not steps of the request.

Without a focus (API clients, MCP), the first endpoints are shown with their handlers so the
overview stays small; ``metadata.endpoint_count`` tells how many exist.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeRecord, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import edges_between, expand, node_view

COLUMNS = ("client", "endpoint", "guard", "handler", "service", "data_access", "model", "external")
COLUMN_LABELS = {
    "client": "Client / UI",
    "endpoint": "Endpoint",
    "guard": "Guards & dependencies",
    "handler": "Handler",
    "service": "Services",
    "data_access": "Data access",
    "model": "Models",
    "external": "External",
}

FORWARD = {
    EdgeType.ROUTES_TO,
    EdgeType.CALLS,
    EdgeType.READS_MODEL,
    EdgeType.WRITES_MODEL,
    EdgeType.QUERIES,
    EdgeType.DEPENDS_ON,
    EdgeType.INJECTS,
}
UPSTREAM = {EdgeType.HTTP_CALLS, EdgeType.CALLS, EdgeType.RENDERS}
DATA_EDGES = {EdgeType.READS_MODEL, EdgeType.WRITES_MODEL, EdgeType.QUERIES}
# Steps that are part of a request, but not worth a box (schema construction, logging, tests).
NOISE_ROLES = {"serializers", "tests", "forms", "admin", "migration"}
MAX_DOWNSTREAM_DEPTH = 4
MAX_CHAIN_NODES = 120


def _role(n: NodeRecord) -> str | None:
    return n.properties.get("role")


def _column(n: NodeRecord) -> str:
    """Column for a node reached downstream of the handler."""
    if n.node_type in (NodeType.MODEL, NodeType.TABLE, NodeType.FIELD):
        return "model"
    if n.node_type == NodeType.EXTERNAL_SERVICE:
        return "external"
    if n.node_type == NodeType.MIDDLEWARE:
        return "guard"
    role = _role(n)
    if role in ("repositories", "managers", "database", "models"):
        return "data_access"
    if role in ("dependencies", "permissions", "middleware"):
        return "guard"
    return "service"


def _keep_downstream(index: GraphIndex, edge_type: EdgeType, target: NodeRecord) -> bool:
    if edge_type == EdgeType.DEPENDS_ON:
        return target.node_type == NodeType.EXTERNAL_SERVICE  # not "Model inherits BaseModel"
    if target.node_type == NodeType.MODULE:
        return False
    if edge_type == EdgeType.CALLS and target.node_type == NodeType.MODEL:
        return False  # `select(Model)` / `Model(...)`: the READS/WRITES edge says it better
    return _role(target) not in NOISE_ROLES


def focused_chain(index: GraphIndex, endpoint_id: str) -> tuple[dict[str, tuple[str, int]], set[tuple[str, str, str]]]:
    """node id → (column, rank) and the (source, target, type) edges that make up the chain."""
    placed: dict[str, tuple[str, int]] = {endpoint_id: ("endpoint", 0)}
    chain_edges: set[tuple[str, str, str]] = set()

    # upstream: frontend callers (HTTP_CALLS) and the components/hooks above them
    frontier = deque()
    for e in index.incoming.get(endpoint_id, []):
        if e.edge_type == EdgeType.HTTP_CALLS and e.source_id in index.nodes:
            placed.setdefault(e.source_id, ("client", 1))
            chain_edges.add((e.source_id, endpoint_id, e.edge_type.value))
            frontier.append((e.source_id, 1))
    while frontier and len(placed) < MAX_CHAIN_NODES:
        cur, d = frontier.popleft()
        if d >= 3:
            continue
        for e in index.incoming.get(cur, []):
            if e.edge_type in UPSTREAM and e.source_id in index.nodes and e.source_id not in placed:
                placed[e.source_id] = ("client", d + 1)
                chain_edges.add((e.source_id, cur, e.edge_type.value))
                frontier.append((e.source_id, d + 1))

    # the route: handler(s) and guards
    handlers: list[str] = []
    for e in index.outgoing.get(endpoint_id, []):
        tgt = index.nodes.get(e.target_id)
        if tgt is None:
            continue
        if e.edge_type == EdgeType.ROUTES_TO:
            placed.setdefault(tgt.id, ("handler", 0))
            handlers.append(tgt.id)
            chain_edges.add((endpoint_id, tgt.id, e.edge_type.value))
        elif e.edge_type in (EdgeType.MIDDLEWARE, EdgeType.INJECTS, EdgeType.DEPENDS_ON) and tgt.node_type != NodeType.MODULE:
            placed.setdefault(tgt.id, ("guard", 0))
            chain_edges.add((endpoint_id, tgt.id, e.edge_type.value))

    # downstream from the handlers
    frontier = deque((h, 0) for h in handlers)
    while frontier and len(placed) < MAX_CHAIN_NODES:
        cur, d = frontier.popleft()
        if d >= MAX_DOWNSTREAM_DEPTH:
            continue
        for e in index.outgoing.get(cur, []):
            if e.edge_type not in FORWARD or e.edge_type == EdgeType.ROUTES_TO:
                continue
            tgt = index.nodes.get(e.target_id)
            if tgt is None or not _keep_downstream(index, e.edge_type, tgt):
                continue
            if e.edge_type == EdgeType.INJECTS:
                col = "guard"
            else:
                col = _column(tgt)
            chain_edges.add((cur, tgt.id, e.edge_type.value))
            if tgt.id in placed:
                continue
            placed[tgt.id] = (col, d + 1)
            if tgt.node_type not in (NodeType.MODEL, NodeType.EXTERNAL_SERVICE, NodeType.TABLE):
                frontier.append((tgt.id, d + 1))
    return placed, chain_edges


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    endpoints = [n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT]
    endpoints.sort(key=lambda n: (n.source_path or "", n.start_line or 0, n.name))
    focus_node = index.nodes.get(focus) if focus else None
    meta: dict[str, Any] = {"endpoint_count": len(endpoints), "focused": bool(focus_node), "columns": [
        {"id": c, "label": COLUMN_LABELS[c]} for c in COLUMNS
    ]}

    if focus_node is not None and focus_node.node_type == NodeType.ENDPOINT:
        placed, chain = focused_chain(index, focus_node.id)
        nodes = []
        for nid, (col, rank) in placed.items():
            v = node_view(index.nodes[nid], index)
            v.properties["column"] = col
            v.properties["column_rank"] = rank
            nodes.append(v)
        edges = [
            e for e in edges_between(index, set(placed), FORWARD | UPSTREAM | {EdgeType.MIDDLEWARE})
            if (e.source, e.target, e.edge_type) in chain
        ]
        meta["layout"] = "columns"
        meta["truncated"] = len(placed) >= MAX_CHAIN_NODES
        if meta["truncated"]:
            meta["truncation_reason"] = f"Chain capped at {MAX_CHAIN_NODES} nodes; open a service in the call graph to go deeper."
        return nodes, edges, meta

    if focus_node is not None:
        # focused on a handler/service: everything it leads to (legacy behaviour for non-endpoints)
        collected = expand(index, [focus_node.id], forward=FORWARD, depth=4)
    else:
        collected = expand(index, [n.id for n in endpoints[:40]], forward={EdgeType.ROUTES_TO}, depth=1)
        for ep in endpoints[:40]:
            for e in index.incoming.get(ep.id, []):
                if e.edge_type == EdgeType.HTTP_CALLS:
                    collected.add(e.source_id)
    nodes = [node_view(index.nodes[i], index) for i in collected if i in index.nodes]
    edges = edges_between(index, collected, FORWARD | UPSTREAM | {EdgeType.MIDDLEWARE})
    return nodes, edges, meta


register_view(
    ViewModule(
        id="api-flow",
        label="API flow",
        description="One request, left to right: client → endpoint → handler → services → data",
        icon="⇢",
        build=build,
        order=30,
        requires=(NodeType.ENDPOINT,),
        best_for=(NodeType.ENDPOINT,),
        focusable=True,
        group="backend",
    )
)
