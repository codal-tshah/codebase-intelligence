"""Explore view and neighborhood API logic."""

from __future__ import annotations

from ci_core.insights import GraphIndex, neighborhood_subgraph
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_core.views.explore import build as explore_build, underlying_between


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


def test_explore_parent_id_and_depth() -> None:
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
    nout, _, _ = explore_build(index, None, {"expanded": ["pkg1"]})
    by_id = {n.id: (n.properties or {}) for n in nout}
    # Project root is not always in the visible set (only top-level packages are roots).
    assert by_id["pkg1"].get("parent_id") is None
    assert by_id["mod1"].get("parent_id") == "pkg1"
    assert int(by_id["pkg1"].get("depth", -1)) == 0
    assert int(by_id["mod1"].get("depth", -1)) == 1


def test_explore_truncated_children_offset() -> None:
    """More structural children than one page: truncated_children and offset param."""
    from ci_core.views.explore import STRUCT_CHILD_PAGE

    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, _ = _node(pid, "proj", NodeType.PROJECT, "root")
    nodes.append(proj)
    pkg, ee = _node(pid, "pkg1", NodeType.PACKAGE, "app", parent="proj")
    nodes.append(pkg)
    edges.extend(ee)
    n_extra = STRUCT_CHILD_PAGE + 5
    for i in range(n_extra):
        # Zero-pad so lexicographic sort matches numeric order (children are sorted by name).
        mod, ee2 = _node(pid, f"mod{i:04d}", NodeType.MODULE, f"m{i:04d}.py", parent="pkg1")
        nodes.append(mod)
        edges.extend(ee2)
    index = GraphIndex.build(nodes, edges)
    nout, _, _ = explore_build(index, None, {"expanded": ["pkg1"]})
    props_pkg = next((n.properties or {} for n in nout if n.id == "pkg1"), {})
    assert int(props_pkg.get("truncated_children", 0)) == 5
    nout2, _, _ = explore_build(
        index,
        None,
        {"expanded": ["pkg1"], "extra_child_offsets": [f"pkg1={STRUCT_CHILD_PAGE}"]},
    )
    ids2 = {n.id for n in nout2}
    assert "mod0080" in ids2
    props2 = next((n.properties or {} for n in nout2 if n.id == "pkg1"), {})
    assert int(props2.get("truncated_children", 0)) == 0


def test_underlying_between_matches_aggregate() -> None:
    pid = "p1"
    nodes: list[NodeRecord] = []
    edges: list[EdgeRecord] = []
    proj, _ = _node(pid, "proj", NodeType.PROJECT, "root")
    nodes.append(proj)
    pkg_a, ee = _node(pid, "pa", NodeType.PACKAGE, "a", parent="proj")
    pkg_b, ee2 = _node(pid, "pb", NodeType.PACKAGE, "b", parent="proj")
    nodes.extend([pkg_a, pkg_b])
    edges.extend(ee + ee2)
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
    index = GraphIndex.build(nodes, edges)
    raw = underlying_between(index, "pa", "pb", "")
    assert len(raw) == 1
    assert raw[0]["id"] == "call1"


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


def test_collapsing_parent_hides_expanded_descendants_and_restores_them():
    """Regression: collapsing a package whose child module is expanded must actually collapse."""
    from ci_core.insights import GraphIndex
    from ci_core.models import NodeType
    from ci_core.views import build_view
    from ci_indexer import analyze_project
    from conftest import FULLSTACK

    res = analyze_project("t", FULLSTACK).result
    index = GraphIndex.build(res.nodes, res.edges)
    top = build_view(index, "explore")
    pkg = next(n for n in top.nodes if n.properties.get("explore_expandable") and n.node_type == "Package")
    opened = build_view(index, "explore", params={"expanded": pkg.id})
    child = next(n for n in opened.nodes if n.properties.get("parent_id") == pkg.id and n.properties.get("explore_expandable"))
    both = build_view(index, "explore", params={"expanded": f"{pkg.id},{child.id}"})
    inner = {n.id for n in both.nodes if n.properties.get("parent_id") == child.id}
    assert inner, "child should show its own children when both are expanded"

    # parent collapsed, child still in the expanded list -> nothing below the parent is shown
    collapsed = build_view(index, "explore", params={"expanded": child.id})
    ids = {n.id for n in collapsed.nodes}
    assert child.id not in ids and not (inner & ids)
    assert {n.id for n in collapsed.nodes} == {n.id for n in top.nodes}
    assert NodeType.PACKAGE  # keep import used
