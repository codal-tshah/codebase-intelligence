"""The tool-calling loop, driven by a scripted fake LLM (no network)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from ci_indexer import create_project_from_path, run_index_job


def _chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_call(index, call_id, name, args):
    return SimpleNamespace(index=index, id=call_id, function=SimpleNamespace(name=name, arguments=args))


@pytest.fixture
def project(data_dir, fullstack_copy):
    record = create_project_from_path(fullstack_copy)
    assert run_index_job(record.id).status.value == "completed"
    return record


def test_agent_calls_tools_then_answers_with_cited_nodes(project, monkeypatch):
    import litellm

    from ci_ai import GraphTools
    from ci_ai.agent import chat_stream

    item_list = GraphTools(project.id).find_symbol("ItemList", limit=1)[0]["id"]
    seen_messages: list[list[dict]] = []

    async def fake_acompletion(**kwargs):
        seen_messages.append(kwargs["messages"])
        assert kwargs["api_key"] == "test-key" and kwargs["tools"]
        step = len(seen_messages)

        async def stream():
            if step == 1:
                yield _chunk(tool_calls=[_tool_call(0, "c1", "search_nodes", '{"query": "Item')])
                yield _chunk(tool_calls=[_tool_call(0, None, None, 'List"}')])
            else:
                yield _chunk(content="The list is rendered by ")
                yield _chunk(content=f"[ItemList](node:{item_list}).\n")

        return stream()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setenv("ALLOW_LLM", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    async def collect():
        return [e async for e in chat_stream(project.id, "Who renders the item list?")]

    events = asyncio.run(collect())
    names = [e["event"] for e in events]
    assert names[0] == "tool" and names[-1] == "done"
    tool = json.loads(events[0]["data"])
    assert tool["name"] == "search_nodes" and tool["args"] == {"query": "ItemList"}
    # the tool result was fed back to the model as a tool message
    assert seen_messages[1][-1]["role"] == "tool" and "ItemList" in seen_messages[1][-1]["content"]
    citations = json.loads(next(e["data"] for e in events if e["event"] == "citations"))
    first = citations[0]
    assert first["node_id"] == item_list and first["cited"] and first["view"] == "components"


def test_agent_falls_back_to_graph_tools_when_llm_errors(project, monkeypatch):
    import litellm

    from ci_ai.agent import chat_stream

    async def broken(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(litellm, "acompletion", broken)
    monkeypatch.setenv("ALLOW_LLM", "true")
    monkeypatch.setenv("LLM_API_KEY", "k")

    async def collect():
        return [e async for e in chat_stream(project.id, "What happens when /api/items/ is called?")]

    events = asyncio.run(collect())
    assert events[0]["event"] == "error"
    text = "".join(e["data"] for e in events if e["event"] == "message")
    assert "list_items" in text and "(node:" in text and "Called from UI" in text
