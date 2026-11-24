from __future__ import annotations

from ci_core.analysis import match_endpoint, route_segments
from ci_core.models import NodeRecord, NodeType


def _ep(route, methods=None, path="api/urls.py"):
    return NodeRecord(
        id=route + str(methods),
        project_id="p",
        node_type=NodeType.ENDPOINT,
        name=route,
        source_path=path,
        extractor="t",
        properties={"route": route, "methods": methods or []},
    )


def test_route_segments_normalise_framework_params():
    assert route_segments("api/items/<int:pk>/") == ("api", "items", "{}")
    assert route_segments("/api/items/{item_id}") == ("api", "items", "{}")
    assert route_segments("/users/:id") == ("users", "{}")
    assert route_segments("/projects/${x}/summary?x=1") == ("projects", "{}", "summary")
    assert route_segments("http://localhost:8000/a/[slug]") == ("a", "{}")


def test_match_prefers_literals_methods_and_proxy_prefix():
    eps = [_ep("/items/{id}", ["GET"]), _ep("/items/search", ["GET"]), _ep("/items", ["POST"])]
    assert match_endpoint("/items/search", "GET", eps)[0].name == "/items/search"
    assert match_endpoint("/items/42", "GET", eps)[0].name == "/items/{id}"
    assert match_endpoint("/items/42", "GET", eps)[2] == "literal"
    assert match_endpoint("/items", "GET", eps) is None  # method mismatch
    hit, conf, variant = match_endpoint("/api/items", "POST", eps)  # dev proxy prefix dropped
    assert hit.name == "/items" and conf < 0.9 and variant == "proxy_prefix"


def test_match_endpoint_prefers_specific_method_over_any():
    any_ep = _ep("/api/hello", ["ANY"], path="pages/api/hello.ts")
    get_ep = _ep("/api/hello", ["GET"], path="app/api/hello/route.ts")
    hit = match_endpoint("/api/hello", "GET", [any_ep, get_ep])
    assert hit is not None and hit[0] is get_ep and hit[2] == "literal"


def test_match_endpoint_marks_ambiguous_duplicate_routes():
    a = _ep("/orders", ["GET"], path="apps/shop/api/app/main.py")
    b = _ep("/orders", ["GET"], path="apps/billing/api/app/main.py")
    hit = match_endpoint("/orders", "GET", [a, b], near="apps/shop/web/page.tsx")
    assert hit is not None
    assert hit[0] is a
    assert hit[2] == "literal"
    amb = match_endpoint("/orders", "GET", [a, b], near="apps/shared/gateway.ts")
    assert amb is not None
    assert amb[2] == "ambiguous" and amb[1] <= 0.68


def test_match_endpoint_accepts_any_method_pages_api():
    eps = [_ep("/api/hello", ["ANY"])]
    hit = match_endpoint("/api/hello", "POST", eps)
    assert hit is not None and hit[0].name == "/api/hello"


def test_match_tie_breaks_on_nearest_service():
    a = _ep("/orders", ["GET"], path="svc_a/routes.py")
    b = _ep("/orders", ["GET"], path="svc_b/routes.py")
    assert match_endpoint("/orders", "GET", [a, b], near="svc_b/web/client.ts")[0] is b
