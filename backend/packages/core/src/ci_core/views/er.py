"""Data model: ORM models with fields, relations, and (optionally) the code that uses them."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import edges_between, node_view

ACCESS = {EdgeType.READS_MODEL, EdgeType.WRITES_MODEL, EdgeType.QUERIES}


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    models = [n for n in index.nodes.values() if n.node_type == NodeType.MODEL]
    model_ids = {m.id for m in models}
    fields = [
        n
        for n in index.nodes.values()
        if n.node_type == NodeType.FIELD and any(e.source_id in model_ids for e in index.incoming.get(n.id, []))
    ][:1000]
    chosen = [*models, *fields]
    allowed = {n.id for n in chosen}
    types = {EdgeType.FK_TO, EdgeType.CONTAINS}
    meta: dict[str, Any] = {}
    if focus and focus in model_ids:
        # show which handlers/services read or write the focused model
        users = {e.source_id for e in index.incoming.get(focus, []) if e.edge_type in ACCESS}
        allowed |= users
        chosen += [index.nodes[u] for u in users]
        types |= ACCESS
        meta["focused"] = True
    return [node_view(n, index) for n in chosen], edges_between(index, allowed, types), meta


register_view(
    ViewModule(
        id="er",
        label="Data model",
        description="ORM models with fields and relations; focus a model to see who reads/writes it",
        icon="▦",
        build=build,
        order=50,
        requires=(NodeType.MODEL,),
        best_for=(NodeType.MODEL, NodeType.FIELD, NodeType.TABLE),
        focusable=True,
        group="data",
    )
)
