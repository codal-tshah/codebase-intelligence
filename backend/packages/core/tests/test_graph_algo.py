from __future__ import annotations

import pytest

from ci_core import graph_algo
from ci_core.insights import GraphIndex
from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
from ci_core.suggestions import suggest


def _mod(name: str) -> NodeRecord:
    return NodeRecord(id=name, project_id="p", node_type=NodeType.MODULE, name=name,
                      source_path=f"app/{name}.py", extractor="t")


def _index(
    names: list[str],
    edges: list[tuple[str, str, EdgeType]],
    *,
    props: dict[tuple[str, str, EdgeType], dict] | None = None,
) -> GraphIndex:
    props = props or {}
    recs = [
        EdgeRecord(
            id=f"{s}>{t}:{k.value}", project_id="p", edge_type=k, source_id=s, target_id=t, extractor="t",
            properties=props.get((s, t, k), {}),
        )
        for s, t, k in edges
    ]
    return GraphIndex.build([_mod(n) for n in names], recs)


IMP = EdgeType.IMPORTS


@pytest.fixture(params=["rustworkx", "networkx"])
def backend(request, monkeypatch):
    pytest.importorskip(request.param)
    monkeypatch.setattr(graph_algo, "_backend", lambda: request.param)
    return request.param


def test_scc_finds_three_node_cycle_and_ignores_dag_and_self_loops(backend):
    idx = _index(list("abcdef"), [("a", "b", IMP), ("b", "c", IMP), ("c", "a", IMP),
                                  ("c", "d", IMP), ("d", "e", IMP), ("f", "f", IMP)])
    assert graph_algo.strongly_connected_components(idx) == [["a", "b", "c"]]
    assert graph_algo.backend_name() == backend


def test_scc_largest_first_and_edge_type_filter(backend):
    idx = _index(list("abcde"), [("a", "b", IMP), ("b", "a", IMP), ("c", "d", IMP), ("d", "e", IMP), ("e", "c", IMP),
                                 ("a", "c", EdgeType.CALLS), ("e", "a", EdgeType.CALLS)])
    assert graph_algo.strongly_connected_components(idx, {IMP}) == [["c", "d", "e"], ["a", "b"]]
    # CALLS edges join the two loops into one component on the full dependency subgraph
    assert graph_algo.strongly_connected_components(idx) == [["a", "b", "c", "d", "e"]]


def test_containment_does_not_make_cycles(backend):
    idx = _index(["a", "b"], [("a", "b", EdgeType.CONTAINS), ("b", "a", EdgeType.CONTAINS)])
    assert graph_algo.strongly_connected_components(idx) == []


def test_shortest_cycle_is_a_real_cycle(backend):
    idx = _index(list("abcd"), [("a", "b", IMP), ("b", "c", IMP), ("c", "a", IMP), ("a", "d", IMP), ("d", "b", IMP)])
    (cyc,) = graph_algo.dependency_cycles(idx, {IMP})
    assert cyc["size"] == 4
    path = cyc["cycle"]
    assert path[0] == "a" and len(path) == 3  # a -> b -> c -> a beats a -> d -> b -> c -> a
    edges = {(e.source_id, e.target_id) for e in idx.edges}
    assert all((path[i], path[(i + 1) % len(path)]) in edges for i in range(len(path)))


def test_backends_agree(monkeypatch):
    pytest.importorskip("rustworkx")
    pytest.importorskip("networkx")
    names = [f"m{i}" for i in range(40)]
    edges = [(names[i], names[(i * 7 + 3) % 40], IMP) for i in range(40)] + [(names[i], names[(i + 1) % 40], IMP) for i in range(0, 40, 3)]
    idx = _index(names, edges)
    results = []
    for name in ("rustworkx", "networkx"):
        monkeypatch.setattr(graph_algo, "_backend", lambda name=name: name)
        results.append(graph_algo.strongly_connected_components(idx))
    assert results[0] == results[1] and results[0]


def test_suggest_reports_long_import_cycles_and_keeps_pair_wording():
    idx = _index(list("abcdxy"), [("a", "b", IMP), ("b", "c", IMP), ("c", "a", IMP), ("x", "y", IMP), ("y", "x", IMP),
                                  ("c", "d", IMP)])
    cycles = [s for s in suggest(idx) if s["kind"] == "cycle"]
    titles = sorted(c["title"] for c in cycles)
    assert titles == [
        "3 modules are tied in import cycles, e.g. a -> b -> c -> a",
        "x and y import each other",
    ]
    triple = next(c for c in cycles if c["title"].startswith("3 modules"))
    assert {n["name"] for n in triple["nodes"]} == {"a", "b", "c"} and triple["severity"] == "medium"


def test_suggest_ignores_init_barrel_hub_for_import_cycles():
    names = ["pkg.__init__", *list("abc")]
    idx = _index(
        names,
        [
            ("pkg.__init__", "a", IMP),
            ("pkg.__init__", "b", IMP),
            ("pkg.__init__", "c", IMP),
            ("a", "pkg.__init__", IMP),
            ("b", "pkg.__init__", IMP),
            ("c", "pkg.__init__", IMP),
            ("a", "b", IMP),
            ("b", "a", IMP),
        ],
    )
    cycles = [s for s in suggest(idx) if s["kind"] == "cycle"]
    assert len(cycles) == 1
    assert cycles[0]["title"].startswith("a and b import each other")


def test_suggest_marks_wide_cycles_high_and_truncates_the_path():
    names = [f"m{i}" for i in range(8)]
    idx = _index(names, [(names[i], names[(i + 1) % 8], IMP) for i in range(8)])
    (cyc,) = [s for s in suggest(idx) if s["kind"] == "cycle"]
    assert cyc["severity"] == "high" and "8 modules" in cyc["title"] and "..." in cyc["title"]


def test_suggest_ignores_type_only_and_lazy_import_edges_for_cycles():
    ab_type_only = _index(
        list("ab"),
        [("a", "b", IMP), ("b", "a", IMP)],
        props={("a", "b", IMP): {"import_kind": "type_only"}},
    )
    lazy_back_edge = _index(
        ["p", "q"],
        [("p", "q", IMP), ("q", "p", IMP)],
        props={("q", "p", IMP): {"import_kind": "lazy"}},
    )
    assert not [s for s in suggest(ab_type_only) if s["kind"] == "cycle"]
    assert not [s for s in suggest(lazy_back_edge) if s["kind"] == "cycle"]
    (runtime,) = [s for s in suggest(_index(["x", "y"], [("x", "y", IMP), ("y", "x", IMP)])) if s["kind"] == "cycle"]
    assert runtime["title"].startswith("x and y")
