"""Resolve underlying dependency edges for aggregated explore arcs."""

from __future__ import annotations

from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import EdgeType


def _lift_to_visible(
    index: GraphIndex, nid: str | None, visible: set[str], parent: dict[str, str]
) -> str | None:
    if nid is None:
        return None
    cur: str | None = nid
    seen = 0
    while cur and cur in index.nodes and seen < 512:
        seen += 1
        if cur in visible:
            return cur
        cur = parent.get(cur)
    return None


def underlying_edges_between_visible(
    index: GraphIndex,
    source_visible_id: str,
    target_visible_id: str,
    visible: set[str],
    parent: dict[str, str],
    *,
    cap: int = 200,
) -> list[dict[str, Any]]:
    """Raw edges that map to the aggregated arc between two visible explore nodes."""
    out: list[dict[str, Any]] = []
    for e in index.edges:
        if e.edge_type not in DEPENDENCY_EDGES or e.edge_type == EdgeType.CONTAINS:
            continue
        s = _lift_to_visible(index, e.source_id, visible, parent)
        t = _lift_to_visible(index, e.target_id, visible, parent)
        if s != source_visible_id or t != target_visible_id:
            continue
        out.append(
            {
                "id": e.id,
                "edge_type": e.edge_type.value,
                "source_id": e.source_id,
                "target_id": e.target_id,
                "confidence": e.confidence,
                "properties": dict(e.properties),
            }
        )
        if len(out) >= cap:
            break
    return out
