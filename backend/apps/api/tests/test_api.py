from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ci_api.main import app


@pytest.fixture
def client(data_dir, project_copy):
    c = TestClient(app)
    res = c.post("/projects/analyze", json={"path": str(project_copy)})
    assert res.status_code == 200, res.text
    c.project_id = res.json()["project"]["id"]
    c.root = project_copy
    return c


def _node_id(client, query, node_type=None):
    params = {"q": query, **({"types": node_type} if node_type else {})}
    return client.get(f"/projects/{client.project_id}/search", params=params).json()["results"][0]["id"]


def test_summary_includes_layers_and_hotspots(client):
    body = client.get(f"/projects/{client.project_id}/summary").json()
    assert body["stats"]["endpoints"] == 5 and body["stats"]["models"] == 4
    assert {layer["id"] for layer in body["layers"]} >= {"api", "data"}
    assert body["hotspots"][0]["name"] == "Item"
    assert "Stripe" in body["integrations"]


def test_graph_views_and_layer_catalog(client):
    for view in ("architecture", "layers", "api-flow", "call-graph", "er", "integrations"):
        payload = client.get(f"/projects/{client.project_id}/graph/{view}").json()
        assert payload["nodes"], view
    assert {layer["id"] for layer in client.get("/layers").json()} >= {"api", "service", "data"}


def test_search_path_tour_endpoints(client):
    hits = client.get(f"/projects/{client.project_id}/search", params={"q": "checkout"}).json()["results"]
    assert hits[0]["name"] == "checkout"
    ep = _node_id(client, "order", "Endpoint")
    model = _node_id(client, "Order", "Model")
    path = client.get(f"/projects/{client.project_id}/path", params={"source": ep, "target": model}).json()
    assert path["found"] and path["nodes"][0]["id"] == ep
    steps = client.get(f"/projects/{client.project_id}/tour").json()["steps"]
    assert steps[0]["nodes"]


def test_impact_by_files_and_by_working_tree(client):
    report = client.post(f"/projects/{client.project_id}/impact", json={"files": ["shop/models.py"]}).json()
    assert report["source"] == "files" and report["affected"] and report["risk"]["level"] in {"medium", "high"}
    # edit a file on disk without re-indexing: impact with no body uses the changed files
    views = client.root / "shop" / "views.py"
    views.write_text(views.read_text() + "\n# edit\n")
    auto = client.post(f"/projects/{client.project_id}/impact", json={}).json()
    assert auto["source"] == "working-tree" and auto["changed_files"] == ["shop/views.py"]
    fresh = client.get(f"/projects/{client.project_id}/freshness").json()
    assert fresh["status"] in {"stale", "dirty"} and fresh["changed_files"] == ["shop/views.py"]


def test_source_is_allowlisted_to_indexed_files(client):
    ok = client.get(f"/projects/{client.project_id}/source", params={"path": "shop/views.py"})
    assert ok.status_code == 200 and "def list_items" in ok.json()["content"]
    (client.root / ".env").write_text("SECRET=hunter2\n")
    assert client.get(f"/projects/{client.project_id}/source", params={"path": ".env"}).status_code == 404
    assert client.get(f"/projects/{client.project_id}/source", params={"path": "../../etc/passwd"}).status_code == 404


