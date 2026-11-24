from __future__ import annotations

from pathlib import Path

import pytest

from ci_adapters_typescript import ANALYZER
from ci_core.analysis import AnalysisResult
from ci_core.models import EdgeType, NodeType
from ci_indexer.analyzers import analyze_project
from ci_parsers import list_source_files

FIXTURES = Path(__file__).resolve().parents[4] / "benchmarks" / "fixtures"


@pytest.fixture(scope="module")
def next_app_result():
    root = FIXTURES / "next_app_router_min"
    files = list_source_files(root, ANALYZER.extensions)
    return ANALYZER.analyze("next-app", root, files)


@pytest.fixture(scope="module")
def next_pages_result():
    root = FIXTURES / "next_pages_router"
    files = list_source_files(root, ANALYZER.extensions)
    return ANALYZER.analyze("next-pages", root, files)


@pytest.fixture(scope="module")
def workspace_npm_result():
    root = FIXTURES / "workspace_npm"
    files = list_source_files(root, ANALYZER.extensions)
    return ANALYZER.analyze("ws-npm", root, files)


@pytest.fixture(scope="module")
def mixed_result():
    root = FIXTURES / "mixed_monorepo"
    return analyze_project("mixed", root).result


def _eps(result, path: str | None = None):
    eps = [n for n in result.nodes if n.node_type == NodeType.ENDPOINT]
    if path:
        eps = [n for n in eps if n.properties.get("route") == path or n.name == path]
    return eps


def _by_route(result, route: str):
    return [n for n in result.nodes if n.properties.get("route") == route and n.node_type == NodeType.COMPONENT]


def test_next_app_layout_contains_page(next_app_result):
    layouts = [
        e
        for e in next_app_result.edges
        if e.edge_type == EdgeType.CONTAINS and (e.properties or {}).get("relation") == "layout"
    ]
    assert len(layouts) >= 1


def test_next_app_framework_and_routes(next_app_result):
    assert "nextjs" in next_app_result.frameworks
    routes = {n.properties["route"] for n in _eps(next_app_result)}
    assert "/api/items" in routes
    get_items = [n for n in _eps(next_app_result, "/api/items") if "GET" in (n.properties.get("methods") or [])]
    assert get_items
    home = _by_route(next_app_result, "/")
    assert home and home[0].properties.get("boundary") == "client"
    mw = [n for n in next_app_result.nodes if n.node_type == NodeType.MIDDLEWARE]
    assert mw and "matcher" in mw[0].properties


def test_next_app_paths_normalize_groups_and_dynamic(next_app_result):
    pages = {
        n.properties["route"]
        for n in next_app_result.nodes
        if n.node_type == NodeType.COMPONENT and n.properties.get("route")
    }
    assert "/settings" in pages
    assert any("slug" in r for r in pages)


def test_next_pages_api_any_method(next_pages_result):
    assert "nextjs" in next_pages_result.frameworks
    api = _eps(next_pages_result, "/api/hello")
    assert len(api) == 1
    assert api[0].properties["methods"] == ["ANY"]
    blog = _by_route(next_pages_result, "/blog/[slug]")
    assert blog


def test_workspace_package_count_and_import(workspace_npm_result):
    pkgs = [n for n in workspace_npm_result.nodes if n.node_type == NodeType.PACKAGE]
    names = {n.properties.get("npm_name") or n.name for n in pkgs}
    assert "@fixture/shared" in names or any("@fixture" in (x or "") for x in names)
    imports = {
        (a, b)
        for e in workspace_npm_result.edges
        if e.edge_type == EdgeType.IMPORTS
        for a, b in [(_n(workspace_npm_result, e.source_id), _n(workspace_npm_result, e.target_id))]
    }
    assert any("greet" in t or "shared" in t for _, t in imports)


def _n(result: AnalysisResult, nid: str) -> str:
    return next(n.name for n in result.nodes if n.id == nid)


def test_mixed_monorepo_cross_package_and_http(mixed_result):
    assert "nextjs" in mixed_result.frameworks
    imports = [e for e in mixed_result.edges if e.edge_type == EdgeType.IMPORTS]
    assert imports
    assert any("/items" in (c.url or "") for c in mixed_result.http_calls)
