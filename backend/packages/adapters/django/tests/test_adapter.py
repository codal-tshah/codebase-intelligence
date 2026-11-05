from __future__ import annotations

import pytest

from ci_adapters_django import analyze_django_project, detect_django
from ci_core.models import EdgeType, NodeType


@pytest.fixture(scope="module")
def result():
    from conftest import FIXTURE

    return analyze_django_project("test-project", FIXTURE)


def _by_name(result, node_type, name):
    return next(n for n in result.nodes if n.node_type == node_type and n.name == name)


def _edges(result, edge_type, source=None, target=None):
    names = {n.id: n.name for n in result.nodes}
    return [
        e
        for e in result.edges
        if e.edge_type == edge_type
        and (source is None or names[e.source_id] == source)
        and (target is None or names[e.target_id] == target)
    ]


def test_detect_django_fixture(fixture_root):
    assert detect_django(fixture_root)


def test_urls_and_models_extracted(result):
    assert result.is_django
    endpoints = [n for n in result.nodes if n.node_type == NodeType.ENDPOINT]
    assert any(n.name == "api/items/" for n in endpoints)
    assert any(n.name == "Item" for n in result.nodes if n.node_type == NodeType.MODEL)
    assert [e for e in result.edges if e.edge_type == EdgeType.ROUTES_TO]
    assert [e for e in result.edges if e.edge_type == EdgeType.READS_MODEL]


def test_include_prefixes_are_joined(result):
    routes = {n.name for n in result.nodes if n.node_type == NodeType.ENDPOINT}
    assert "shop/categories/" in routes
    assert "shop/items/<int:pk>/order/" in routes
    assert "categories/" not in routes  # bare child route must not leak


def test_http_methods_from_decorators_and_class_views(result):
    order = _by_name(result, NodeType.ENDPOINT, "shop/items/<int:pk>/order/")
    assert order.properties["methods"] == ["POST"]
    detail = _by_name(result, NodeType.ENDPOINT, "shop/items/<int:pk>/detail/")
    assert detail.properties["methods"] == ["GET"]
    assert _edges(result, EdgeType.ROUTES_TO, "shop/items/<int:pk>/detail/", "ItemDetailView")


def test_foreign_keys_resolve_without_duplicate_models(result):
    assert _edges(result, EdgeType.FK_TO, "Item", "Category")
    assert _edges(result, EdgeType.FK_TO, "Order", "Item")  # string "shop.Item"
    assert _edges(result, EdgeType.FK_TO, "Order", "User")  # settings.AUTH_USER_MODEL -> auth.User stub
    names = [n.name for n in result.nodes if n.node_type == NodeType.MODEL]
    assert names.count("Category") == 1 and names.count("Item") == 1
    user = _by_name(result, NodeType.MODEL, "User")
    assert user.properties["inferred"] is True


def test_model_inheritance_and_abstract(result):
    base = _by_name(result, NodeType.MODEL, "TimeStamped")
    assert base.properties["abstract"] is True
    assert _edges(result, EdgeType.DEPENDS_ON, "Item", "TimeStamped")


def test_relative_imports_and_calls_resolve(result):
    assert _edges(result, EdgeType.IMPORTS, "shop/views", "shop/models")
    assert _edges(result, EdgeType.IMPORTS, "shop/urls", "shop/views")
    assert _edges(result, EdgeType.CALLS, "create_order", "checkout")
    assert _edges(result, EdgeType.CALLS, "checkout", "charge")
    # method callers must be attributed to the method, not a garbled name
    assert _edges(result, EdgeType.CALLS, "ItemDetailView.get", "get_item")


def test_orm_read_and_write_are_distinguished(result):
    assert _edges(result, EdgeType.READS_MODEL, "checkout", "Item")
    assert _edges(result, EdgeType.WRITES_MODEL, "checkout", "Order")
    assert _edges(result, EdgeType.READS_MODEL, "ItemDetailView", "Item")  # model = Item


def test_signals_middleware_admin_and_integrations(result):
    assert _edges(result, EdgeType.SUBSCRIBES, "invalidate_item_cache", "Item")
    mw = _by_name(result, NodeType.MIDDLEWARE, "AuditMiddleware")
    assert mw.properties["layer"] == "middleware"
    assert _edges(result, EdgeType.MIDDLEWARE, "demo/settings", "AuditMiddleware")
    assert _edges(result, EdgeType.DEPENDS_ON, "ItemAdmin", "Item")
    assert _edges(result, EdgeType.DEPENDS_ON, "shop/services", "Stripe")
    assert any(n.node_type == NodeType.EXTERNAL_SERVICE and n.name == "Stripe" for n in result.nodes)


def test_every_code_node_has_layer_complexity_and_summary(result):
    for node in result.nodes:
        if node.node_type in (NodeType.FUNCTION, NodeType.CLASS, NodeType.MODEL, NodeType.ENDPOINT, NodeType.MODULE):
            assert node.properties.get("layer"), node.name
            assert node.properties.get("summary"), node.name
        if node.node_type in (NodeType.FUNCTION, NodeType.MODEL, NodeType.MODULE):
            assert node.properties.get("complexity") in {"simple", "moderate", "complex"}
    layers = {n.properties.get("layer") for n in result.nodes}
    assert {"api", "data", "service", "middleware", "test", "config"} <= layers


def test_node_and_edge_ids_are_unique(result):
    assert len({n.id for n in result.nodes}) == len(result.nodes)
    assert len({e.id for e in result.edges}) == len(result.edges)
    ids = {n.id for n in result.nodes}
    assert all(e.source_id in ids and e.target_id in ids for e in result.edges)


def test_broken_file_is_reported_not_fatal(project_copy):
    (project_copy / "shop" / "broken.py").write_text("def oops(:\n", encoding="utf-8")
    res = analyze_django_project("p", project_copy)
    assert any("broken.py" in w for w in res.warnings)
    assert any(n.name == "Item" for n in res.nodes)  # rest of the project is still analysed


def test_ciignore_excludes_files(project_copy):
    (project_copy / ".ciignore").write_text("shop/tests.py\n", encoding="utf-8")
    res = analyze_django_project("p", project_copy)
    assert "shop/tests.py" not in res.files
    assert "shop/views.py" in res.files
