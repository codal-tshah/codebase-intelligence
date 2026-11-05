"""Architecture: packages/apps and the weighted dependencies between them."""

from __future__ import annotations

from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, node_view


def package_of(index: GraphIndex) -> dict[str, str]:
    """Map every node to its nearest ancestor Package via CONTAINS edges."""
    parent: dict[str, str] = {}
    for e in index.edges:
        if e.edge_type == EdgeType.CONTAINS:
            parent[e.target_id] = e.source_id
    result: dict[str, str] = {}
    for node_id in index.nodes:
        cur: str | None = node_id
        guard = 0
        while cur is not None and guard < 16:
            node = index.nodes.get(cur)
            if node and node.node_type == NodeType.PACKAGE:
                result[node_id] = cur
                break
            cur = parent.get(cur)
            guard += 1
    return result


def build(index: GraphIndex, focus: str | None) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    packages = [n for n in index.nodes.values() if n.node_type == NodeType.PACKAGE]
    if not packages:
        packages = [n for n in index.nodes.values() if n.node_type == NodeType.MODULE][:MAX_NODES]
    pkg_ids = {p.id for p in packages}
    owner = package_of(index)
    parent_pkg: dict[str, str] = {}
    for e in index.edges:
        if e.edge_type == EdgeType.CONTAINS and e.source_id in pkg_ids and e.target_id in pkg_ids:
            parent_pkg[e.target_id] = e.source_id

    weights: dict[tuple[str, str], dict[str, int]] = {}
    for e in index.edges:
        if e.edge_type not in DEPENDENCY_EDGES:
            continue
        a, b = owner.get(e.source_id), owner.get(e.target_id)
        if a is None and e.source_id in pkg_ids:
            a = e.source_id
        if b is None and e.target_id in pkg_ids:
            b = e.target_id
        if not a or not b or a == b or a not in pkg_ids or b not in pkg_ids:
            continue
        bucket = weights.setdefault((a, b), {})
        bucket[e.edge_type.value] = bucket.get(e.edge_type.value, 0) + 1

    nodes: list[GraphNodeView] = []
    for p in packages:
        view = node_view(p, index)
        view.properties["member_count"] = sum(1 for nid, pid in owner.items() if pid == p.id and nid != p.id)
        if p.id in parent_pkg:
            view.properties["parent_package"] = parent_pkg[p.id]
        nodes.append(view)

    edges: list[GraphEdgeView] = []
    for (a, b), by_type in weights.items():
        total = sum(by_type.values())
        dominant = max(by_type, key=lambda k: by_type[k])
        edges.append(
            GraphEdgeView(
                id=f"agg:{a}:{b}",
                source=a,
                target=b,
                edge_type=dominant,
                properties={"weight": total, "by_type": by_type},
            )
        )
    return nodes, edges, {}


register_view(
    ViewModule(
        id="architecture",
        label="Architecture",
        description="Packages and services with the weighted dependencies between them",
        icon="◫",
        build=build,
        order=20,
        best_for=(NodeType.PACKAGE, NodeType.PROJECT),
        group="overview",
    )
)
