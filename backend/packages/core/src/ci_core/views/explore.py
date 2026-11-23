"""Hierarchical drill-down exploration: packages → modules → symbols with lifted dependency edges."""

from __future__ import annotations

import contextlib
from collections import defaultdict
from typing import Any

from ci_core.insights import DEPENDENCY_EDGES, GraphIndex
from ci_core.models import EdgeType, GraphEdgeView, GraphNodeView, NodeType
from ci_core.views import ViewModule, register_view
from ci_core.views._common import is_test_node, node_view

BUDGET = 250
SHOW_MORE = 200
# Max structural children surfaced per expanded node per request (pagination via extra_child_offsets).
STRUCT_CHILD_PAGE = 80


# Types that can list children in the explorer (structural containment).
_EXPAND_TYPES = frozenset(
    {
        NodeType.PROJECT,
        NodeType.PACKAGE,
        NodeType.MODULE,
        NodeType.CLASS,
        NodeType.COMPONENT,
        NodeType.MODEL,
    }
)

# Direct children we surface under MODULE (skip Field by default — ER view owns fields).
_MODULE_CHILD_TYPES = frozenset(
    {
        NodeType.CLASS,
        NodeType.FUNCTION,
        NodeType.ENDPOINT,
        NodeType.COMPONENT,
        NodeType.MODEL,
        NodeType.MIDDLEWARE,
        NodeType.MIGRATION,
        NodeType.TABLE,
        NodeType.CONFIG_REF,
    }
)


def _project_id(index: GraphIndex) -> str | None:
    for n in index.nodes.values():
        if n.node_type == NodeType.PROJECT:
            return n.id
    return None


def _contains_parent(index: GraphIndex) -> dict[str, str]:
    # Cached on the index: these helpers run once per visible node, so rescanning every edge
    # here made each explore request O(visible x edges).
    return index.contains_parent


def _contains_children(index: GraphIndex) -> dict[str, list[str]]:
    return index.contains_children


def _expand_closure(index: GraphIndex, expanded: set[str]) -> set[str]:
    """Tree-view semantics: an expanded node only takes effect when every CONTAINS ancestor
    (below the project) is expanded too. Collapsing a parent therefore hides its expanded
    descendants without forgetting them, and re-expanding restores them.

    (Previously ancestors were auto-added, which made collapsing a parent with an expanded
    child impossible: the closure immediately re-expanded it.)
    """
    parent = _contains_parent(index)
    effective: set[str] = set()
    for eid in expanded:
        cur = eid
        ok = True
        guard = 0
        while cur in parent and guard < 256:
            p = parent[cur]
            guard += 1
            if p not in index.nodes or index.nodes[p].node_type == NodeType.PROJECT:
                break
            if index.nodes[p].node_type in _EXPAND_TYPES and p not in expanded:
                ok = False
                break
            cur = p
        if ok:
            effective.add(eid)
    return effective


def _direct_structural_children(index: GraphIndex, nid: str) -> list[str]:
    node = index.nodes.get(nid)
    if node is None:
        return []
    raw = _contains_children(index).get(nid, [])
    out: list[str] = []
    for cid in raw:
        c = index.nodes.get(cid)
        if c is None:
            continue
        if node.node_type in (NodeType.PROJECT, NodeType.PACKAGE):
            if c.node_type in (NodeType.PACKAGE, NodeType.MODULE):
                out.append(cid)
        elif node.node_type == NodeType.MODULE:
            if c.node_type in _MODULE_CHILD_TYPES:
                out.append(cid)
        elif node.node_type in (NodeType.CLASS, NodeType.COMPONENT, NodeType.MODEL):
            if c.node_type in (
                NodeType.FUNCTION,
                NodeType.CLASS,
                NodeType.FIELD,
                NodeType.ENDPOINT,
                NodeType.COMPONENT,
            ):
                out.append(cid)
        else:
            out.append(cid)
    out.sort(key=lambda i: (index.nodes[i].node_type.value, index.nodes[i].name))
    return out


