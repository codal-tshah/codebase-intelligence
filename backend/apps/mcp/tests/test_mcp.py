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
    assert {"project_overview", "trace_endpoint", "impact_analysis", "list_models", "index_project"} <= names

    overview = _payload(_call(server, "project_overview", {}))  # auto-indexes the path
    assert "fastapi" in overview["frameworks"] and overview["counts"]["Endpoint"] >= 5

    trace = _payload(_call(server, "trace_endpoint", {"route": "/api/items/{item_id}", "method": "GET"}))
    assert trace["handler"]["name"] == "get_item"
    assert any(c["name"] == "api.getItem" for c in trace["callers"])

    found = _payload(_call(server, "search_nodes", {"query": "ItemList"}))
    assert found["results"][0]["name"] == "ItemList"

    projects = _payload(_call(server, "list_projects", {}))
    assert len(projects["projects"]) == 1
