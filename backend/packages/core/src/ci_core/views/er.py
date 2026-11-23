"""Data model: ORM models with fields, relations, and (optionally) the code that uses them."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import edges_between, node_view

ACCESS = {EdgeType.READS_MODEL, EdgeType.WRITES_MODEL, EdgeType.QUERIES}
FIELD_CAP_PER_MODEL = 12


def _fields_for_model(index: GraphIndex, model_id: str) -> list[str]:
    fields = [
        e.target_id
        for e in index.outgoing.get(model_id, [])
        if e.edge_type == EdgeType.CONTAINS and index.nodes[e.target_id].node_type == NodeType.FIELD
    ]
    fields.sort(
        key=lambda fid: (
            index.nodes[fid].properties.get("order", 0),
            index.nodes[fid].name,
        )
    )
    return fields


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    models = [n for n in index.nodes.values() if n.node_type == NodeType.MODEL]
    model_ids = {m.id for m in models}
    field_ids: list[str] = []
    for model in models:
        fids = _fields_for_model(index, model.id)
        field_ids.extend(fids[:FIELD_CAP_PER_MODEL])
    chosen_models = list(models)
    chosen_fields = [index.nodes[fid] for fid in field_ids if fid in index.nodes]
    chosen = [*chosen_models, *chosen_fields]
    allowed = {n.id for n in chosen}
    types = {EdgeType.FK_TO, EdgeType.CONTAINS}
    meta: dict[str, Any] = {}
    if focus and focus in model_ids:
        users = {e.source_id for e in index.incoming.get(focus, []) if e.edge_type in ACCESS}
        allowed |= users
        chosen += [index.nodes[u] for u in users if u in index.nodes]
        types |= ACCESS
        meta["focused"] = True
    nodes: list[GraphNodeView] = []
    for model in chosen_models:
        view = node_view(model, index)
        total = len(_fields_for_model(index, model.id))
        view.properties["field_count"] = total
        nodes.append(view)
    nodes.extend(node_view(f, index) for f in chosen_fields)
    return nodes, edges_between(index, allowed, types), meta


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
