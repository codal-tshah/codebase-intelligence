"""Graph views, Explore paging, node details, source, search, path, impact and exports."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response

from ci_ai import GraphTools
from ci_api.deps import MAX_ID, check_expanded, pid, require_project
from ci_api.schemas import ImpactBody
from ci_core.db import GraphStore
from ci_core.insights import (
    build_tour,
    find_path,
    impact_for_request,
    list_endpoints,
    neighborhood_subgraph,
    search_nodes,
)
from ci_core.layers import layer_catalog
from ci_core.serializers import node_summary
from ci_core.settings import get_settings
from ci_core.source import resolve_source_path
from ci_core.views import get_view
from ci_core.views.explore import _parse_offsets_param, underlying_between
from ci_indexer import compute_freshness

router = APIRouter()


@router.get("/projects/{project_ref:path}/endpoints")
def endpoints(project_ref: str, q: str | None = Query(default=None, max_length=200)) -> dict:
    """API explorer: every route with handler, guards, frontend callers and models touched."""
    items = list_endpoints(GraphStore(pid(project_ref)).load_index(), query=q)
    return {"count": len(items), "endpoints": items}


@router.get("/projects/{project_ref:path}/models")
def models(project_ref: str) -> dict:
    """Data models with tables, fields, relations, and the code that reads/writes them."""
    items = GraphTools(pid(project_ref)).models(limit=500)
    return {"count": len(items), "models": items}


@router.get("/projects/{project_ref:path}/background-jobs")
def background_jobs(project_ref: str) -> dict:
    """Background tasks, scheduled jobs and management commands with the models they read/write."""
    items = GraphTools(pid(project_ref)).jobs()
    return {"count": len(items), "jobs": items}


@router.get("/projects/{project_ref:path}/suggestions")
def suggestions(project_ref: str, limit: int = Query(default=40, ge=1, le=200)) -> dict:
    """Optimization and reuse leads derived from the graph."""
    items = GraphTools(pid(project_ref)).suggestions(limit=limit)
    return {"count": len(items), "suggestions": items}


@router.get("/projects/{project_ref:path}/graph/neighborhood")
def graph_neighborhood(
    project_ref: str,
    node_id: str = Query(..., min_length=1, max_length=MAX_ID),
    direction: str = Query("both", max_length=8),
    depth: int = Query(1, ge=1, le=3),
) -> dict:
    d = direction.lower()
    if d not in {"in", "out", "both"}:
        raise HTTPException(status_code=422, detail="direction must be in, out, or both")
    index = GraphStore(pid(project_ref)).load_index()
    if node_id not in index.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    return neighborhood_subgraph(index, node_id, direction=d, depth=depth)


@router.get("/projects/{project_ref:path}/graph/edges")
def graph_explore_underlying_edges(
    project_ref: str,
    source: str = Query(
        ..., min_length=1, max_length=MAX_ID, description="Visible explore node id (aggregated arc source)"
    ),
    target: str = Query(
        ..., min_length=1, max_length=MAX_ID, description="Visible explore node id (aggregated arc target)"
    ),
    expanded: str | None = Query(
        default=None, description="Same expanded= list as /graph/explore so lifting matches the canvas"
    ),
    extra_child_offsets: list[str] | None = Query(
        default=None, description="Same as explore view: node_id=offset for structural paging"
    ),
    include_tests: bool = Query(
        default=False,
        description="Same as explore view: include test-scoped nodes when computing the visible lift set",
    ),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    check_expanded(expanded, extra_child_offsets)
    index = GraphStore(pid(project_ref)).load_index()
    if source not in index.nodes or target not in index.nodes:
        raise HTTPException(status_code=404, detail="node not found")
    off: dict[str, int] = _parse_offsets_param({"extra_child_offsets": extra_child_offsets or []})
    edges = underlying_between(
        index, source, target, expanded, cap=limit + 1, extra_offsets=off, show_tests=include_tests
    )
    capped = len(edges) > limit  # fetched one extra row: only true when something was cut off
    return {"source": source, "target": target, "edges": edges[:limit], "capped": capped}


@router.get("/projects/{project_ref:path}/graph/{view}")
def get_graph(
    project_ref: str,
    view: str,
    focus_node_id: str | None = Query(default=None, max_length=MAX_ID),
    expanded: str | None = Query(default=None, description="Comma-separated node ids expanded in explore view"),
    extra_child_offsets: list[str] | None = Query(
        default=None,
        description="Repeat param: node_id=offset for paging structural children under expanded nodes",
    ),
    expand_to_level: int | None = Query(
        default=None, ge=1, le=64, description="Explore: also open every node above this level (within the node budget)"
    ),
    level_root: str | None = Query(
        default=None, max_length=MAX_ID, description="Explore: apply expand_to_level only inside this node's subtree"
    ),
    include_tests: bool = Query(
        default=False,
        description="Include test-layer nodes in integrations, call-graph, architecture, and explore",
    ),
) -> dict:
    if get_view(view) is None:
        raise HTTPException(status_code=404, detail=f"unknown view {view[:64]!r}")
    check_expanded(expanded, extra_child_offsets)
    params: dict = {}
    if expanded:
        params["expanded"] = expanded
    if extra_child_offsets:
        params["extra_child_offsets"] = extra_child_offsets
    if expand_to_level:
        params["expand_to_level"] = expand_to_level
        if level_root:
            params["level_root"] = level_root
    if include_tests:
        params["include_tests"] = True
    payload = GraphStore(pid(project_ref)).build_graph_view(view, focus_node_id=focus_node_id, params=params or None)
    return payload.model_dump(mode="json")


@router.get("/projects/{project_ref:path}/export")
def export_graph(project_ref: str) -> Response:
    """Download the complete knowledge graph (nodes + edges + layers) as JSON."""
    project = require_project(project_ref)
    index = GraphStore(project.id).load_index()
    from ci_core.evidence import edge_with_evidence

    payload = {
        "version": 1,
        "project": project.model_dump(mode="json"),
        "layers": layer_catalog(),
        "nodes": [n.model_dump(mode="json", exclude={"project_id"}) for n in index.nodes.values()],
        "edges": [edge_with_evidence(e) for e in index.edges],
    }
    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{project.name}-graph.json"'},
    )


@router.get("/projects/{project_ref:path}/tour")
def tour(project_ref: str) -> dict:
    """Guided walkthrough: where a newcomer should read first."""
    index = GraphStore(pid(project_ref)).load_index()
    steps = build_tour(index)
    for step in steps:
        step["nodes"] = [node_summary(index.nodes[nid]) for nid in step["node_ids"] if nid in index.nodes]
    return {"steps": steps}


@router.get("/projects/{project_ref:path}/search")
def search(
    project_ref: str,
    q: str = Query(..., min_length=1, max_length=200),
    types: str | None = Query(default=None, description="Comma-separated node types"),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    nodes = GraphStore(pid(project_ref)).list_all_nodes()
    wanted = {t.strip() for t in types.split(",") if t.strip()} if types else None
    hits = search_nodes(nodes, q, types=wanted, limit=limit)
    return {"query": q, "results": [node_summary(n, score=score) for n, score in hits]}


@router.get("/projects/{project_ref:path}/path")
def shortest_path(
    project_ref: str,
    source: str = Query(..., max_length=MAX_ID, description="Source node id"),
    target: str = Query(..., max_length=MAX_ID, description="Target node id"),
    max_hops: int = Query(12, ge=1, le=30),
) -> dict:
    index = GraphStore(pid(project_ref)).load_index()
    result = find_path(index, source, target, max_hops=max_hops)
    result["nodes"] = [node_summary(index.nodes[nid]) for nid in result.get("node_ids", []) if nid in index.nodes]
    return result


@router.post("/projects/{project_ref:path}/impact")
def impact(project_ref: str, body: ImpactBody) -> dict:
    project = require_project(project_ref)
    index = GraphStore(project.id).load_index()
    files = [f.replace("\\", "/") for f in body.files]
    source = "files" if files else "nodes"
    if body.base and not files and not body.node_ids:
        from ci_parsers import git_changed_between

        diff = git_changed_between(Path(project.root_path), body.base)
        if diff is None:
            raise HTTPException(status_code=400, detail=f"could not diff against {body.base!r}")
        files = diff
        source = "git-ref"
    elif not files and not body.node_ids:
        fresh = compute_freshness(project.id, Path(project.root_path))
        files = list(fresh.get("changed_files", []))
        source = "working-tree"
    report = impact_for_request(index, files=files, node_ids=body.node_ids, depth=body.depth)
    report["source"] = source
    return report


@router.get("/projects/{project_ref:path}/nodes/{node_id}")
def get_node(project_ref: str, node_id: str) -> dict:
    if len(node_id) > MAX_ID:
        raise HTTPException(status_code=422, detail="node id too long")
    index = GraphStore(pid(project_ref)).load_index()
    node = index.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    edges = [*index.outgoing.get(node_id, []), *index.incoming.get(node_id, [])]
    neighbours: dict[str, dict] = {}
    for e in edges:
        other_id = e.target_id if e.source_id == node_id else e.source_id
        other = index.nodes.get(other_id)
        if other:
            neighbours[other_id] = {
                "id": other.id,
                "name": other.name,
                "node_type": other.node_type.value,
                "source_path": other.source_path,
                "layer": other.properties.get("layer"),
            }
    from ci_core.evidence import classify_http_call_record, classify_node, edge_with_evidence

    node_dump = node.model_dump(mode="json")
    props = dict(node_dump.get("properties") or {})
    raw_calls = props.get("http_calls") or []
    if isinstance(raw_calls, list):
        props["http_calls"] = [
            {**c, "evidence": classify_http_call_record(c)} if isinstance(c, dict) else c for c in raw_calls
        ]
    node_dump["properties"] = props
    node_dump["evidence"] = classify_node(node)
    return {
        "node": node_dump,
        "edges": [edge_with_evidence(e) for e in edges],
        "neighbors": neighbours,
    }


@router.get("/projects/{project_ref:path}/source")
def get_source(
    project_ref: str,
    path: str = Query(..., min_length=1, max_length=1024),
    start: int = Query(1, ge=1),
    end: int | None = Query(default=None, ge=1),
) -> dict:
    project = require_project(project_ref)
    allowed = GraphStore(project.id).indexed_paths()
    candidate = resolve_source_path(Path(project.root_path), path, allowed)
    if candidate is None:
        raise HTTPException(status_code=404, detail="not an indexed source file")
    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    end_line = min(end or start + 80, len(lines), start + 400)
    out = {
        "path": path,
        "start": start,
        "end": end_line,
        "total_lines": len(lines),
        "language": _language_for(path),
        "abs_path": str(candidate),
        "content": "\n".join(lines[start - 1 : end_line]),
    }
    if get_settings().mode == "server":
        out.pop("abs_path")  # don't reveal the server's filesystem layout to API clients
    return out


def _language_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python",
        "ts": "typescript",
        "tsx": "tsx",
        "js": "javascript",
        "jsx": "jsx",
        "mjs": "javascript",
        "cjs": "javascript",
    }.get(ext, ext or "text")
