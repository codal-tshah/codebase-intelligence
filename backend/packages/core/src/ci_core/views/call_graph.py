"""Call graph: callers and callees around one symbol."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import edges_between, expand, node_view

CALL_TYPES = {EdgeType.CALLS, EdgeType.SUBSCRIBES, EdgeType.INJECTS, EdgeType.HTTP_CALLS}
CALLABLE = (NodeType.FUNCTION, NodeType.CLASS, NodeType.MIDDLEWARE, NodeType.COMPONENT)


def build(index: GraphIndex, focus: str | None) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    seed = focus if focus in index.nodes else None
    if seed is None:
        def call_degree(node_id: str) -> int:
            return sum(1 for e in index.outgoing.get(node_id, []) if e.edge_type in CALL_TYPES) + sum(
                1 for e in index.incoming.get(node_id, []) if e.edge_type in CALL_TYPES
            )

        callable_nodes = [n for n in index.nodes.values() if n.node_type in CALLABLE]
        if callable_nodes:
            seed = max(callable_nodes, key=lambda n: (call_degree(n.id), n.name)).id
    if seed is None:
        return [], [], {}
    collected = expand(index, [seed], forward=CALL_TYPES, backward=CALL_TYPES, depth=2, limit=120)
    nodes = [node_view(index.nodes[i], index) for i in collected]
    return nodes, edges_between(index, collected, CALL_TYPES), {"seed": seed}


register_view(
    ViewModule(
        id="call-graph",
        label="Call graph",
        description="Callers and callees around a function, class or component",
        icon="◎",
        build=build,
        order=40,
        requires=(NodeType.FUNCTION, NodeType.CLASS),
        best_for=(NodeType.FUNCTION, NodeType.CLASS, NodeType.MIDDLEWARE),
        focusable=True,
        group="backend",
    )
)
