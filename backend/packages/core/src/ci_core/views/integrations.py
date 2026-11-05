"""Integrations: third-party services/SDKs/hosts and the code that uses them."""

from __future__ import annotations

from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, edges_between, node_view


def build(index: GraphIndex, focus: str | None) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    services = [n for n in index.nodes.values() if n.node_type == NodeType.EXTERNAL_SERVICE]
    if focus and focus in index.nodes and index.nodes[focus].node_type == NodeType.EXTERNAL_SERVICE:
        services = [index.nodes[focus]]
    collected = {s.id for s in services}
    for s in services:
        for e in index.incoming.get(s.id, []):
            collected.add(e.source_id)
    nodes = [node_view(index.nodes[i], index) for i in collected if i in index.nodes][:MAX_NODES]
    allowed = {n.id for n in nodes}
    return nodes, edges_between(index, allowed, set(DEPENDENCY_EDGES)), {}


register_view(
    ViewModule(
        id="integrations",
        label="Integrations",
        description="External services, SDKs and HTTP hosts, and who uses them",
        icon="⇄",
        build=build,
        order=60,
        requires=(NodeType.EXTERNAL_SERVICE,),
        best_for=(NodeType.EXTERNAL_SERVICE,),
        focusable=True,
        group="integrations",
    )
)