def _top_level_roots(index: GraphIndex, proj: str) -> list[str]:
    kids = _direct_structural_children(index, proj)
    if not kids:
        return []
    if any(index.nodes[i].node_type == NodeType.PACKAGE for i in kids):
        return [i for i in kids if index.nodes[i].node_type == NodeType.PACKAGE]
    return kids


def _is_expandable(index: GraphIndex, nid: str) -> bool:
    n = index.nodes.get(nid)
    if n is None or n.node_type not in _EXPAND_TYPES:
        return False
    return bool(_direct_structural_children(index, nid))


# Deepest level offered by "expand to level" (the UI also offers "All", sent as this value).
MAX_LEVEL = 64
_DEPTH_ATTR = "_explore_structural_depths"


def structural_depths(index: GraphIndex) -> dict[str, int]:
    """Absolute Explore level of every structural node: top-level roots are level 1, their
    children level 2, and so on. Cached per loaded index (the store rebuilds it on re-index)."""
    cached = index.__dict__.get(_DEPTH_ATTR)
    if isinstance(cached, dict):
        return cached
    proj = _project_id(index)
    depths: dict[str, int] = {}
    if proj:
        frontier = _top_level_roots(index, proj)
        for r in frontier:
            depths[r] = 1
        while frontier:
            nxt: list[str] = []
            for nid in frontier:
                for c in _direct_structural_children(index, nid):
                    if c not in depths:
                        depths[c] = depths[nid] + 1
                        nxt.append(c)
            frontier = nxt
    index.__dict__[_DEPTH_ATTR] = depths
    return depths


def expansion_for_level(
    index: GraphIndex, level: int, budget: int = BUDGET, root: str | None = None
) -> tuple[set[str], int, bool]:
    """Expanded set that opens the tree down to absolute `level` (level 1 = top-level roots).

    With `root`, only that node's subtree is opened (and its ancestors, so it is on the canvas).
    Opens one level at a time. When a whole level does not fit in the visible-node budget, the
    busiest nodes of that level are opened first until the budget is used, and `capped` is set
    so the UI can say so. Returns (expanded ids, deepest level reached, capped?).
    """
    proj = _project_id(index)
    if not proj:
        return set(), 1, False
    depths = structural_depths(index)
    expanded: set[str] = set()
    if root and root in index.nodes and root in depths:
        parent = _contains_parent(index)
        cur = parent.get(root)
        while cur and cur in depths:  # ancestors (below the project) must be open
            expanded.add(cur)
            cur = parent.get(cur)
        frontier = [root]
        start = depths[root]
        visible = len(_top_level_roots(index, proj)) + sum(len(_direct_structural_children(index, a)) for a in expanded)
    else:
        frontier = _top_level_roots(index, proj)
        start = 1
        visible = len(frontier)
    reached = start
    for lv in range(start, max(start, level)):
        openable = [n for n in frontier if _is_expandable(index, n)]
        if not openable:
            break
        pages = {n: _direct_structural_children(index, n)[:STRUCT_CHILD_PAGE] for n in openable}
        total = sum(len(k) for k in pages.values())
        if visible + total > budget:
            # partial level: busiest first, so the parts of the code that matter most open first
            for n in sorted(
                openable,
                key=lambda i: (is_test_node(index, i), -index.degree(i), index.nodes[i].name),
            ):
                if visible + len(pages[n]) > budget:
                    continue
                expanded.add(n)
                visible += len(pages[n])
            return expanded, reached, True
        expanded.update(openable)
        visible += total
        frontier = [c for n in openable for c in pages[n]]
        reached = lv + 1
    return expanded, reached, False


