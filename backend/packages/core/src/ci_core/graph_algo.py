"""Graph algorithms on the dependency subgraph (analytics only; extraction is unchanged).

One adapter over rustworkx (preferred, Rust core) with a networkx fallback. Both are
permissively licensed and run in-process on the already-loaded `GraphIndex`.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Collection
from functools import lru_cache

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import EdgeType


@lru_cache(maxsize=1)
def _backend() -> str:
    try:
        import rustworkx  # noqa: F401

        return "rustworkx"
    except ImportError:
        pass
    try:
        import networkx  # noqa: F401

        return "networkx"
    except ImportError as exc:
        raise ImportError("graph analytics need rustworkx (preferred) or networkx: pip install rustworkx") from exc


def backend_name() -> str:
    return _backend()


def _adjacency(index: GraphIndex, edge_types: Collection[EdgeType]) -> dict[str, list[str]]:
    """Node id -> distinct dependency targets (self-loops dropped), in stable edge order."""
    out: dict[str, dict[str, None]] = {}
    for e in index.edges:
        if e.edge_type in edge_types and e.source_id != e.target_id:
            out.setdefault(e.source_id, {})[e.target_id] = None
            out.setdefault(e.target_id, {})
    return {k: list(v) for k, v in out.items()}


def _sccs(adj: dict[str, list[str]]) -> list[list[str]]:
    ids = list(adj)
    if _backend() == "rustworkx":
        import rustworkx as rx

        graph = rx.PyDiGraph(multigraph=False)
        pos = dict(zip(ids, graph.add_nodes_from(ids), strict=True))
        graph.add_edges_from_no_data([(pos[s], pos[t]) for s, targets in adj.items() for t in targets])
        return [[graph[i] for i in comp] for comp in rx.strongly_connected_components(graph)]
    import networkx as nx

    graph = nx.DiGraph()
    graph.add_nodes_from(ids)
    graph.add_edges_from((s, t) for s, targets in adj.items() for t in targets)
    return [list(comp) for comp in nx.strongly_connected_components(graph)]


def strongly_connected_components(
    index: GraphIndex, edge_types: Collection[EdgeType] = DEPENDENCY_EDGES, *, min_size: int = 2
) -> list[list[str]]:
    """SCCs of the subgraph over `edge_types`; each is a set of mutually dependent nodes.

    Components smaller than `min_size` are dropped (a singleton is not a cycle). Largest first,
    members sorted, so the result is identical across backends.
    """
    comps = [sorted(c) for c in _sccs(_adjacency(index, edge_types)) if len(c) >= min_size]
    return sorted(comps, key=lambda c: (-len(c), c))


def dependency_cycles(
    index: GraphIndex, edge_types: Collection[EdgeType] = DEPENDENCY_EDGES
) -> list[dict[str, object]]:
    """One entry per cyclic component: its members and a shortest concrete cycle through it."""
    adj = _adjacency(index, edge_types)
    return [
        {"node_ids": comp, "size": len(comp), "cycle": shortest_cycle(adj, comp)}
        for comp in strongly_connected_components(index, edge_types)
    ]


def shortest_cycle(adj: dict[str, list[str]], component: list[str]) -> list[str]:
    """Shortest cycle through the first member, as ids ``[a, b, c]`` meaning a→b→c→a."""
    members = set(component)
    start = component[0]
    parent: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adj.get(cur, []):
            if nxt not in members:
                continue
            if nxt == start:
                path = [cur]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])  # type: ignore[arg-type]
                return path[::-1]
            if nxt not in parent:
                parent[nxt] = cur
                queue.append(nxt)
    return [start]
