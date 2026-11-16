"""Shared JSON shapes for API responses and tool output."""

from __future__ import annotations

from typing import Any

from ci_core.models import NodeRecord


def node_summary(node: NodeRecord, *, score: float | None = None) -> dict[str, Any]:
    """Compact node dict used by HTTP routes (search, path, tour enrichment)."""
    out: dict[str, Any] = {
        "id": node.id,
        "name": node.name,
        "node_type": node.node_type.value,
        "source_path": node.source_path,
        "start_line": node.start_line,
        "layer": node.properties.get("layer"),
        "summary": node.properties.get("summary"),
    }
    if score is not None:
        out["score"] = score
    return out


def tool_node_brief(node: NodeRecord) -> dict[str, Any]:
    """Node dict for LLM/MCP tools (includes qualified name and legacy `type` key)."""
    return {
        "id": node.id,
        "name": node.name,
        "type": node.node_type.value,
        "path": node.source_path,
        "line": node.start_line,
        "qualified_name": node.qualified_name,
        "layer": node.properties.get("layer"),
        "summary": node.properties.get("summary"),
    }
