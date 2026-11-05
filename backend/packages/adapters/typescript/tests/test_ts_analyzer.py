from __future__ import annotations

import pytest

from ci_adapters_typescript import ANALYZER
from ci_core.models import EdgeType, NodeType
from ci_parsers import list_source_files


@pytest.fixture(scope="module")
def result(request):
    from conftest import FULLSTACK

    files = list_source_files(FULLSTACK, ANALYZER.extensions)
    return ANALYZER.analyze("ts", FULLSTACK, files)


def _by_name(result, name, node_type=None):
    return [n for n in result.nodes if n.name == name and (node_type is None or n.node_type == node_type)]


def _edges(result, edge_type):
    names = {n.id: n.name for n in result.nodes}
    return {(names[e.source_id], names[e.target_id]) for e in result.edges if e.edge_type == edge_type}


def test_components_hooks_and_roles(result):
    comps = {n.name for n in result.nodes if n.node_type == NodeType.COMPONENT}
    assert {"App", "ItemList", "ItemCard", "ItemPage"} <= comps
    hook = _by_name(result, "useItems")[0]
    assert hook.properties["role"] == "hooks" and hook.properties["layer"] == "ui"


def test_jsx_render_edges_resolve_through_aliases_and_default_exports(result):
    renders = _edges(result, EdgeType.RENDERS)
    assert ("App", "ItemList") in renders  # via tsconfig "@/*" path alias
    assert ("App", "ItemPage") in renders  # default export
    assert ("ItemList", "ItemCard") in renders
    assert ("web/src/main", "App") in renders  # module-level render


def test_calls_through_object_api_client_and_hooks(result):
    calls = _edges(result, EdgeType.CALLS)
    assert ("ItemList", "useItems") in calls
    assert ("useItems", "api.listItems") in calls
    assert ("ItemPage", "api.getItem") in calls


def test_http_calls_are_collected_with_methods(result):
    calls = {(c.method, c.url) for c in result.http_calls}
    assert ("GET", "/api/items/") in calls
    assert ("GET", "/api/items/${x}") in calls
    assert ("POST", "/api/orders/") in calls
    assert ("POST", "https://api.stripe.com/v1/payment_intents") in calls


def test_express_routes_with_mount_prefix_middleware_and_inline_handler(result):
    eps = {(tuple(n.properties["methods"]), n.name): n for n in result.nodes if n.node_type == NodeType.ENDPOINT}
    assert (("GET",), "/v1/orders") in eps and (("POST",), "/v1/orders") in eps
    routes = _edges(result, EdgeType.ROUTES_TO)
    assert ("/v1/orders", "listOrders") in routes and ("/v1/orders", "createOrder") in routes
    deps = {(a, b) for a, b in _edges(result, EdgeType.DEPENDS_ON)}
    assert ("/v1/orders", "requireAuth") in deps
    # inline arrow handler: calls are attributed to the endpoint itself
    assert ("/v1/orders/:id", "listOrders") in _edges(result, EdgeType.CALLS)


def test_nest_controller_routes_guards_and_constructor_injection(result):
    routes = _edges(result, EdgeType.ROUTES_TO)
    assert ("/users", "UsersController.findAll") in routes
    assert ("/users/:id", "UsersController.findOne") in routes
    assert ("UsersController", "UsersService") in _edges(result, EdgeType.INJECTS)
    assert ("UsersController.findAll", "UsersService.findAll") in _edges(result, EdgeType.CALLS)
    assert ("/users", "AuthGuard") in _edges(result, EdgeType.DEPENDS_ON)


def test_react_router_routes_mark_pages(result):
    page = _by_name(result, "ItemPage", NodeType.COMPONENT)[0]
    assert page.properties["route"] == "/items/:id"
    assert "page" in page.properties["tags"]


def test_sdk_imports_become_external_services(result):
    services = {n.name for n in result.nodes if n.node_type == NodeType.EXTERNAL_SERVICE}
    assert "Redis" in services


def test_files_have_fingerprints_and_language(result):
    entry = result.files["web/src/App.tsx"]
    assert entry["language"] == "typescript" and entry["structural"] and entry["sha"]
    assert {"react", "express", "nestjs"} <= set(result.frameworks)


def test_ids_unique_and_edges_reference_nodes(result):
    ids = [n.id for n in result.nodes]
    assert len(ids) == len(set(ids))
    known = set(ids)
    assert all(e.source_id in known and e.target_id in known for e in result.edges)