def _collect_visible(
    index: GraphIndex,
    proj: str,
    expanded: set[str],
    extra_child_offsets: dict[str, int],
) -> tuple[set[str], dict[str, int], dict[str, int]]:
    """
    Visible nodes: roots + recursive children of every expanded node.

    For expanded nodes, only a page of structural children is included (STRUCT_CHILD_PAGE),
    starting at extra_child_offsets.get(nid, 0). Returns (visible, child_count, truncated_children).
    """
    visible: set[str] = set()
    child_count: dict[str, int] = {}
    truncated_children: dict[str, int] = {}

    def visit(nid: str) -> None:
        visible.add(nid)
        all_ch = _direct_structural_children(index, nid)
        child_count[nid] = len(all_ch)
        if nid not in expanded:
            return
        off = max(0, int(extra_child_offsets.get(nid, 0) or 0))
        page = all_ch[off : off + STRUCT_CHILD_PAGE]
        rest = len(all_ch) - off - len(page)
        if rest > 0:
            truncated_children[nid] = rest
        for c in page:
            visit(c)

    roots = _top_level_roots(index, proj)
    for r in roots:
        visit(r)
    return visible, child_count, truncated_children


def _lift_to_visible(index: GraphIndex, nid: str | None, visible: set[str], parent: dict[str, str]) -> str | None:
    if nid is None:
        return None
    cur: str | None = nid
    seen = 0
    while cur and cur in index.nodes and seen < 512:
        seen += 1
        if cur in visible:
            return cur
        cur = parent.get(cur)
    return None


def _aggregate_edges(
    index: GraphIndex, visible: set[str], parent: dict[str, str]
) -> tuple[list[GraphEdgeView], list[GraphEdgeView]]:
    """Returns (contains_edges, dependency_agg_edges)."""
    contains_out: list[GraphEdgeView] = []
    seen_c: set[tuple[str, str]] = set()
    for e in index.edges:
        if e.edge_type != EdgeType.CONTAINS:
            continue
        if e.source_id in visible and e.target_id in visible:
            key = (e.source_id, e.target_id)
            if key in seen_c:
                continue
            seen_c.add(key)
            contains_out.append(
                GraphEdgeView(
                    id=e.id,
                    source=e.source_id,
                    target=e.target_id,
                    edge_type=e.edge_type.value,
                    confidence=e.confidence,
                    properties=dict(e.properties),
                )
            )

    weights: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    conf: dict[tuple[str, str], list[float]] = defaultdict(list)
    raw_counts: dict[tuple[str, str], int] = defaultdict(int)
    lift_mismatch: dict[tuple[str, str], bool] = defaultdict(bool)
    for e in index.edges:
        if e.edge_type not in DEPENDENCY_EDGES:
            continue
        if e.edge_type == EdgeType.CONTAINS:
            continue
        s0, t0 = e.source_id, e.target_id
        s = _lift_to_visible(index, s0, visible, parent)
        t = _lift_to_visible(index, t0, visible, parent)
        if not s or not t or s == t:
            continue
        key2 = (s, t)
        weights[key2][e.edge_type.value] += 1
        conf[key2].append(e.confidence)
        raw_counts[key2] += 1
        if s0 != s or t0 != t:
            lift_mismatch[key2] = True

    dep_edges: list[GraphEdgeView] = []
    for (a, b), by_type in weights.items():
        total = sum(by_type.values())
        dominant = max(by_type, key=lambda k: by_type[k])
        min_conf = min(conf[(a, b)]) if conf[(a, b)] else 1.0
        uc = raw_counts[(a, b)]
        dep_edges.append(
            GraphEdgeView(
                id=f"explore-agg:{a}:{b}:{dominant}",
                source=a,
                target=b,
                edge_type=dominant,
                confidence=min_conf,
                properties={
                    "weight": total,
                    "by_type": dict(by_type),
                    "underlying_edge_count": uc,
                    "aggregated": uc > 1 or lift_mismatch[(a, b)],
                },
            )
        )
    return contains_out, dep_edges


