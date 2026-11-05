"""Shared helpers for view modules."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from ci_core.insights import GraphIndex
from ci_core.models import EdgeRecord, EdgeType, GraphEdgeView, GraphNodeView, NodeRecord, NodeType

MAX_NODES = 220


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
) -> set[str]:
    """BFS from `seeds` along outgoing `forward` and incoming `backward` edge types."""
    collected: set[str] = set(s for s in seeds if s in index.nodes)
    frontier: deque[tuple[str, int]] = deque((s, 0) for s in collected)
    while frontier and len(collected) < limit:
        cur, d = frontier.popleft()
        if d >= depth:
            continue
        if forward:
            for e in index.outgoing.get(cur, []):
                if e.edge_type in forward and e.target_id not in collected:
                    collected.add(e.target_id)
                    frontier.append((e.target_id, d + 1))
        if backward:
            for e in index.incoming.get(cur, []):
                if e.edge_type in backward and e.source_id not in collected:
                    collected.add(e.source_id)
                    frontier.append((e.source_id, d + 1))
    return collected
