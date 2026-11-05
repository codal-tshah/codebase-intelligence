from __future__ import annotations

import pytest

from ci_adapters_django import analyze_django_project
from ci_core.insights import GraphIndex, build_tour, compute_impact, find_path, search_nodes
from ci_core.models import NodeType
from ci_core.views import VIEW_IDS, build_view, view_catalog


@pytest.fixture(scope="module")
def index():
    from conftest import FIXTURE

    res = analyze_django_project("t", FIXTURE)
    return GraphIndex.build(res.nodes, res.edges)


def _id(index, node_type, name):
    return next(n.id for n in index.nodes.values() if n.node_type == node_type and n.name == name)


def test_fuzzy_search_ranks_exact_then_prefix_then_typo(index):
    names = [n.name for n, _ in search_nodes(index.nodes.values(), "list_items")]
    assert names[0] == "list_items"
    assert search_nodes(index.nodes.values(), "chekout")[0][0].name == "checkout"  # typo tolerated
    assert search_nodes(index.nodes.values(), "zzzzzz") == []


def test_shortest_path_between_endpoint_and_model(index):
    ep = _id(index, NodeType.ENDPOINT, "shop/items/<int:pk>/order/")
    order = _id(index, NodeType.MODEL, "Order")
    result = find_path(index, ep, order)
    assert result["found"]
    names = [index.nodes[i].name for i in result["node_ids"]]
    assert names[0] == "shop/items/<int:pk>/order/" and names[-1] == "Order"
    assert "create_order" in names and "checkout" in names


def test_path_not_found_for_unknown_node(index):
    assert find_path(index, "nope", "nada")["found"] is False


def test_impact_of_model_change_reaches_endpoints_tests_and_flags_migration(index):
    seeds = [n.id for n in index.nodes.values() if n.source_path == "shop/models.py"]
    report = compute_impact(index, seeds)
    affected = {a["name"] for a in report["affected"]}
    assert {"list_items", "checkout", "invalidate_item_cache"} <= affected
    assert any(e["name"] == "api/items/" for e in report["affected_endpoints"])
    assert any("migration" in note for note in report["notes"])
    assert report["risk"]["level"] in {"medium", "high"}
    assert {layer["id"] for layer in report["layers"]} >= {"api", "data", "service"}


def test_impact_of_leaf_change_is_small(index):
    seeds = [_id(index, NodeType.FUNCTION, "charge")]
    report = compute_impact(index, seeds, depth=1)
    assert {a["name"] for a in report["affected"]} == {"checkout"}
    assert report["risk"]["level"] == "low"


def test_impact_respects_depth(index):
    seeds = [_id(index, NodeType.FUNCTION, "charge")]
    shallow = {a["name"] for a in compute_impact(index, seeds, depth=1)["affected"]}
    deep = {a["name"] for a in compute_impact(index, seeds, depth=3)["affected"]}
    assert shallow < deep
    assert "create_order" in deep


def test_tour_orders_entry_to_data_to_tests(index):
    steps = build_tour(index)
    titles = [s["title"] for s in steps]
    assert titles[0].startswith("Entry points")
    assert titles.index("URL routing") < titles.index("Data models") < titles.index("Tests")
    for step in steps:
        assert step["node_ids"] and all(nid in index.nodes for nid in step["node_ids"])
    routing = next(s for s in steps if s["title"] == "URL routing")
    assert all(index.nodes[n].node_type in (NodeType.MODULE, NodeType.ENDPOINT) for n in routing["node_ids"])


@pytest.mark.parametrize("view", VIEW_IDS)
def test_every_view_builds_consistent_payload(index, view):
    payload = build_view(index, view)
    ids = {n.id for n in payload.nodes}
    available = {v["id"]: v["available"] for v in view_catalog(index)}
    assert bool(ids) == available[view], f"{view}: empty={not ids} available={available[view]}"
    assert all(e.source in ids and e.target in ids for e in payload.edges)
    assert payload.metadata["node_count"] == len(payload.nodes)


def test_architecture_view_rolls_up_package_dependencies(index):
    payload = build_view(index, "architecture")
    labels = {n.id: n.label for n in payload.nodes}
    pairs = {(labels[e.source], labels[e.target]) for e in payload.edges}
    assert ("demo", "shop") in pairs
    edge = next(e for e in payload.edges if labels[e.source] == "demo")
    assert edge.properties["weight"] >= 1


def test_er_view_has_models_fields_and_relations(index):
    payload = build_view(index, "er")
    kinds = {n.node_type for n in payload.nodes}
    assert {"Model", "Field"} <= kinds
    assert any(e.edge_type == "FK_TO" for e in payload.edges)


def test_api_flow_focus_follows_one_request(index):
    ep = _id(index, NodeType.ENDPOINT, "shop/items/<int:pk>/order/")
    payload = build_view(index, "api-flow", ep)
    labels = {n.label for n in payload.nodes}
    assert {"create_order", "checkout", "Order"} <= labels
    assert payload.metadata["focused"] is True
