"""API flow: route -> middleware/guards -> handler -> services -> models/external, plus the
frontend code that calls the route (end-to-end when focused on one endpoint)."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import edges_between, expand, node_view

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


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    endpoints = [n for n in index.nodes.values() if n.node_type == NodeType.ENDPOINT]
    endpoints.sort(key=lambda n: (n.source_path or "", n.start_line or 0, n.name))
    focused = bool(focus and focus in index.nodes)
    if focused:
        collected = expand(index, [focus], forward=FORWARD, depth=4)
        node = index.nodes[focus]
        if node.node_type == NodeType.ENDPOINT:
            # who calls this endpoint: api client -> hook -> component (2-3 hops upstream)
            callers = {e.source_id for e in index.incoming.get(focus, []) if e.edge_type == EdgeType.HTTP_CALLS}
            collected |= expand(index, callers, backward=UPSTREAM, depth=3, limit=60)
    else:
        collected = expand(index, [n.id for n in endpoints[:40]], forward=FORWARD, depth=2)
        # first-hop frontend callers so the overview shows who uses each route
        for ep in endpoints[:40]:
            for e in index.incoming.get(ep.id, []):
                if e.edge_type == EdgeType.HTTP_CALLS:
                    collected.add(e.source_id)

    middleware = [n for n in index.nodes.values() if n.node_type == NodeType.MIDDLEWARE and not n.properties.get("external")]
    for m in middleware[:6]:
        collected.add(m.id)

    nodes = [node_view(index.nodes[i], index) for i in collected if i in index.nodes]
    edges = edges_between(index, collected, FORWARD | UPSTREAM | {EdgeType.MIDDLEWARE})
    return nodes, edges, {"endpoint_count": len(endpoints), "focused": focused}


register_view(
    ViewModule(
        id="api-flow",
        label="API flow",
        description="Route → handler → services → models, with the UI code that calls it",
        icon="⇢",
        build=build,
        order=30,
        requires=(NodeType.ENDPOINT,),
        best_for=(NodeType.ENDPOINT,),
        focusable=True,
        group="backend",
    )
)
