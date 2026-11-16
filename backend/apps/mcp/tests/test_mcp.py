from __future__ import annotations

import asyncio
import json

from ci_mcp.server import build_server


def _call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    return result


def _payload(result):
    """Tool results come back as content blocks (and/or structured content); normalise to a dict."""
    if isinstance(result, dict):
        return result
    if isinstance(result, tuple):
        for part in result:
            if isinstance(part, dict):
                return part
        result = result[0]
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured:
        return structured
    blocks = getattr(result, "content", result)
    text = "".join(getattr(b, "text", "") for b in blocks)
    return json.loads(text)


def test_mcp_lists_tools_and_answers_against_path(data_dir, fullstack_copy):
    server = build_server(str(fullstack_copy))
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"project_overview", "trace_endpoint", "impact_analysis", "list_models", "index_project",
            "list_jobs", "suggest_optimizations", "generate_docs", "build_context", "find_references"} <= names

    overview = _payload(_call(server, "project_overview", {}))  # auto-indexes the path
    assert "fastapi" in overview["frameworks"] and overview["counts"]["Endpoint"] >= 5

    docs = _payload(_call(server, "generate_docs", {"output_dir": "docs/map"}))
    assert "docs/map/architecture.md" in docs["written"] and (fullstack_copy / "docs/map/README.md").is_file()

    trace = _payload(_call(server, "trace_endpoint", {"route": "/api/items/{item_id}", "method": "GET"}))
    assert trace["handler"]["name"] == "get_item"
    assert any(c["name"] == "api.getItem" for c in trace["callers"])

    found = _payload(_call(server, "search_nodes", {"query": "ItemList"}))
    assert found["results"][0]["name"] == "ItemList"

    projects = _payload(_call(server, "list_projects", {}))
    assert len(projects["projects"]) == 1


def test_mcp_impact_of_working_tree_with_git_base(data_dir, fullstack_copy):
    import subprocess

    from ci_indexer import create_project_from_path, run_index_job

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

    project = create_project_from_path(fullstack_copy)
    assert run_index_job(project.id).status.value == "completed"

    server = build_server(str(fullstack_copy), auto_index=False)
    report = _payload(_call(server, "impact_of_working_tree", {"base": "HEAD~1", "depth": 3}))
    assert report.get("source") == "git-ref" and report.get("affected")


def test_mcp_index_project_accepts_github_url(data_dir, fullstack_copy, monkeypatch):
    import pytest

    import ci_indexer
    from ci_indexer import create_project_from_path

    cloned = []

    def fake_git(url, work_root=None):  # no network in tests: "clone" = register the fixture copy
        cloned.append(url)
        return create_project_from_path(fullstack_copy, git_url=url)

    monkeypatch.setattr(ci_indexer, "create_project_from_git", fake_git)
    server = build_server(str(fullstack_copy))
    out = _payload(_call(server, "index_project", {"path": "https://github.com/example/shop"}))
    assert cloned == ["https://github.com/example/shop"] and out["status"] == "completed"

    monkeypatch.setenv("CI_MODE", "server")
    monkeypatch.setenv("CI_API_KEY", "k")
    monkeypatch.setenv("CI_PROJECT_ROOTS", str(fullstack_copy))
    with pytest.raises(Exception) as err:
        _call(server, "index_project", {"path": "https://github.com/example/shop"})
    assert "disabled in server mode" in f"{err.value} {err.value.__cause__}"
