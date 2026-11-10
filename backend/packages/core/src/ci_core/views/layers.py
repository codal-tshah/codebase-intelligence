"""Layers: modules, routes, models and components grouped by architectural layer."""

from __future__ import annotations

from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, edges_between, node_view

KEEP = {
    NodeType.MODULE,
    NodeType.ENDPOINT,
    NodeType.MODEL,
    NodeType.MIDDLEWARE,
    NodeType.EXTERNAL_SERVICE,
}


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    candidates = [n for n in index.nodes.values() if n.node_type in KEEP]
    candidates.sort(key=lambda n: (-index.degree(n.id), n.name))
    truncated = len(candidates) > MAX_NODES
    chosen = candidates[:MAX_NODES]
    allowed = {n.id for n in chosen}
    return [node_view(n, index) for n in chosen], edges_between(index, allowed, set(DEPENDENCY_EDGES)), {"truncated": truncated}


register_view(
    ViewModule(
        id="layers",
        label="Layers",
        description="Modules, routes and models grouped by architectural layer",
        icon="≡",
        build=build,
        order=10,
        best_for=(NodeType.MODULE, NodeType.MIGRATION, NodeType.CONFIG_REF),
        group="overview",
    )
)
