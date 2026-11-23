"""Views that hide test-scoped nodes unless include_tests is set."""

from __future__ import annotations

from ci_core.insights import GraphIndex
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_core.views.architecture import build as architecture_build
from ci_core.views.call_graph import build as call_graph_build
from ci_core.views.integrations import build as integrations_build


def _mod(
    pid: str,
    nid: str,
    *,
    path: str,
    layer: str = "service",
    ntype: NodeType = NodeType.MODULE,
) -> NodeRecord:
    return NodeRecord(
        id=nid,
        project_id=pid,
        node_type=ntype,
        name=path.rsplit("/", 1)[-1],
        qualified_name=path.replace("/", "."),
        source_path=path,
        extractor="t",
        confidence=1.0,
        properties={"layer": layer},
    )


def _pkg(pid: str, nid: str, name: str, *, subpackage: bool = False) -> NodeRecord:
    return NodeRecord(
        id=nid,
        project_id=pid,
        node_type=NodeType.PACKAGE,
        name=name,
        qualified_name=name,
        source_path=name,
        extractor="t",
        confidence=1.0,
        properties={"subpackage": subpackage} if subpackage else {},
    )


def _edge(pid: str, src: str, tgt: str, etype: EdgeType) -> EdgeRecord:
    return EdgeRecord(
        id=f"{src}-{etype.value}-{tgt}",
        project_id=pid,
        edge_type=etype,
        source_id=src,
        target_id=tgt,
        extractor="t",
        confidence=1.0,
    )


def test_integrations_hides_test_dependants() -> None:
    pid = "p1"
    ext = _mod(pid, "ext", path="httpx", layer="external", ntype=NodeType.EXTERNAL_SERVICE)
    app = _mod(pid, "appmod", path="app/services/foo.py", layer="service")
    test = _mod(pid, "testmod", path="tests/test_foo.py", layer="test")
    nodes = [ext, app, test]
    edges = [
        _edge(pid, app.id, ext.id, EdgeType.DEPENDS_ON),
        _edge(pid, test.id, ext.id, EdgeType.DEPENDS_ON),
    ]
    index = GraphIndex.build(nodes, edges)
    hidden, _, meta = integrations_build(index, None, {})
    assert meta.get("hidden_tests") is True
    ids = {n.id for n in hidden}
    assert ext.id in ids and app.id in ids
    assert test.id not in ids
    shown, _, _ = integrations_build(index, None, {"include_tests": True})
    assert test.id in {n.id for n in shown}


def test_call_graph_seed_skips_tests() -> None:
    pid = "p1"
    test_fn = NodeRecord(
        id="tfn",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="make_thing",
        qualified_name="tests.fixtures.make_thing",
        source_path="tests/fixtures.py",
        extractor="t",
        confidence=1.0,
        properties={"layer": "test"},
    )
    app_fn = NodeRecord(
        id="afn",
        project_id=pid,
        node_type=NodeType.FUNCTION,
        name="slugify",
        qualified_name="app.utils.slugify",
        source_path="app/utils.py",
        extractor="t",
        confidence=1.0,
        properties={"layer": "service"},
    )
    edges = [
        _edge(pid, test_fn.id, test_fn.id, EdgeType.CALLS),
        _edge(pid, app_fn.id, app_fn.id, EdgeType.CALLS),
        _edge(pid, test_fn.id, app_fn.id, EdgeType.CALLS),
    ]
    index = GraphIndex.build([test_fn, app_fn], edges)
    _nodes, _, meta = call_graph_build(index, None, {})
    assert meta.get("hidden_tests") is True
    assert meta["seed"] == app_fn.id


def test_architecture_omits_tests_package() -> None:
    pid = "p1"
    proj = NodeRecord(
        id="proj",
        project_id=pid,
        node_type=NodeType.PROJECT,
        name="demo",
        qualified_name="demo",
        extractor="t",
        confidence=1.0,
        properties={},
    )
    app = _pkg(pid, "pkg_app", "app")
    tests = _pkg(pid, "pkg_tests", "tests")
    app_mod = _mod(pid, "mod_app", path="app/main.py", layer="api")
    test_mod = _mod(pid, "mod_test", path="tests/test_main.py", layer="test")
    nodes = [proj, app, tests, app_mod, test_mod]
    edges = [
        _edge(pid, proj.id, app.id, EdgeType.CONTAINS),
        _edge(pid, proj.id, tests.id, EdgeType.CONTAINS),
        _edge(pid, app.id, app_mod.id, EdgeType.CONTAINS),
        _edge(pid, tests.id, test_mod.id, EdgeType.CONTAINS),
        _edge(pid, app_mod.id, test_mod.id, EdgeType.IMPORTS),
    ]
    index = GraphIndex.build(nodes, edges)
    nodes_out, _, meta = architecture_build(index, None, {})
    assert meta.get("hidden_tests") is True
    assert "pkg_tests" not in {n.id for n in nodes_out}
    with_tests, _, _ = architecture_build(index, None, {"include_tests": True})
    assert "pkg_tests" in {n.id for n in with_tests}
