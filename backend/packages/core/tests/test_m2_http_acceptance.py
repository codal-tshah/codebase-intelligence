"""Milestone 2.2 acceptance: cross-stack HTTP and monorepo integration (fixture-backed)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ci_core.evidence import classify_edge, classify_http_call_record
from ci_core.models import EdgeType
from ci_indexer.analyzers import analyze_project

FIXTURES = Path(__file__).resolve().parents[3] / "benchmarks" / "fixtures"


@pytest.fixture(scope="module")
def mixed():
    return analyze_project("mixed-m2", FIXTURES / "mixed_monorepo").result


@pytest.fixture(scope="module")
def duplicate_routes():
    return analyze_project("dup-routes", FIXTURES / "duplicate_routes_monorepo").result


def _node_map(result):
    return {n.id: n for n in result.nodes}


def test_mixed_monorepo_http_call_to_fastapi(mixed):
    http_edges = [e for e in mixed.edges if e.edge_type == EdgeType.HTTP_CALLS]
    assert len(http_edges) == 1
    edge = http_edges[0]
    nodes = _node_map(mixed)
    source = nodes[edge.source_id]
    target = nodes[edge.target_id]
    assert source.name == "loadItems"
    assert source.source_path == "apps/next-app/app/page.tsx"
    assert edge.start_line == 4
    assert target.name == "/items"
    assert target.source_path == "api/app/main.py"
    assert target.properties.get("methods") == ["GET"]
    assert edge.properties.get("method") == "GET"
    assert "items" in edge.properties.get("url", "")
    assert edge.properties.get("match_variant") == "literal"
    ev = classify_edge(edge)
    assert ev["tier"] == "high"
    assert ev["reason_code"] == "http_literal_route_match"
    rec = next(r for r in source.properties.get("http_calls", []) if r.get("endpoint_id") == target.id)
    assert classify_http_call_record(rec)["tier"] == "high"


def test_duplicate_routes_prefers_service_near_caller(duplicate_routes):
    nodes = _node_map(duplicate_routes)
    shop = next(
        e
        for e in duplicate_routes.edges
        if e.edge_type == EdgeType.HTTP_CALLS and nodes[e.source_id].source_path == "apps/shop/web/page.tsx"
    )
    assert nodes[shop.target_id].source_path == "apps/shop/api/app/main.py"
    assert shop.properties.get("match_variant") == "literal"
    assert classify_edge(shop)["tier"] == "high"


def test_duplicate_routes_ambiguous_when_paths_tie(duplicate_routes):
    nodes = _node_map(duplicate_routes)
    gw_edge = next(
        e
        for e in duplicate_routes.edges
        if e.edge_type == EdgeType.HTTP_CALLS and nodes[e.source_id].source_path == "apps/shared/gateway.ts"
    )
    assert gw_edge.properties.get("match_variant") == "ambiguous"
    assert gw_edge.confidence <= 0.68
    assert classify_edge(gw_edge)["tier"] == "medium"
    assert classify_edge(gw_edge)["reason_code"] == "http_ambiguous_route_match"


@pytest.mark.parametrize(
    "name",
    [
        "next_app_router_min",
        "next_pages_router",
        "workspace_npm",
        "workspace_pnpm",
        "mixed_monorepo",
    ],
)
def test_fixture_index_smoke_and_timing(name: str):
    root = FIXTURES / name
    t0 = time.perf_counter()
    pa = analyze_project(f"perf-{name}", root)
    elapsed = time.perf_counter() - t0
    r = pa.result
    assert r.nodes and r.stats.get("nodes", len(r.nodes)) > 0
    assert "typescript:3" in pa.version or "python:" in pa.version
    assert elapsed < 30.0
    assert elapsed  # recorded in CI output via capsys if needed
