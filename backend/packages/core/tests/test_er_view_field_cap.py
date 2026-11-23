"""ER view: per-model field cap and field_count metadata."""

from __future__ import annotations

from ci_core.insights import GraphIndex
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_core.views.er import FIELD_CAP_PER_MODEL, build


def test_er_caps_fields_per_model() -> None:
    pid = "p1"
    model = NodeRecord(
        id="m1",
        project_id=pid,
        node_type=NodeType.MODEL,
        name="Widget",
        qualified_name="app.Widget",
        extractor="t",
        confidence=1.0,
        properties={},
    )
    nodes = [model]
    edges: list[EdgeRecord] = []
    for i in range(20):
        fid = f"f{i}"
        nodes.append(
            NodeRecord(
                id=fid,
                project_id=pid,
                node_type=NodeType.FIELD,
                name=f"col_{i}",
                qualified_name=f"app.Widget.col_{i}",
                extractor="t",
                confidence=1.0,
                properties={"order": i, "field_type": "str"},
            )
        )
        edges.append(
            EdgeRecord(
                id=f"c-{i}",
                project_id=pid,
                edge_type=EdgeType.CONTAINS,
                source_id=model.id,
                target_id=fid,
                extractor="t",
                confidence=1.0,
            )
        )
    index = GraphIndex.build(nodes, edges)
    out, _, _ = build(index, None, {})
    fields = [n for n in out if n.node_type == "Field"]
    model_view = next(n for n in out if n.id == model.id)
    assert len(fields) == FIELD_CAP_PER_MODEL
    assert model_view.properties["field_count"] == 20
