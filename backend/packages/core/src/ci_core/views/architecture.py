"""Architecture: packages/apps and the weighted dependencies between them."""

from __future__ import annotations

from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import GraphEdgeView, GraphNodeView, NodeRecord, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import MAX_NODES, include_tests, is_test_node, node_view


def package_of(index: GraphIndex, allowed: set[str] | None = None) -> dict[str, str]:
    """Map every node to its nearest ancestor Package via CONTAINS edges (only `allowed` ids, if given)."""
    parent = index.contains_parent
    result: dict[str, str] = {}
    for node_id in index.nodes:
        cur: str | None = node_id
        guard = 0
        while cur is not None and guard < 32:
            node = index.nodes.get(cur)
            if node and node.node_type == NodeType.PACKAGE and (allowed is None or cur in allowed):
                result[node_id] = cur
                break
            cur = parent.get(cur)
            guard += 1
    return result


def architecture_packages(index: GraphIndex) -> list[NodeRecord]:
    """App-level packages. Nested directory packages (``subpackage``) are skipped, except inside a
    dominant app (3+ sub-packages holding 40%+ of the project's modules: the usual FastAPI/Flask
    ``app/`` monolith), whose first level is shown too, otherwise the diagram is a single box."""
    all_pkgs = [n for n in index.nodes.values() if n.node_type == NodeType.PACKAGE]
    apps = [n for n in all_pkgs if not n.properties.get("subpackage")]
    parent = index.contains_parent
    owner = package_of(index, {a.id for a in apps})
    modules = [n.id for n in index.nodes.values() if n.node_type == NodeType.MODULE]
    total = max(1, len(modules))
    out = list(apps)
    for app in apps:
        subs = [n for n in all_pkgs if n.properties.get("subpackage") and parent.get(n.id) == app.id]
        share = sum(1 for m in modules if owner.get(m) == app.id) / total
        if len(subs) >= 3 and share >= 0.4:
            out.extend(subs)
    return out


def _is_tests_package(pkg: NodeRecord) -> bool:
    if pkg.properties.get("subpackage"):
        return False
    qn = (pkg.qualified_name or pkg.name or "").replace("\\", "/")
    return qn.split("/")[0] == "tests" or pkg.name == "tests"


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    show_tests = include_tests(params)
    packages = architecture_packages(index)
    if not show_tests:
        packages = [p for p in packages if not _is_tests_package(p)]
    if not packages:
        packages = [n for n in index.nodes.values() if n.node_type == NodeType.MODULE][:MAX_NODES]
    pkg_ids = {p.id for p in packages}
    owner = package_of(index, pkg_ids)
    parent_pkg: dict[str, str] = {}
    for pid in pkg_ids:
        up = index.contains_parent.get(pid)
        if up is not None and up in pkg_ids:
            parent_pkg[pid] = up

    weights: dict[tuple[str, str], dict[str, int]] = {}
    for e in index.edges:
        if e.edge_type not in DEPENDENCY_EDGES:
            continue
        if not show_tests and (is_test_node(index, e.source_id) or is_test_node(index, e.target_id)):
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
        view.properties["member_count"] = sum(
            1
            for nid, pid in owner.items()
            if pid == p.id and nid != p.id and (show_tests or not is_test_node(index, nid))
        )
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
    meta: dict[str, Any] = {}
    if not show_tests:
        meta["hidden_tests"] = True
    return nodes, edges, meta


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
