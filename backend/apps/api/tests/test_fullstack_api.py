"""API-level checks on the fullstack fixture (cross-stack HTTP, components, models, impact)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ci_api.main import app


@pytest.fixture
def fs_client(data_dir, fullstack_copy):
    c = TestClient(app)
    res = c.post("/projects/analyze", json={"path": str(fullstack_copy)})
    assert res.status_code == 200, res.text
    c.project_id = res.json()["project"]["id"]
    return c


def test_fullstack_summary_and_views(fs_client):
    summary = fs_client.get(f"/projects/{fs_client.project_id}/summary").json()
    stack = " ".join(summary.get("techStack", [])).lower()
    assert "fastapi" in stack or "react" in stack
    catalog = {v["id"]: v for v in fs_client.get(f"/projects/{fs_client.project_id}/views").json()}
    assert catalog["components"]["available"] and catalog["components"]["count"] >= 4
    assert catalog["api-flow"]["available"]


def test_fullstack_models_and_impact_reaches_ui(fs_client):
    models = fs_client.get(f"/projects/{fs_client.project_id}/models").json()["models"]
    item = next(m for m in models if m["name"] == "Item")
    assert item["fields"] and item.get("read_by")
    report = fs_client.post(
        f"/projects/{fs_client.project_id}/impact",
        json={"node_ids": [item["id"]], "depth": 6},
    ).json()
    names = {a["name"] for a in report["affected"]}
    assert "ItemList" in names and "api.listItems" in names


def test_fullstack_endpoints_list_callers(fs_client):
    body = fs_client.get(f"/projects/{fs_client.project_id}/endpoints").json()
    route = next(e for e in body["endpoints"] if e["route"] == "/api/items")
    assert any(c.get("name") == "api.listItems" for c in route.get("callers", []))


def test_explore_underlying_edges_capped_only_when_truncated(fs_client):
    pid = fs_client.project_id
    top = fs_client.get(f"/projects/{pid}/graph/explore").json()
    arcs = [e for e in top["edges"] if e["edge_type"] != "CONTAINS" and (e.get("properties") or {}).get("weight", 1) >= 1]
    assert arcs, "top-level explore should aggregate cross-package dependencies"
    arc = max(arcs, key=lambda e: (e.get("properties") or {}).get("weight", 1))
    params = {"source": arc["source"], "target": arc["target"]}
    full = fs_client.get(f"/projects/{pid}/graph/edges", params=params).json()
    n = len(full["edges"])
    assert n >= 1 and full["capped"] is False
    exact = fs_client.get(f"/projects/{pid}/graph/edges", params={**params, "limit": n}).json()
    assert len(exact["edges"]) == n and exact["capped"] is False  # exactly limit rows is not truncation
    if n > 1:
        cut = fs_client.get(f"/projects/{pid}/graph/edges", params={**params, "limit": n - 1}).json()
        assert len(cut["edges"]) == n - 1 and cut["capped"] is True


def test_graph_lookup_routes_404_on_unknown_nodes(fs_client):
    pid = fs_client.project_id
    assert fs_client.get(f"/projects/{pid}/graph/neighborhood", params={"node_id": "nope"}).status_code == 404
    assert fs_client.get(f"/projects/{pid}/graph/neighborhood", params={"node_id": "x", "depth": 9}).status_code == 422
    assert fs_client.get(f"/projects/{pid}/graph/edges", params={"source": "a", "target": "b"}).status_code == 404
