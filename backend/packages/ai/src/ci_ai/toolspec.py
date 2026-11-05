"""Grounding tools as data: one definition serves the LLM agent, the MCP server and the CLI.

Each tool maps a JSON-schema'd call onto :class:`GraphTools`. Outputs are JSON-able,
size-capped, and secret-redacted before they can reach a model.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ci_ai.tools import GraphTools
from ci_security import sanitize_for_llm

MAX_RESULT_CHARS = 9000


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[..., Any]


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


_STR = {"type": "string"}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "project_overview",
        "Project summary: frameworks, languages, node counts and the guided reading order. Call first for broad questions.",
        _obj({}),
        lambda t: t.overview(),
    ),
    ToolSpec(
        "search_nodes",
        "Fuzzy-search the code graph (functions, classes, components, endpoints, models, modules, services) by name, path, tag or summary.",
        _obj(
            {
                "query": {**_STR, "description": "Name, path fragment, or concept (e.g. 'auth', 'checkout', 'ItemList')"},
                "node_types": {"type": "array", "items": _STR, "description": "Optional filter, e.g. ['Endpoint','Model','Component','Function']"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 40},
            },
            ["query"],
        ),
        lambda t, query, node_types=None, limit=12: t.find_symbol(query, limit=limit, types=set(node_types) if node_types else None),
    ),
    ToolSpec(
        "get_node",
        "Details for one node (by id or name): summary, layer, role, source location, HTTP calls, and its incoming/outgoing relations.",
        _obj({"node": {**_STR, "description": "Node id or name"}}, ["node"]),
        lambda t, node: t.get_node(node) or {"error": f"no node matches {node!r}"},
    ),
    ToolSpec(
        "list_endpoints",
        "All HTTP endpoints (any framework) with method, route, handler, guards, frontend callers and models touched.",
        _obj({"query": {**_STR, "description": "Optional route/handler substring filter"}}),
        lambda t, query=None: t.endpoints(query),
    ),
    ToolSpec(
        "trace_endpoint",
        "What happens when an API is called: handler, injected dependencies, guards, call chain, models read/written, external services, and which frontend code calls it.",
        _obj({"route": {**_STR, "description": "Route path like /api/items/{id} or an endpoint node id"}, "method": _STR}, ["route"]),
        lambda t, route, method=None: t.endpoint_details(route, method),
    ),
    ToolSpec(
        "get_callers",
        "Functions/components that call the given node (by id or name).",
        _obj({"node": _STR}, ["node"]),
        lambda t, node: (lambda n: t.get_callers(n.id) if n else [])(t.resolve(node)),
    ),
    ToolSpec(
        "get_callees",
        "Functions the given node calls (by id or name).",
        _obj({"node": _STR}, ["node"]),
        lambda t, node: (lambda n: t.get_callees(n.id) if n else [])(t.resolve(node)),
    ),
    ToolSpec(
        "impact_analysis",
        "Blast radius of changing a symbol or file: dependent nodes by hop, affected endpoints, layers, hotspots, risk and notes.",
        _obj({"target": {**_STR, "description": "Symbol name, node id, or file path"}, "depth": {"type": "integer", "minimum": 1, "maximum": 6}}, ["target"]),
        lambda t, target, depth=3: t.impact_of(target, depth=depth),
    ),
    ToolSpec(
        "find_path",
        "Shortest dependency path between two nodes (names or ids), e.g. a component and a database model.",
        _obj({"source": _STR, "target": _STR}, ["source", "target"]),
        lambda t, source, target: t.find_path(source, target),
    ),
    ToolSpec(
        "list_models",
        "Database/ORM models with tables, fields, relations, and which code reads or writes each.",
        _obj({}),
        lambda t: t.models(),
    ),
    ToolSpec(
        "read_source",
        "Read lines of an indexed source file (secrets redacted). Use after locating a node to quote real code.",
        _obj({"path": _STR, "start_line": {"type": "integer", "minimum": 1}, "end_line": {"type": "integer", "minimum": 1}}, ["path"]),
        lambda t, path, start_line=1, end_line=None: t.read_source_snippet(path, start_line, end_line),
    ),
    ToolSpec(
        "search_code",
        "Exact-text search across indexed files (like grep). Good for config keys, error messages, env vars.",
        _obj({"pattern": _STR, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ["pattern"]),
        lambda t, pattern, limit=20: t.search_code(pattern, limit=limit),
    ),
)

TOOL_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def openai_tools() -> list[dict[str, Any]]:
    """Tool definitions in the OpenAI/LiteLLM function-calling format."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}} for t in TOOLS]


def run_tool(tools: GraphTools, name: str, args: dict[str, Any] | None) -> Any:
    spec = TOOL_BY_NAME.get(name)
    if spec is None:
        return {"error": f"unknown tool {name!r}"}
    allowed = set(spec.parameters.get("properties", {}))
    clean = {k: v for k, v in (args or {}).items() if k in allowed and v is not None}
    try:
        return spec.run(tools, **clean)
    except TypeError as exc:
        return {"error": f"bad arguments for {name}: {exc}"}
    except Exception as exc:  # noqa: BLE001 - tool errors are reported to the model, not raised
        return {"error": f"{type(exc).__name__}: {exc}"}


def tool_result_text(result: Any) -> tuple[str, int]:
    """Serialised, redacted, size-capped tool output and the number of redactions."""
    text = json.dumps(result, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + '..."[truncated]"'
    return sanitize_for_llm(text)


def collect_refs(result: Any, out: dict[str, dict[str, Any]] | None = None, depth: int = 0) -> dict[str, dict[str, Any]]:
    """Every node-like dict in a tool result (has an id and a path) -> citation candidate."""
    out = {} if out is None else out
    if depth > 6:
        return out
    if isinstance(result, dict):
        nid = result.get("id")
        path = result.get("path") or result.get("source_path")
        if isinstance(nid, str) and len(nid) == 32 and nid not in out:
            out[nid] = {
                "node_id": nid,
                "label": result.get("name") or result.get("route") or nid[:8],
                "path": path,
                "line": result.get("line") or result.get("start_line"),
                "node_type": result.get("type") or result.get("node_type"),
            }
        for value in result.values():
            if isinstance(value, (dict, list)):
                collect_refs(value, out, depth + 1)
    elif isinstance(result, list):
        for item in result[:80]:
            collect_refs(item, out, depth + 1)
    return out
