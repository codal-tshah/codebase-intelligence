"""Project management: remove (never touching the source), rename, settings, saved views,
audit log, overview/status, error shape, gzip and the auto-refresh check."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ci_api.main import app


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(root).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def client(data_dir, project_copy):
    c = TestClient(app)
    res = c.post("/projects/analyze", json={"path": str(project_copy)})
    assert res.status_code == 200, res.text
    c.project_id = res.json()["project"]["id"]
    c.root = project_copy
    return c


def test_delete_removes_index_but_never_the_source(client, data_dir):
    before = _tree_digest(client.root)
    plan = client.get(f"/projects/{client.project_id}/removal-plan").json()
    assert plan["managed_clone"] is None and plan["source_untouched"] == str(client.root)
    assert plan["index_data"].startswith(str(data_dir))

    res = client.delete(f"/projects/{client.project_id}")
    assert res.status_code == 200, res.text
    assert not (data_dir / "projects" / client.project_id).exists()
    assert client.get("/projects").json() == []
    assert client.get(f"/projects/{client.project_id}/summary").status_code == 404
    assert _tree_digest(client.root) == before  # the original folder is byte-for-byte unchanged
    entry = client.get("/audit", params={"action": "project.delete"}).json()["entries"][0]
    assert entry["project_id"] == client.project_id and entry["detail"]["source_untouched"] == str(client.root)


def test_delete_removes_a_managed_clone(client, data_dir):
    from ci_core.project_admin import removal_plan
    from ci_core.registry import register_project

    clone = data_dir / "sources" / "owner__repo"
    clone.mkdir(parents=True)
    (clone / "x.py").write_text("x = 1\n")
    rec = client.get(f"/projects/resolve?ref={client.project_id}").json()
    from ci_core.models import ProjectRecord

    managed = ProjectRecord.model_validate({**rec, "id": "managed-1", "name": "repo", "root_path": str(clone)})
    register_project(managed)
    assert removal_plan(managed)["managed_clone"] == str(clone.resolve())
    assert client.delete("/projects/managed-1").status_code == 200
    assert not clone.exists()
    assert client.root.exists()


def test_delete_refused_while_indexing(client, monkeypatch):
    import ci_api.routers.projects as projects

    monkeypatch.setattr(projects, "index_in_progress", lambda pid: True)
    res = client.delete(f"/projects/{client.project_id}")
    assert res.status_code == 409
    assert "running" in res.json()["detail"] and res.json()["request_id"]


def test_rename_unique_and_survives_reindex(client, project_copy):
    res = client.patch(f"/projects/{client.project_id}", json={"name": "  Billing   service "})
    assert res.status_code == 200 and res.json()["name"] == "Billing service"
    assert client.get("/projects/resolve", params={"ref": "Billing service"}).json()["id"] == client.project_id
    client.post("/projects/analyze", json={"path": str(project_copy)})  # re-analyze keeps the name
    assert client.get("/projects").json()[0]["name"] == "Billing service"


def test_settings_ignore_patterns_apply_on_next_index(client):
    pid = client.project_id
    files_before = client.get("/projects/overview").json()[0]["files"]
    res = client.put(f"/projects/{pid}/settings", json={"ignore": ["*/admin.py", "# comment", ""], "auto_refresh": True})
    assert res.status_code == 200
    assert res.json()["ignore"] == ["*/admin.py"] and res.json()["auto_refresh"] is True
    job = client.post(f"/projects/{pid}/index").json()
    assert client.get(f"/projects/{pid}/jobs/{job['id']}").json()["status"] == "completed"
    files_after = client.get("/projects/overview").json()[0]["files"]
    assert files_after < files_before
    assert client.get(f"/projects/{pid}/index-jobs").json()["jobs"][0]["id"] == job["id"]


def test_saved_views_roundtrip(client):
    pid = client.project_id
    v = client.post(f"/projects/{pid}/saved-views", json={"name": "Orders flow", "state": {"v": "api-flow", "n": "abc", "x": "dropped"}}).json()
    assert v["state"] == {"v": "api-flow", "n": "abc"}
    assert [i["name"] for i in client.get(f"/projects/{pid}/saved-views").json()["views"]] == ["Orders flow"]
    assert client.delete(f"/projects/{pid}/saved-views/{v['id']}").status_code == 200
    assert client.delete(f"/projects/{pid}/saved-views/{v['id']}").status_code == 404
    assert client.get(f"/projects/{pid}").status_code == 405  # only DELETE/PATCH on the bare project path


def test_overview_status_and_audit(client):
    item = client.get("/projects/overview").json()[0]
    assert item["indexed_at"] and item["stats"]["files"] >= 1 and item["indexing"] is False
    status = client.get("/status").json()
    assert status["project_count"] == 1 and status["mode"] == "local" and status["analyzers"]
    actions = [e["action"] for e in client.get("/audit").json()["entries"]]
    assert "project.analyze" in actions


def test_validation_errors_share_the_error_shape(client):
    res = client.get(f"/projects/{client.project_id}/graph/explore", params={"expand_to_level": 0})
    assert res.status_code == 422
    body = res.json()
    assert isinstance(body["detail"], list) and "request_id" in body


def test_large_graph_responses_are_gzipped(client):
    res = client.get(f"/projects/{client.project_id}/graph/layers", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    if len(res.content) > 2048:
        assert res.headers.get("content-encoding") == "gzip"


def test_auto_refresh_due_only_when_head_moved(client, monkeypatch):
    import ci_api.autorefresh as ar

    client.put(f"/projects/{client.project_id}/settings", json={"auto_refresh": True})
    from ci_core.fingerprints import load_fingerprints

    indexed = (load_fingerprints(client.project_id) or {}).get("commit_sha")
    monkeypatch.setattr(ar, "load_fingerprints", lambda pid: {"commit_sha": "old"})
    monkeypatch.setattr(ar, "git_head", lambda root: "new")
    assert [d[0] for d in ar.due_projects()] == [client.project_id]
    monkeypatch.setattr(ar, "git_head", lambda root: "old")
    assert ar.due_projects() == []
    assert indexed is None or isinstance(indexed, str)


def test_git_dir_is_detected_for_hooks(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    from ci_cli.main import _git_hook_paths

    assert _git_hook_paths(tmp_path) is not None