def test_cors_is_not_wildcard(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_export_contains_full_graph(client):
    res = client.get(f"/projects/{client.project_id}/export")
    assert res.headers["content-disposition"].startswith("attachment")
    body = res.json()
    assert body["nodes"] and body["edges"] and body["layers"]


def test_unknown_project_is_404(data_dir):
    c = TestClient(app)
    for path in ("summary", "tour", "freshness", "export"):
        assert c.get(f"/projects/nope/{path}").status_code == 404


def test_chat_tool_mode_answers_impact_question(client):
    with client.stream(
        "POST", f"/projects/{client.project_id}/chat", json={"message": "What breaks if I change Item?"}
    ) as res:
        text = "".join(res.iter_text())
    assert "Impact analysis" in text


def _sse_events(raw: str) -> list[tuple[str, str]]:
    events, name, data = [], "message", []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        elif line == "" and data:
            events.append((name, "\n".join(data)))
            name, data = "message", []
    return events


def test_view_catalog_reports_availability(client):
    catalog = {v["id"]: v for v in client.get(f"/projects/{client.project_id}/views").json()}
    assert catalog["er"]["available"] and catalog["er"]["count"] == 5  # 4 models + 1 inferred stub
    assert catalog["components"]["available"] is False  # Django fixture has no UI components
    assert {v["id"] for v in client.get("/views").json()} >= {"layers", "api-flow", "components"}
    assert client.get(f"/projects/{client.project_id}/graph/not-a-view").status_code == 404
    assert {a["id"] for a in client.get("/analyzers").json()} >= {"python", "typescript"}


def test_endpoints_explorer_and_models(client):
    body = client.get(f"/projects/{client.project_id}/endpoints").json()
    assert body["count"] == 5
    order = next(e for e in body["endpoints"] if e["route"].endswith("order/"))
    assert order["handler"]["name"] == "create_order"
    assert {m["name"] for m in order["models"]} & {"Order", "Item"}
    models = client.get(f"/projects/{client.project_id}/models").json()["models"]
    item = next(m for m in models if m["name"] == "Item")
    assert item["fields"] and item["read_by"]


def test_chat_streams_structured_events_with_navigable_links(client):
    with client.stream(
        "POST", f"/projects/{client.project_id}/chat", json={"message": "Which tables does the checkout flow use?"}
    ) as res:
        events = _sse_events("".join(res.iter_text()))
    names = [e[0] for e in events]
    assert "tool" in names and names[-1] == "done"
    text = "".join(d for n, d in events if n == "message")
    assert "\n" in text and "(node:" in text  # markdown keeps newlines; nodes are links
    citations = json.loads(next(d for n, d in events if n == "citations"))
    assert citations and all("node_id" in c and "view" in c for c in citations)


def test_server_mode_requires_key_and_confines_paths(data_dir, project_copy, tmp_path, monkeypatch):
    import pytest as _pytest

    from ci_core.settings import SettingsError, get_settings

    monkeypatch.setenv("CI_MODE", "server")
    with _pytest.raises(SettingsError):  # fails fast without key/roots
        get_settings()
    monkeypatch.setenv("CI_API_KEY", "s3cret")
    monkeypatch.setenv("CI_PROJECT_ROOTS", str(tmp_path / "project"))
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/projects").status_code == 401
    assert c.get("/projects", headers={"X-API-Key": "wrong"}).status_code == 401
    ok = {"Authorization": "Bearer s3cret"}
    assert c.get("/projects", headers=ok).status_code == 200
    assert c.post("/projects/analyze", json={"path": str(tmp_path)}, headers=ok).status_code == 403
    assert (
        c.post(
            "/projects/analyze",
            json={"git_url": "https://github.com/example/example"},
            headers=ok,
        ).status_code
        == 403
    )
    res = c.post("/projects/analyze", json={"path": str(project_copy)}, headers=ok)
    assert res.status_code == 200 and res.headers["x-request-id"]
    pid = res.json()["project"]["id"]
    src = c.get(f"/projects/{pid}/source", params={"path": "shop/views.py"}, headers=ok)
    assert src.status_code == 200 and "abs_path" not in src.json()  # no server paths leak to clients


def test_graph_and_source_params_are_bounded(client):
    pid = client.project_id
    too_many = ",".join(f"n{i}" for i in range(501))
    assert client.get(f"/projects/{pid}/graph/explore", params={"expanded": too_many}).status_code == 422
    assert client.get(f"/projects/{pid}/graph/explore", params={"expanded": "a,b"}).status_code == 200
    offsets = [f"n{i}=10" for i in range(201)]
    assert client.get(f"/projects/{pid}/graph/explore", params={"extra_child_offsets": offsets}).status_code == 422
    long_id = "x" * 513
    assert client.get(f"/projects/{pid}/graph/neighborhood", params={"node_id": long_id}).status_code == 422
    assert client.get(f"/projects/{pid}/graph/edges", params={"source": long_id, "target": "a"}).status_code == 422
    assert client.get(f"/projects/{pid}/nodes/{long_id}").status_code == 422
    assert client.get(f"/projects/{pid}/source", params={"path": "a" * 1025}).status_code == 422
    assert client.get(f"/projects/{pid}/source", params={"path": "shop/views.py", "end": 0}).status_code == 422
    assert client.get(f"/projects/{pid}/graph/{'v' * 300}").status_code == 404


def test_project_routes_resolve_by_name_and_subdirectory(client):
    name = client.get("/projects").json()[0]["name"]
    assert client.get(f"/projects/{name}/summary").status_code == 200
    sub = str(client.root / "shop").replace("\\", "/")
    assert client.get(f"/projects/{sub}/freshness").status_code == 200


def test_impact_with_git_base(client, fullstack_copy):
    import subprocess

    def git(*args):
        subprocess.run(
            ["git", "-C", str(fullstack_copy), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    db = fullstack_copy / "api" / "app" / "db.py"
    db.write_text(db.read_text() + "\n# touched\n")
    git("commit", "-qam", "change")
    c = TestClient(app)
    res = c.post("/projects/analyze", json={"path": str(fullstack_copy)})
    assert res.status_code == 200
    pid = res.json()["project"]["id"]
    report = c.post(f"/projects/{pid}/impact", json={"base": "HEAD~1", "depth": 3}).json()
    assert report["source"] == "git-ref" and report["affected"]
    assert c.post(f"/projects/{pid}/impact", json={"base": "no-such-ref"}).status_code == 400
    out = fullstack_copy / "injected"
    assert c.post(f"/projects/{pid}/impact", json={"base": f"--output={out}"}).status_code == 400
    assert not list(fullstack_copy.glob("injected*"))  # never parsed as a git option


def test_resolve_by_name_and_path_and_request_id(client):
    name = client.get("/projects").json()[0]["name"]
    assert client.get("/projects/resolve", params={"ref": name}).json()["id"] == client.project_id
    inside = str(client.root / "shop")
    res = client.get("/projects/resolve", params={"ref": inside})
    assert res.json()["id"] == client.project_id and res.headers["x-request-id"]
    assert client.get("/projects/resolve", params={"ref": "nope"}).status_code == 404
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers["x-request-id"] == "abc123"


def test_summary_is_cached_until_the_index_changes(client, monkeypatch):
    from ci_ai import summarize

    calls = []
    real = summarize._build_project_summary
    monkeypatch.setattr(summarize, "_build_project_summary", lambda pid: calls.append(pid) or real(pid))
    summarize._SUMMARY_CACHE.clear()
    first = client.get(f"/projects/{client.project_id}/summary").json()
    second = client.get(f"/projects/{client.project_id}/summary").json()
    assert first == second and len(calls) == 1
    (client.root / "shop" / "extra_view.py").write_text("def ping():\n    return 1\n")
    job = client.post(f"/projects/{client.project_id}/index").json()
    assert job["status"] in {"pending", "running", "completed"}
    import time

    for _ in range(100):
        if client.get(f"/projects/{client.project_id}/jobs/{job['id']}").json()["status"] not in {"pending", "running"}:
            break
        time.sleep(0.05)
    client.get(f"/projects/{client.project_id}/summary")
    assert len(calls) == 2  # rebuilt after the index changed


def test_health_is_public_when_mounted_under_api(data_dir, tmp_path, monkeypatch):
    """Docker HEALTHCHECK hits /api/health on the combined app; server mode must not 401 it."""
    from ci_api.main import create_app

    monkeypatch.setenv("CI_MODE", "server")
    monkeypatch.setenv("CI_API_KEY", "s3cret")
    monkeypatch.setenv("CI_PROJECT_ROOTS", str(tmp_path))
    ui = tmp_path / "ui"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<!doctype html><title>t</title>")
    c = TestClient(create_app(ui_dir=ui))
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/projects", headers={"X-API-Key": "s3cret"}).status_code == 200