def _parse_offsets_param(params: dict[str, Any]) -> dict[str, int]:
    """Parse extra_child_offsets: JSON object, comma key=value, or FastAPI list of key=value strings."""
    raw = params.get("extra_child_offsets") or params.get("child_offsets")
    out: dict[str, int] = {}
    if raw is None:
        return out
    if isinstance(raw, list):
        for item in raw:
            s = str(item).strip()
            if "=" in s:
                k, _, v = s.partition("=")
                k, v = k.strip(), v.strip()
                if k:
                    with contextlib.suppress(TypeError, ValueError):
                        out[k] = max(0, int(v))
        return out
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            import json

            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k, v in obj.items():
                    with contextlib.suppress(TypeError, ValueError):
                        out[str(k)] = max(0, int(v))
        except Exception:
            pass
        return out
    if isinstance(raw, str):
        for chunk in raw.split(","):
            part = chunk.strip()
            if "=" in part:
                k, _, v = part.partition("=")
                k, v = k.strip(), v.strip()
                if k:
                    with contextlib.suppress(TypeError, ValueError):
                        out[k] = max(0, int(v))
    return out


def _visible_depths(parent_id: dict[str, str | None]) -> dict[str, int]:
    """Nesting depth on the canvas (0 = drawn at the root), one pass over a child map."""
    children: dict[str | None, list[str]] = defaultdict(list)
    for nid, p in parent_id.items():
        children[p].append(nid)
    depth: dict[str, int] = {}
    queue = [(r, 0) for r in children.get(None, [])]
    while queue:
        u, d = queue.pop()
        depth[u] = d
        queue.extend((v, d + 1) for v in children.get(u, []))
    return depth


def _nearest_visible_parent(nid: str, visible: set[str], parent_map: dict[str, str]) -> str | None:
    cur: str | None = nid
    guard = 0
    while cur and guard < 512:
        cand = parent_map.get(cur)
        if not cand:
            break
        if cand in visible:
            return cand
        cur = cand
        guard += 1
    return None


def _explore_visible_bundle(
    index: GraphIndex,
    proj: str,
    expanded_set: set[str],
    extra_child_offsets: dict[str, int],
) -> tuple[
    set[str],
    dict[str, int],
    dict[str, int],
    dict[str, str | None],
    dict[str, int],
    bool,
    str,
]:
    """
    Single pass: visible set, per-node total child counts, truncated_children (unshown struct kids),
    parent_id (nearest visible CONTAINS ancestor), depth from visible roots, global truncation.
    """
    visible, child_count, trunc_page = _collect_visible(index, proj, expanded_set, extra_child_offsets)
    parent_map = _contains_parent(index)

    parent_id = {nid: _nearest_visible_parent(nid, visible, parent_map) for nid in visible}

    depth = _visible_depths(parent_id)

    truncated_children = dict(trunc_page)
    truncated = False
    reason = ""
    if len(visible) > BUDGET:
        truncated = True
        reason = f"visible node budget ({BUDGET}) exceeded"
        ranked = sorted(visible, key=lambda i: (-index.degree(i), index.nodes[i].name))
        keep = set(ranked[:SHOW_MORE])
        root_ids = set(_top_level_roots(index, proj))
        visible = keep | root_ids | expanded_set
        visible = {v for v in visible if v in index.nodes}
        if len(visible) > BUDGET:
            visible = set(ranked[:BUDGET])
        child_count = {k: v for k, v in child_count.items() if k in visible}
        truncated_children = {k: v for k, v in truncated_children.items() if k in visible}
        parent_id = {nid: _nearest_visible_parent(nid, visible, parent_map) for nid in visible}
        depth = _visible_depths(parent_id)

    return visible, child_count, truncated_children, parent_id, depth, truncated, reason


