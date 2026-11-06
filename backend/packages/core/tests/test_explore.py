"""Explore view and neighborhood API logic."""

from __future__ import annotations

from ci_core.insights import GraphIndex, neighborhood_subgraph
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_core.views.explore import build as explore_build


def _node(pid: str, nid: str, ntype: NodeType, name: str, parent: str | None = None) -> tuple[NodeRecord, list[EdgeRecord]]:
    edges: list[EdgeRecord] = []
    n = NodeRecord(
        id=nid,
        project_id=pid,
        node_type=ntype,
        name=name,
        qualified_name=name,
        source_path=None,
        start_line=None,
        end_line=None,
        extractor="t",
        confidence=1.0,
        properties={},
    )
    if parent:
        edges.append(
            EdgeRecord(
                id=f"c-{parent}-{nid}",
                project_id=pid,
                edge_type=EdgeType.CONTAINS,
                source_id=parent,
                target_id=nid,
                extractor="t",
                confidence=1.0,
            )
        )
    return n, edges


def test_explore_top_level_only() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, e0 = _node(pid, "proj", NodeType.PROJECT, "root")
    nodes.append(proj)
    edges.extend(e0)
    for i, name in enumerate(("pkg_a", "pkg_b")):
        n, ee = _node(pid, f"pkg{i}", NodeType.PACKAGE, name, parent="proj")
        nodes.append(n)
        edges.extend(ee)
    index = GraphIndex.build(nodes, edges)
    nout, eout, meta = explore_build(index, None, {})
    assert meta.get("truncated") is not True
    ids = {n.id for n in nout}
    assert "pkg0" in ids and "pkg1" in ids
    # children not expanded
    assert all((n.properties or {}).get("explore_expanded") is not True for n in nout)


def test_explore_expand_package_shows_modules() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, _ = _node(pid, "proj", NodeType.PROJECT, "root")
    nodes.append(proj)
    pkg, ee = _node(pid, "pkg1", NodeType.PACKAGE, "app", parent="proj")
    nodes.append(pkg)
    edges.extend(ee)
    mod, ee2 = _node(pid, "mod1", NodeType.MODULE, "views.py", parent="pkg1")
    nodes.append(mod)
    edges.extend(ee2)
    index = GraphIndex.build(nodes, edges)
    nout, _, meta = explore_build(index, None, {"expanded": ["pkg1"]})
    ids = {n.id for n in nout}
    assert "mod1" in ids
    assert meta["explore"]["expanded"]


def test_aggregate_preserves_underlying_count() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, _ = _node(pid, "proj", NodeType.PROJECT, "root")
    pkg_a, ee = _node(pid, "pa", NodeType.PACKAGE, "a", parent="proj")
    pkg_b, ee2 = _node(pid, "pb", NodeType.PACKAGE, "b", parent="proj")
    nodes.extend([proj, pkg_a, pkg_b])
    edges.extend(ee + ee2)
    # Hidden symbols inside packages
    fa, efa = _node(pid, "fa", NodeType.FUNCTION, "fa", parent="pa")
    fb, efb = _node(pid, "fb", NodeType.FUNCTION, "fb", parent="pb")
    nodes.extend([fa, fb])
    edges.extend(efa + efb)
    edges.append(
        EdgeRecord(
            id="call1",
            project_id=pid,
            edge_type=EdgeType.CALLS,
            source_id="fa",
            target_id="fb",
            extractor="t",
            confidence=1.0,
        )
    )
    edges.append(
        EdgeRecord(
            id="call2",
            project_id=pid,
            edge_type=EdgeType.CALLS,
            source_id="fa",
            target_id="fb",
            extractor="t",
            confidence=1.0,
        )
    )
    index = GraphIndex.build(nodes, edges)
    _, eout, _ = explore_build(index, None, {})
    agg = next((e for e in eout if e.properties.get("aggregated")), None)
    assert agg is not None
    assert agg.properties.get("underlying_edge_count") == 2
    assert agg.properties.get("weight") == 2


def test_neighborhood_depth() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    a = NodeRecord(
        id="a",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="a",
        qualified_name="a",
        extractor="t",
        confidence=1.0,
        properties={},
    )
    b = NodeRecord(
        id="b",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="b",
        qualified_name="b",
        extractor="t",
        confidence=1.0,
        properties={},
    )
    c = NodeRecord(
        id="c",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="c",
        qualified_name="c",
        extractor="t",
        confidence=1.0,
        properties={},
    )
    nodes.extend([a, b, c])
    edges.extend(
        [
            EdgeRecord(
                id="e1",
                project_id=pid,
                edge_type=EdgeType.CALLS,
                source_id="a",
                target_id="b",
                extractor="t",
                confidence=1.0,
            ),
            EdgeRecord(
                id="e2",
                project_id=pid,
                edge_type=EdgeType.CALLS,
                source_id="b",
                target_id="c",
                extractor="t",
                confidence=1.0,
            ),
        ]
    )
    index = GraphIndex.build(nodes, edges)
    nh = neighborhood_subgraph(index, "a", direction="out", depth=2)
    assert "c" in nh["reachable_ids"]


def test_large_graph_truncation_flag() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, _ = _node(pid, "proj", NodeType.PROJECT, "root")
    nodes.append(proj)
    for i in range(300):
        pkg, ee = _node(pid, f"pkg{i}", NodeType.PACKAGE, f"p{i}", parent="proj")
        nodes.append(pkg)
        edges.extend(ee)
    index = GraphIndex.build(nodes, edges)
    _, _, meta = explore_build(index, None, {})
    assert meta.get("truncated") is True
    assert meta.get("truncation_reason")
