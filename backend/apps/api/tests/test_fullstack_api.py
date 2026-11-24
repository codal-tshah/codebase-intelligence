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
    arcs = [
        e for e in top["edges"] if e["edge_type"] != "CONTAINS" and (e.get("properties") or {}).get("weight", 1) >= 1
    ]
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


def test_background_jobs_suggestions_and_docs_routes(fs_client):
    pid = fs_client.project_id
    jobs = fs_client.get(f"/projects/{pid}/background-jobs")
    assert jobs.status_code == 200 and jobs.json()["count"] == 0  # fixture has no jobs
    views = {v["id"]: v for v in fs_client.get(f"/projects/{pid}/views").json()}
    assert views["jobs"]["available"] is False
    sug = fs_client.get(f"/projects/{pid}/suggestions?limit=5")
    assert sug.status_code == 200 and sug.json()["count"] <= 5
    assert fs_client.get(f"/projects/{pid}/suggestions?limit=0").status_code == 422
    files = fs_client.get(f"/projects/{pid}/docs").json()["files"]
    assert "```mermaid" in files["api-flows.md"] and "erDiagram" in files["data-model.md"]


def test_git_check_route_validates_and_reports(fs_client, monkeypatch):
    import ci_api.routers.system as api  # routes live in routers since the main.py split

    assert fs_client.get("/git/check?url=https://gitlab.com/o/r").status_code == 422
    import ci_parsers

    denied = lambda url, token=None: {"ok": False, "reason": "private", "needs_token": True}  # noqa: E731
    monkeypatch.setattr(api, "check_git_access", denied)
    monkeypatch.setattr(ci_parsers, "check_git_access", denied)  # used by create_project_from_git
    body = fs_client.get("/git/check?url=https://github.com/o/r").json()
    assert body["ok"] is False and body["needs_token"] is True and "token_configured" in body
    res = fs_client.post("/projects/analyze", json={"git_url": "https://github.com/o/r"})
    assert res.status_code == 400 and "cannot access repository" in res.json()["detail"]


def test_build_context_and_find_references(fs_client):
    from ci_ai import GraphTools

    tools = GraphTools(fs_client.project_id)
    ctx = tools.build_context("get_item", token_budget=8000)
    assert ctx["node"]["name"] == "get_item"
    assert ctx["token_budget"] == 8000
    assert isinstance(ctx.get("missing_evidence"), list)
    assert ctx["source"] and "def get_item" in ctx["source"]["content"]
    tight = tools.build_context("get_item", token_budget=8, max_snippets=1)
    assert tight["source"]["truncated"] is True
    assert len(tight["source"]["content"]) <= 32
    assert any(m["name"] == "Item" for m in ctx["models"])
    refs = tools.find_references("Item")
    assert refs["count"] > 0 and {"READS_MODEL"} <= {r["relation"] for r in refs["references"]}
    assert all("evidence" in r and r["evidence"]["tier"] for r in refs["references"])


def test_node_detail_and_graph_edge_evidence(fs_client):
    pid = fs_client.project_id
    models = fs_client.get(f"/projects/{pid}/models").json()["models"]
    item = next(m for m in models if m["name"] == "Item")
    detail = fs_client.get(f"/projects/{pid}/nodes/{item['id']}").json()
    assert detail["node"].get("evidence", {}).get("tier")
    assert detail["edges"] and all(e.get("evidence", {}).get("reason_code") for e in detail["edges"])
    exp = fs_client.get(f"/projects/{pid}/graph/explore").json()
    arc = next(e for e in exp["edges"] if e.get("evidence"))
    under = fs_client.get(
        f"/projects/{pid}/graph/edges", params={"source": arc["source"], "target": arc["target"]}
    ).json()
    assert under["edges"] and under["edges"][0].get("evidence")
