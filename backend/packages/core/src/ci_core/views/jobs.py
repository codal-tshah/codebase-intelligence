"""Jobs: background tasks, scheduled jobs and management commands -> what they call -> the
models they read or write (the "who writes to the DB outside a request" flowchart)."""

from __future__ import annotations

from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeRecord
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, edges_between, expand, node_view

FORWARD = {
    EdgeType.CALLS,
    EdgeType.READS_MODEL,
    EdgeType.WRITES_MODEL,
    EdgeType.QUERIES,
    EdgeType.DEPENDS_ON,
    EdgeType.INJECTS,
    EdgeType.HTTP_CALLS,
}
# Who enqueues a task (e.g. an endpoint handler calling task.delay()).
UPSTREAM = {EdgeType.CALLS}


def job_nodes(index: GraphIndex) -> list[NodeRecord]:
    jobs = [n for n in index.nodes.values() if n.properties.get("job")]
    jobs.sort(key=lambda n: (n.source_path or "", n.start_line or 0, n.name))
    return jobs


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    jobs = job_nodes(index)
    focused = bool(focus and focus in index.nodes)
    if focused:
        collected = expand(index, [focus], forward=FORWARD, depth=4)
        collected |= expand(index, [focus], backward=UPSTREAM, depth=1, limit=MAX_NODES)
    else:
        collected = expand(index, [n.id for n in jobs[:60]], forward=FORWARD, depth=3)
    nodes = [node_view(index.nodes[i], index) for i in collected if i in index.nodes][:MAX_NODES]
    allowed = {n.id for n in nodes}
    meta = {"job_count": len(jobs), "focused": focused}
    return nodes, edges_between(index, allowed, FORWARD), meta


register_view(
    ViewModule(
        id="jobs",
        label="Jobs",
        description="Background tasks, scheduled jobs and commands → functions → models they write",
        icon="⏱",
        build=build,
        order=35,
        focusable=True,
        group="backend",
        count=lambda index: len(job_nodes(index)),
    )
)
