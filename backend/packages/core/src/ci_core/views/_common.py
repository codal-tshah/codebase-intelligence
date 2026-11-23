"""Shared helpers for view modules."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from ci_core.insights import GraphIndex
from ci_core.models import EdgeRecord, EdgeType, GraphEdgeView, GraphNodeView, NodeRecord, NodeType

MAX_NODES = 220

_TEST_ROOT_SEGMENTS = frozenset({"tests", "test", "__tests__", "spec"})


def include_tests(params: dict[str, Any] | None) -> bool:
    """True when the client asked to keep test-scoped nodes (query `include_tests=1` or bool)."""
    if not params:
        return False
    raw = params.get("include_tests")
    if raw is True:
        return True
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes"}
    return bool(raw)


def is_test_record(node: NodeRecord) -> bool:
    """Union of view/suggestion heuristics for test-scoped nodes."""
    path = (node.source_path or node.qualified_name or node.name or "").replace("\\", "/").lower()
    test_segment = any(seg.startswith("test_") for seg in path.split("/"))
    first_seg = path.split("/")[0] if path else ""
    return (
        node.properties.get("layer") == "test"
        or "/tests/" in f"/{path}"
        or test_segment
        or ".test." in path
        or ".spec." in path
        or first_seg in _TEST_ROOT_SEGMENTS
    )


def is_test_node(index: GraphIndex, node_id: str) -> bool:
    node = index.nodes.get(node_id)
    return is_test_record(node) if node is not None else False


def node_view(node: NodeRecord, index: GraphIndex) -> GraphNodeView:
    props = dict(node.properties)
    props["fan_in"] = index.fan_in(node.id)
    props["fan_out"] = index.fan_out(node.id)
    return GraphNodeView(
        id=node.id,
        label=node.name,
        node_type=node.node_type.value,
        source_path=node.source_path,
        layer=props.get("layer"),
        complexity=props.get("complexity"),
        summary=props.get("summary"),
        tags=list(props.get("tags", [])),
        confidence=node.confidence,
        properties=props,
    )


def edge_view(edge: EdgeRecord) -> GraphEdgeView:
    return GraphEdgeView(
        id=edge.id,
        source=edge.source_id,
        target=edge.target_id,
        edge_type=edge.edge_type.value,
        confidence=edge.confidence,
        properties=edge.properties,
    )


def edges_between(index: GraphIndex, allowed: set[str], types: set[EdgeType] | None = None) -> list[GraphEdgeView]:
    out: list[GraphEdgeView] = []
    seen: set[tuple[str, str, str]] = set()
    for e in index.edges:
        if types is not None and e.edge_type not in types:
            continue
        if e.source_id not in allowed or e.target_id not in allowed:
            continue
        key = (e.source_id, e.target_id, e.edge_type.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge_view(e))
    return out


def nodes_of(index: GraphIndex, *types: NodeType) -> list[NodeRecord]:
    wanted = set(types)
    return [n for n in index.nodes.values() if n.node_type in wanted]


def expand(
    index: GraphIndex,
    seeds: Iterable[str],
    *,
    forward: set[EdgeType] | None = None,
    backward: set[EdgeType] | None = None,
    depth: int = 2,
    limit: int = MAX_NODES,
    skip: Callable[[str], bool] | None = None,
) -> set[str]:
    """BFS from `seeds` along outgoing `forward` and incoming `backward` edge types."""
    collected: set[str] = {s for s in seeds if s in index.nodes and (skip is None or not skip(s))}
    frontier: deque[tuple[str, int]] = deque((s, 0) for s in collected)
    while frontier and len(collected) < limit:
        cur, d = frontier.popleft()
        if d >= depth:
            continue
        if forward:
            for e in index.outgoing.get(cur, []):
                tid = e.target_id
                if e.edge_type in forward and tid not in collected and (skip is None or not skip(tid)):
                    collected.add(tid)
                    frontier.append((tid, d + 1))
        if backward:
            for e in index.incoming.get(cur, []):
                sid = e.source_id
                if e.edge_type in backward and sid not in collected and (skip is None or not skip(sid)):
                    collected.add(sid)
                    frontier.append((sid, d + 1))
    return collected
