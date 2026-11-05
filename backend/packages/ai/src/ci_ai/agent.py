"""Project-grounded assistant.

With an LLM configured, a tool-calling agent explores the code graph (`ci_ai.toolspec`)
and streams an answer whose references are navigable links:

    [ItemList](node:<node id>)        -> select the node / open its best diagram
    [src/App.tsx:12](source:src/App.tsx#L12) -> open the source viewer at a line

Without an LLM, deterministic graph tools answer directly (same link format).

`chat_stream` yields SSE-ready events: ``{"event": <name>, "data": <str>}``

    message    answer text (markdown, incremental)
    tool       JSON {name, args, summary} for each grounding call (transparency)
    citations  JSON [{node_id, label, path, line, node_type, view}]
    done       JSON {mode, steps}
    error      text
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from ci_ai.llm import llm_enabled, llm_kwargs
from ci_ai.tools import GraphTools
from ci_ai.toolspec import collect_refs, openai_tools, run_tool, tool_result_text
from ci_security import sanitize_for_llm

MAX_STEPS = 6

SYSTEM_PROMPT = """You are the codebase intelligence assistant for ONE specific software project.
Ground every claim in this project's code graph and source by calling tools; do not answer from general knowledge alone.

Workflow: locate (project_overview, search_nodes, list_endpoints, list_models) -> inspect (get_node, trace_endpoint,
get_callers/get_callees, impact_analysis, find_path, read_source) -> answer. Use several tools when a question spans
layers (UI -> API -> service -> database -> external services).