def build(
    index: GraphIndex, focus: str | None, params: dict[str, Any] | None = None
) -> tuple[list[GraphNodeView], list[GraphEdgeView], dict[str, Any]]:
    params = params or {}
    proj = _project_id(index)
    if not proj:
        return [], [], {"reason": "no project root in index"}

    expanded_raw = params.get("expanded") or params.get("expanded_ids")
    expanded_set: set[str] = set()
    if isinstance(expanded_raw, str) and expanded_raw.strip():
        expanded_set = {s.strip() for s in expanded_raw.split(",") if s.strip()}
    elif isinstance(expanded_raw, (list, tuple, set)):
        expanded_set = {str(s).strip() for s in expanded_raw if str(s).strip()}

    expanded_set = {e for e in expanded_set if e in index.nodes}

    # "Expand to level N": open every node above level N (within the node budget), on top of
    # what is already expanded. Collapsing is done by the client from `expanded_depths`.
    level_info: dict[str, Any] = {}
    raw_level = params.get("expand_to_level")
    if raw_level not in (None, ""):
        try:
            level = max(1, min(MAX_LEVEL, int(raw_level)))
        except (TypeError, ValueError):
            level = 1
        root = params.get("level_root")
        opened, reached, capped = expansion_for_level(index, level, root=str(root) if root else None)
        expanded_set |= opened
        level_info = {"requested_level": level, "level_reached": reached, "level_capped": capped}

    expanded_set = _expand_closure(index, expanded_set)

    extra_offsets = _parse_offsets_param(params)
    visible, child_count, truncated_children, parent_id, depth, truncated, reason = _explore_visible_bundle(
        index, proj, expanded_set, extra_offsets
    )
    parent = _contains_parent(index)

    nodes_out: list[GraphNodeView] = []
    for nid in sorted(visible, key=lambda i: (index.nodes[i].node_type.value, index.nodes[i].name)):
        n = index.nodes[nid]
        view = node_view(n, index)
        cnt = child_count[nid] if nid in child_count else len(_direct_structural_children(index, nid))
        exp = _is_expandable(index, nid)
        view.properties["explore_expandable"] = exp
        view.properties["child_count"] = cnt
        view.properties["explore_expanded"] = nid in expanded_set
        view.properties["parent_id"] = parent_id.get(nid)
        view.properties["depth"] = depth.get(nid, 0)
        view.properties["truncated_children"] = truncated_children.get(nid, 0)
        nodes_out.append(view)

    cedges, dedges = _aggregate_edges(index, visible, parent)
    edges_out = cedges + dedges

    abs_depth = structural_depths(index)
    meta = {
        "explore": {
            "expanded": sorted(expanded_set),
            "project_id": proj,
            # deepest level in the structural tree (the UI offers levels 1..max_depth)
            "max_depth": max(abs_depth.values(), default=1),
            "expanded_depths": {e: abs_depth.get(e, 1) for e in expanded_set},
            **level_info,
        },
        "truncated": truncated,
        "truncation_reason": reason if truncated else None,
    }
    return nodes_out, edges_out, meta


def underlying_between(
    index: GraphIndex,
    source_id: str,
    target_id: str,
    expanded_raw: str | None,
    cap: int = 200,
    *,
    extra_offsets: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Public helper for API: underlying edges between two visible explore nodes."""
    from ci_core.views.explore_edges import underlying_edges_between_visible

    proj = _project_id(index)
    if not proj or source_id not in index.nodes or target_id not in index.nodes:
        return []

    expanded_set: set[str] = set()
    if isinstance(expanded_raw, str) and expanded_raw.strip():
        expanded_set = {s.strip() for s in expanded_raw.split(",") if s.strip()}
    expanded_set = {e for e in expanded_set if e in index.nodes}
    expanded_set = _expand_closure(index, expanded_set)

    visible, _, _, _, _, _, _ = _explore_visible_bundle(index, proj, expanded_set, extra_offsets or {})
    parent = _contains_parent(index)
    return underlying_edges_between_visible(index, source_id, target_id, visible, parent, cap=cap)


register_view(
    ViewModule(
        id="explore",
        label="Explore",
        description="Hierarchical drill-down from packages to files and symbols",
        icon="⊞",
        build=build,
        order=15,
        requires=(),
        best_for=(NodeType.PACKAGE, NodeType.PROJECT, NodeType.MODULE),
        group="overview",
    )
)
