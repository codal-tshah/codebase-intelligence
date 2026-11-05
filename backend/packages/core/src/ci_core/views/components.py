"""Frontend components: component render tree, hooks/stores they use, and the API calls
they make (linked to backend endpoints)."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, edges_between, expand, node_view

UI_EDGES = {EdgeType.RENDERS, EdgeType.CALLS, EdgeType.HTTP_CALLS}
UI_ROLES = {"components", "pages", "hooks", "stores", "api-client"}


def _is_ui(node) -> bool:
    return node.node_type == NodeType.COMPONENT or node.properties.get("role") in UI_ROLES


def build(index: GraphIndex, focus: str | None) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    components = [n for n in index.nodes.values() if n.node_type == NodeType.COMPONENT]
    if focus and focus in index.nodes:
        seeds = [focus]
        collected = expand(index, seeds, forward={EdgeType.RENDERS}, depth=4, limit=MAX_NODES)
        collected |= expand(index, seeds, backward={EdgeType.RENDERS}, depth=2, limit=40)
    else:
        components.sort(key=lambda n: (-index.degree(n.id), n.name))
        collected = {n.id for n in components[:MAX_NODES]}

    # data dependencies of the chosen components: hooks / api clients / stores, then endpoints
    data = expand(index, collected, forward={EdgeType.CALLS, EdgeType.HTTP_CALLS}, depth=3, limit=MAX_NODES + 80)
    keep = set(collected)
    for nid in data - collected:
        node = index.nodes[nid]
        if _is_ui(node) or node.node_type == NodeType.ENDPOINT or node.properties.get("http_calls"):
            keep.add(nid)
    nodes = [node_view(index.nodes[i], index) for i in keep]
    return nodes, edges_between(index, keep, UI_EDGES), {"component_count": len(components), "focused": bool(focus)}


register_view(
    ViewModule(
        id="components",
        label="Components",
        description="UI component tree, hooks and stores, and the API endpoints they call",
        icon="◰",
        build=build,
        order=35,
        requires=(NodeType.COMPONENT,),
        best_for=(NodeType.COMPONENT,),
        focusable=True,
        group="frontend",
    )
)