Cite evidence inline as markdown links so the developer can click through:
- graph nodes: [ItemList](node:<the 32-character id from a tool result>)
- source lines: [web/src/App.tsx:12](source:web/src/App.tsx#L12)
Only cite ids and paths that appeared in tool results. Never invent files, routes, or ids.

Nodes carry a layer (api, middleware, service, data, ui, config, test, external), a role and a summary; edges carry a
confidence. Say explicitly when the graph is incomplete, a link is inferred (confidence < 0.7), or behaviour is dynamic
and cannot be confirmed statically. Prefer short sections: Summary, Flow (numbered steps), Data, External services, Risks."""

_IMPACT_RX = re.compile(r"\b(impact|break|breaks|affect|affects|blast|depend(?:s|ents)? on|change[sd]?|modify|refactor)\b", re.I)
_PATH_RX = re.compile(r"\b(path|connect(?:ed|s|ion)?|reach(?:es)?|between|flow from)\b", re.I)
_DATA_RX = re.compile(r"\b(model|models|table|tables|database|db|schema|orm|entity|entities)\b", re.I)
_API_RX = re.compile(r"\b(endpoint|endpoints|api|apis|route|routes|request|http)\b", re.I)
_OVERVIEW_RX = re.compile(r"\b(overview|architecture|get started|where to start|tour|structure|how is .* organi[sz]ed)\b", re.I)
_IDENT_RX = re.compile(r"[A-Za-z_][A-Za-z0-9_./{}:-]*")
_NODE_LINK_RX = re.compile(r"\(node:([a-f0-9]{32})\)")


def _event(name: str, data: Any) -> dict[str, str]:
    return {"event": name, "data": data if isinstance(data, str) else json.dumps(data, default=str)}


def _view_for(node_type: str | None) -> str | None:
    from ci_core.views import registered_views

    for v in registered_views():
        if any(t.value == node_type for t in v.best_for):
            return v.id
    return None


def _citations(refs: dict[str, dict[str, Any]], text: str, limit: int = 14) -> list[dict[str, Any]]:
    cited = [m for m in dict.fromkeys(_NODE_LINK_RX.findall(text)) if m in refs]
    ordered = cited + [k for k in refs if k not in cited]
    out = []
    for nid in ordered[:limit]:
        ref = refs[nid]
        out.append({**ref, "view": _view_for(ref.get("node_type")), "cited": nid in cited})
    return out


def _summarize_result(result: Any) -> str:
    if isinstance(result, list):
        return f"{len(result)} result(s)"
    if isinstance(result, dict):
        if "error" in result:
            return f"error: {result['error']}"
        for key in ("affected", "chain", "results", "steps", "models", "edges"):
            if isinstance(result.get(key), list):
                return f"{len(result[key])} {key}"
        return result.get("name") or result.get("route") or "ok"
    return "ok"


async def chat_stream(
    project_id: str,
    message: str,
    focus_node_id: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, str]]:
    tools = GraphTools(project_id)
    safe_msg, redactions = sanitize_for_llm(message)
    if llm_enabled():
        try:
            async for event in _agent(tools, safe_msg, focus_node_id, conversation_history or [], redactions):
                yield event
            return
        except Exception as exc:  # noqa: BLE001 - fall back to deterministic answers
            yield _event("error", f"LLM unavailable ({type(exc).__name__}); answering from graph tools only.")
    async for event in _tools_only(tools, safe_msg, focus_node_id):
        yield event


# ---------------------------------------------------------------------- agent


async def _agent(
    tools: GraphTools, message: str, focus_node_id: str | None, history: list[dict[str, str]], redactions: int
) -> AsyncIterator[dict[str, str]]:
    from litellm import acompletion

    refs: dict[str, dict[str, Any]] = {}
    user = message
    if focus_node_id:
        focus = tools.get_node(focus_node_id)
        if focus:
            collect_refs(focus, refs)
            brief = {k: focus.get(k) for k in ("id", "name", "type", "path", "line", "layer", "summary")}
            user += f"\n\n(The developer currently has this node selected: {json.dumps(brief)})"
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            content, _ = sanitize_for_llm(str(turn["content"])[:2000])
            messages.append({"role": turn["role"], "content": content})
    messages.append({"role": "user", "content": user})

    answer: list[str] = []
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    step = 0
    for step in range(1, MAX_STEPS + 1):
        final = step == MAX_STEPS
        response = await acompletion(
            **llm_kwargs(),
            messages=messages,
            tools=openai_tools(),
            tool_choice="none" if final else "auto",
            stream=True,
        )
        text_parts: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                text_parts.append(content)
                answer.append(content)
                yield _event("message", content)
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = calls.setdefault(getattr(tc, "index", None) or 0, {"id": "", "name": "", "arguments": ""})
                if getattr(tc, "id", None):
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None) and not slot["name"]:
                        slot["name"] = fn.name
                    if getattr(fn, "arguments", None):
                        slot["arguments"] += fn.arguments
        if not calls:
            break
        ordered = [(i, c) for i, c in sorted(calls.items()) if c["name"]]
        messages.append(
            {
                "role": "assistant",
                "content": "".join(text_parts) or None,
                "tool_calls": [
                    {"id": c["id"] or f"call_{step}_{i}", "type": "function", "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                    for i, c in ordered
                ],
            }
        )
        for i, c in ordered:
            try:
                args = json.loads(c["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await asyncio.to_thread(run_tool, tools, c["name"], args if isinstance(args, dict) else {})
            collect_refs(result, refs)
            text, red = tool_result_text(result)
            redactions += red
            chars += len(text)
            yield _event("tool", {"name": c["name"], "args": args, "summary": _summarize_result(result)})
            messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{step}_{i}", "content": text})

    tools.store.log_llm_request(token_estimate=chars // 4, redaction_count=redactions)
    yield _event("citations", _citations(refs, "".join(answer)))
    yield _event("done", {"mode": "agent", "steps": step})


# ------------------------------------------------------------------ tools-only


def _identifiers(message: str) -> list[str]:
    """Code-like tokens first (snake_case, CamelCase, paths), then other meaningful words."""
    tokens = [t.strip("./:") for t in _IDENT_RX.findall(message)]
    tokens = [t for t in tokens if t and t.lower() not in _STOP and len(t) > 1]
    codey = [t for t in tokens if "_" in t or "/" in t or "." in t or (t != t.lower() and t != t.capitalize())]
    capitalised = [t for t in tokens if t[0].isupper() and t not in codey]
    rest = [t for t in tokens if t not in codey and t not in capitalised]
    return list(dict.fromkeys([*codey, *capitalised, *sorted(rest, key=len, reverse=True)]))


_STOP = {
    "how", "does", "the", "what", "when", "where", "which", "this", "that", "work", "here", "is", "are", "a", "an",
    "of", "to", "in", "on", "and", "or", "for", "with", "me", "show", "tell", "about", "find", "who", "why", "can",
    "if", "i", "do", "it", "its", "between", "from", "path", "impact", "change", "changes", "break", "breaks",
    "affect", "affects", "my", "our", "any", "all", "get", "list", "view", "views", "function", "class", "model",
    "models", "endpoint", "endpoints", "route", "routes", "handle", "handles", "use", "uses", "used", "api", "apis",
    "happens", "called", "call", "calls", "project", "code", "codebase", "explain", "involved", "tables", "table",
    "database", "data", "services", "service", "third-party", "party", "third", "internally", "complete", "flow",
    "execution", "feature", "entire", "layer", "modify", "would", "could", "should", "there", "they", "them",
}


def _link(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("route") or "node"
    nid = item.get("id")
    return f"[{name}](node:{nid})" if isinstance(nid, str) and len(nid) == 32 else f"`{name}`"


def _loc(item: dict[str, Any]) -> str:
    path = item.get("path") or item.get("source_path")
    line = item.get("line") or item.get("start_line")
    if not path:
        return ""
    label = f"{path}:{line}" if line else path
    return f" — [{label}](source:{path}#L{line or 1})"


async def _tools_only(tools: GraphTools, message: str, focus_node_id: str | None) -> AsyncIterator[dict[str, str]]:
    refs: dict[str, dict[str, Any]] = {}
    sections: list[str] = ["> **Graph-tools mode** — set `ALLOW_LLM=true` with `LLM_API_KEY` or `LLM_API_BASE` for agentic answers.", ""]
    idents = _identifiers(message)
    keyword = idents[0] if idents else (message.split()[0] if message.split() else "")

    def call(name: str, **args: Any) -> Any:
        result = run_tool(tools, name, args)
        collect_refs(result, refs)
        return result

    events: list[dict[str, str]] = []

    def note(name: str, args: dict[str, Any], result: Any) -> None:
        events.append(_event("tool", {"name": name, "args": args, "summary": _summarize_result(result)}))

    if focus_node_id:
        focus = call("get_node", node=focus_node_id)
        note("get_node", {"node": focus_node_id}, focus)
        if isinstance(focus, dict) and "error" not in focus:
            sections += [f"**Selected:** {_link(focus)} ({focus.get('type')}) — {focus.get('summary') or ''}", ""]

    if _OVERVIEW_RX.search(message):
        overview = call("project_overview")
        note("project_overview", {}, overview)
        sections += [f"**{overview.get('name')}** — {overview.get('summary') or ''}", "", "Suggested reading order:"]
        sections += [f"{s['order']}. **{s['title']}** — {s['description']}" for s in overview.get("tour", [])[:8]]
        sections.append("")

    route = next((t for t in message.split() if "/" in t), None)
    if route or (_API_RX.search(message) and not _DATA_RX.search(message)):
        if route:
            details = call("trace_endpoint", route=route.strip("'\"`?,."))
            note("trace_endpoint", {"route": route}, details)
            if isinstance(details, dict) and details.get("handler") is not None:
                sections.append(f"**Endpoint** {' '.join(details.get('methods') or [])} {_link(details)}{_loc(details)}")
                sections.append(f"- Handler: {_link(details['handler'])}{_loc(details['handler'])}")
                for g in details.get("guards", []) + details.get("dependencies", []):
                    sections.append(f"- Guard / dependency: {_link(g)}")
                for m in details.get("models", []):
                    sections.append(f"- Data: {_link(m)} ({'/'.join(m['access'])})")
                for x in details.get("external", []):
                    sections.append(f"- External: {_link(x)}")
                for c in details.get("callers", []):
                    sections.append(f"- Called from UI/client: {_link(c)}{_loc(c)}")
                sections.append("")
            elif isinstance(details, dict) and details.get("chain"):
                sections.append(f"Endpoint trace for `{details.get('route')}`:")
                sections += [f"- {s['type']}: {_link(s)}{_loc(s)}" for s in details["chain"]]
                sections.append("")
        else:
            eps = call("list_endpoints", query=None if not idents else None)
            note("list_endpoints", {}, eps)
            sections.append(f"**{len(eps)} endpoint(s)**:")
            for ep in eps[:20]:
                handler = ep.get("handler") or {}
                callers = f" · called by {', '.join(_link(c) for c in ep['callers'][:3])}" if ep.get("callers") else ""
                sections.append(f"- `{' '.join(ep.get('methods') or ['ANY'])}` {_link(ep)} → {_link(handler) if handler else '_unresolved_'}{callers}")
            sections.append("")

    if _DATA_RX.search(message):
        models = call("list_models")
        note("list_models", {}, models)
        sections.append(f"**{len(models)} data model(s)**:")
        for m in models[:15]:
            rel = ", ".join(r["to"] for r in m.get("relations", []))
            users = ", ".join(m.get("read_by", [])[:3] + m.get("written_by", [])[:3])
            sections.append(f"- {_link(m)} `{m.get('table') or ''}`" + (f" → {rel}" if rel else "") + (f" · used by {users}" if users else ""))
        sections.append("")

    if _IMPACT_RX.search(message) and idents:
        impact = call("impact_analysis", target=idents[0])
        note("impact_analysis", {"target": idents[0]}, impact)
        if impact.get("changed"):
            sections.append(
                f"**Impact analysis** — risk **{impact['risk']['level']}** (score {impact['risk']['score']}), "
                f"{len(impact['affected'])} dependent node(s):"
            )
            sections += [
                f"- {_link(item)} ({item['node_type']}, {item.get('layer') or 'n/a'}, {item['hops']} hop(s))"
                for item in impact["affected"][:10]
            ]
            sections += [f"- _{n}_" for n in impact.get("notes", [])[:3]]
            sections.append("")

    if _PATH_RX.search(message) and len(idents) >= 2:
        path = call("find_path", source=idents[0], target=idents[1])
        note("find_path", {"source": idents[0], "target": idents[1]}, path)
        if path.get("found"):
            sections += ["**Shortest dependency path:** " + " → ".join(_link(s) for s in path["steps"]), ""]

    symbols = call("search_nodes", query=keyword, limit=8) if keyword else []
    note("search_nodes", {"query": keyword}, symbols)
    if symbols:
        sections.append("**Matching nodes:**")
        sections += [f"- {_link(s)} ({s.get('type')}) {s.get('summary') or ''}{_loc(s)}" for s in symbols[:8]]
        sections.append("")
    hits = call("search_code", pattern=keyword, limit=6) if keyword else []
    if hits:
        sections.append("**Code search:**")
        sections += [f"- [{h['path']}:{h['line']}](source:{h['path']}#L{h['line']}) `{h['text'][:110]}`" for h in hits[:6]]
        sections.append("")

    for ev in events:
        yield ev
    text = "\n".join(sections).rstrip() + "\n"
    yield _event("message", text)
    yield _event("citations", _citations(refs, text))
    yield _event("done", {"mode": "tools", "steps": len(events)})
