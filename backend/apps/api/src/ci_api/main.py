from __future__ import annotations

import hmac
import logging
import re
import uuid
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from ci_ai import GraphTools, build_project_summary, chat_stream
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
from ci_core.views import get_view, view_catalog
from ci_core.logging_setup import configure_logging, request_id
from ci_core.models import ProjectRecord
from ci_core.projects import resolve_project
from ci_core.registry import load_registry
from ci_core.serializers import node_summary
from ci_core.settings import get_settings
from ci_core.source import resolve_source_path
from ci_indexer import (
    analyzer_catalog,
    compute_freshness,
    create_project_from_git,
    create_project_from_path,
    run_index_job,
)

_settings = get_settings()  # fails fast on invalid configuration (e.g. CI_MODE=server without a key)
configure_logging(_settings.log_level, _settings.log_json)
log = logging.getLogger("ci_api")


def _reconcile_orphaned_index_jobs() -> None:
    n = 0
    for p in load_registry():
        n += GraphStore(p.id).fail_orphaned_running_jobs()
    if n:
        log.warning("marked %d orphaned index job(s) as failed on startup", n)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _reconcile_orphaned_index_jobs()
    yield


app = FastAPI(title="Codebase Intelligence API", version="0.3.0", lifespan=_lifespan)

# Local-first: only the dev UI origins by default. Extend with CI_CORS_ORIGINS="https://a,https://b".
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request, call_next):
    """Correlation id on every request/response and, in server mode, API-key authentication."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id.set(rid)
    try:
        settings = get_settings()
        if settings.mode == "server" and request.method != "OPTIONS" and request.url.path != "/health":
            supplied = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not settings.api_key or not hmac.compare_digest(supplied, settings.api_key):
                return JSONResponse({"detail": "invalid or missing API key"}, status_code=401, headers={"X-Request-ID": rid})
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    except Exception:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "internal error", "request_id": rid}, status_code=500, headers={"X-Request-ID": rid})
    finally:
        request_id.reset(token)


_GITHUB_URL = re.compile(r"^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?(\.git)?$", re.I)


class ChatMessage(BaseModel):
    role: str
    content: str


class CreateProjectBody(BaseModel):
    path: str | None = None
    git_url: str | None = Field(default=None, description="Public GitHub repository URL")

    @field_validator("git_url")
    @classmethod
    def validate_git_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not _GITHUB_URL.match(v):
            raise ValueError("Must be a valid GitHub repository URL (https://github.com/owner/repo)")
        return v


class ImpactBody(BaseModel):
    """Blast radius of a change. With no files/nodes, the working tree's changed files are used."""

    files: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    base: str | None = Field(default=None, description="Git ref to diff against (e.g. origin/main); ignored if files set")
    depth: int = Field(default=3, ge=1, le=6)


def _register(body: "CreateProjectBody") -> ProjectRecord:
    """Create a project from a path or GitHub URL (server mode confines paths to CI_PROJECT_ROOTS)."""
    if body.path:
        path = Path(body.path)
        if not get_settings().path_allowed(path):
            raise HTTPException(status_code=403, detail="path is outside the allowed project roots")
        if not path.expanduser().is_dir():
            raise HTTPException(status_code=400, detail=f"not a directory: {body.path}")
        return create_project_from_path(path)
    if body.git_url:
        if get_settings().mode == "server":
            raise HTTPException(
                status_code=403,
                detail="git_url ingest is disabled in server mode; clone under CI_PROJECT_ROOTS and use path",
            )
        return create_project_from_git(body.git_url)
    raise HTTPException(status_code=400, detail="path or git_url required")


def _require_project(project_ref: str) -> ProjectRecord:
    project = resolve_project(project_ref)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def _pid(ref: str) -> str:
    return _require_project(ref).id


class AnalyzeBody(CreateProjectBody):
    """Create project and run a full index (ingest + graph + embeddings)."""


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    focus_node_id: str | None = None
    conversation_history: list[ChatMessage] = Field(default_factory=list)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/projects")
def list_projects() -> list[dict]:
    return [p.model_dump(mode="json") for p in load_registry()]


@app.get("/projects/resolve")
def resolve(ref: str = Query(..., min_length=1, max_length=1024)) -> dict:
    """Resolve an id, name, or a path inside a repo to its registered project (same rules as the CLI and MCP)."""
    record = resolve_project(ref)
    if record is None:
        raise HTTPException(status_code=404, detail="no matching project")
    return record.model_dump(mode="json")


@app.post("/projects")
def create_project(body: CreateProjectBody) -> dict:
    return _register(body).model_dump(mode="json")


@app.post("/projects/analyze")
def analyze_project(body: AnalyzeBody) -> dict:
    """Ingest-style flow: register project, index synchronously, return summary."""
    record = _register(body)
    job = run_index_job(record.id)
    if job.status.value == "failed":
        raise HTTPException(status_code=500, detail=job.error or "Index failed")
    summary = build_project_summary(record.id)
    return {
        "project": record.model_dump(mode="json"),
        "job": job.model_dump(mode="json"),
        "summary": summary,
    }


@app.get("/layers")
def layers() -> list[dict]:
    """The framework-neutral architectural layer taxonomy (id, name, description, colour)."""
    return layer_catalog()


@app.get("/analyzers")
def analyzers() -> list[dict]:
    """Installed language/framework analyzers (built-ins plus entry-point plugins)."""
    return analyzer_catalog()


@app.get("/views")
def views() -> list[dict]:
    """Registered diagram modules (without project-specific availability)."""
    return view_catalog()


@app.get("/projects/{project_ref:path}/views")
def project_views(project_ref: str) -> list[dict]:
    """Diagram modules with availability and counts for this project's graph."""
    return view_catalog(GraphStore(_pid(project_ref)).load_index())


@app.get("/projects/{project_ref:path}/endpoints")
def endpoints(project_ref: str, q: str | None = Query(default=None, max_length=200)) -> dict:
    """API explorer: every route with handler, guards, frontend callers and models touched."""
    pid = _pid(project_ref)
    items = list_endpoints(GraphStore(pid).load_index(), query=q)
    return {"count": len(items), "endpoints": items}


@app.get("/projects/{project_ref:path}/models")
def models(project_ref: str) -> dict:
    """Data models with tables, fields, relations, and the code that reads/writes them."""
    pid = _pid(project_ref)
    items = GraphTools(pid).models(limit=500)
    return {"count": len(items), "models": items}


@app.get("/projects/{project_ref:path}/summary")
def project_summary(project_ref: str) -> dict:
    return build_project_summary(_pid(project_ref))


@app.get("/projects/{project_ref:path}/freshness")
def freshness(project_ref: str) -> dict:
    """fresh | dirty | stale | unknown, with the files that differ from the index."""
    project = _require_project(project_ref)
    return compute_freshness(project.id, Path(project.root_path))


@app.post("/projects/{project_ref:path}/index")
def index_project(project_ref: str, background: BackgroundTasks, incremental: bool = False) -> dict:
    """Start an index job. `incremental=true` skips unchanged work; default forces a rebuild."""
    pid = _pid(project_ref)
    store = GraphStore(pid)
    job = store.create_job()

    def _run() -> None:
        run_index_job(pid, incremental=incremental, job_id=job.id)

    background.add_task(_run)
    return job.model_dump(mode="json")


@app.get("/projects/{project_ref:path}/jobs/{job_id}")
def get_job(project_ref: str, job_id: str) -> dict:
    pid = _pid(project_ref)
    job = GraphStore(pid).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")


@app.get("/projects/{project_ref:path}/graph/neighborhood")
def graph_neighborhood(
    project_ref: str,
    node_id: str = Query(..., min_length=1),
    direction: str = Query("both"),
    depth: int = Query(1, ge=1, le=3),
) -> dict:
    d = direction.lower()
    if d not in {"in", "out", "both"}:
        raise HTTPException(status_code=422, detail="direction must be in, out, or both")
    store = GraphStore(_pid(project_ref))
    index = store.load_index()
    return neighborhood_subgraph(index, node_id, direction=d, depth=depth)


@app.get("/projects/{project_ref:path}/graph/{view}")
def get_graph(
    project_ref: str,
    view: str,
    focus_node_id: str | None = Query(default=None),
    expanded: str | None = Query(default=None, description="Comma-separated node ids expanded in explore view"),
) -> dict:
    if get_view(view) is None:
        raise HTTPException(status_code=404, detail=f"unknown view {view!r}")
    params: dict | None = None
    if expanded:
        params = {"expanded": expanded}
    payload = GraphStore(_pid(project_ref)).build_graph_view(view, focus_node_id=focus_node_id, params=params)
    return payload.model_dump(mode="json")


@app.get("/projects/{project_ref:path}/export")
def export_graph(project_ref: str) -> Response:
    """Download the complete knowledge graph (nodes + edges + layers) as JSON."""
    project = _require_project(project_ref)
    store = GraphStore(project.id)
    index = store.load_index()
    payload = {
        "version": 1,
        "project": project.model_dump(mode="json"),
        "layers": layer_catalog(),
        "nodes": [n.model_dump(mode="json", exclude={"project_id"}) for n in index.nodes.values()],
        "edges": [e.model_dump(mode="json", exclude={"project_id"}) for e in index.edges],
    }
    import json

    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{project.name}-graph.json"'},
    )


@app.get("/projects/{project_ref:path}/tour")
def tour(project_ref: str) -> dict:
    """Guided walkthrough: where a newcomer should read first."""
    index = GraphStore(_pid(project_ref)).load_index()
    steps = build_tour(index)
    for step in steps:
        step["nodes"] = [node_summary(index.nodes[nid]) for nid in step["node_ids"] if nid in index.nodes]
    return {"steps": steps}


@app.get("/projects/{project_ref:path}/search")
def search(
    project_ref: str,
    q: str = Query(..., min_length=1, max_length=200),
    types: str | None = Query(default=None, description="Comma-separated node types"),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    nodes = GraphStore(_pid(project_ref)).list_all_nodes()
    wanted = {t.strip() for t in types.split(",") if t.strip()} if types else None
    hits = search_nodes(nodes, q, types=wanted, limit=limit)
    return {
        "query": q,
        "results": [node_summary(n, score=score) for n, score in hits],
    }


@app.get("/projects/{project_ref:path}/path")
def shortest_path(
    project_ref: str,
    source: str = Query(..., description="Source node id"),
    target: str = Query(..., description="Target node id"),
    max_hops: int = Query(12, ge=1, le=30),
) -> dict:
    index = GraphStore(_pid(project_ref)).load_index()
    result = find_path(index, source, target, max_hops=max_hops)
    result["nodes"] = [
        node_summary(index.nodes[nid])
        for nid in result.get("node_ids", [])
        if nid in index.nodes
    ]
    return result


@app.post("/projects/{project_ref:path}/impact")
def impact(project_ref: str, body: ImpactBody) -> dict:
    project = _require_project(project_ref)
    pid = project.id
    index = GraphStore(pid).load_index()
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
        fresh = compute_freshness(pid, Path(project.root_path))
        files = list(fresh.get("changed_files", []))
        source = "working-tree"
    report = impact_for_request(index, files=files, node_ids=body.node_ids, depth=body.depth)
    report["source"] = source
    return report


@app.get("/projects/{project_ref:path}/nodes/{node_id}")
def get_node(project_ref: str, node_id: str) -> dict:
    index = GraphStore(_pid(project_ref)).load_index()
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
    return {
        "node": node.model_dump(mode="json"),
        "edges": [e.model_dump(mode="json") for e in edges],
        "neighbors": neighbours,
    }


@app.get("/projects/{project_ref:path}/source")
def get_source(
    project_ref: str,
    path: str = Query(...),
    start: int = Query(1, ge=1),
    end: int | None = None,
) -> dict:
    project = _require_project(project_ref)
    allowed = GraphStore(project.id).indexed_paths()
    candidate = resolve_source_path(Path(project.root_path), path, allowed)
    if candidate is None:
        raise HTTPException(status_code=404, detail="not an indexed source file")
    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    end_line = min(end or start + 80, len(lines), start + 400)
    return {
        "path": path,
        "start": start,
        "end": end_line,
        "total_lines": len(lines),
        "language": _language_for(path),
        "abs_path": str(candidate),
        "content": "\n".join(lines[start - 1 : end_line]),
    }


def _language_for(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {"py": "python", "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx", "mjs": "javascript", "cjs": "javascript"}.get(ext, ext or "text")


@app.post("/projects/{project_ref:path}/chat")
async def chat(project_ref: str, body: ChatBody, response: Response) -> EventSourceResponse:
    pid = _pid(project_ref)
    response.headers["X-CI-Mode"] = "graph-tools-rag"

    history = [{"role": m.role, "content": m.content} for m in body.conversation_history]

    async def event_generator():
        # events: message (markdown text), tool, citations, done, error — see ci_ai.agent
        async for event in chat_stream(
            pid,
            body.message,
            body.focus_node_id,
            conversation_history=history,
        ):
            yield event

    return EventSourceResponse(event_generator())


def create_app(ui_dir: Path | None = None) -> FastAPI:
    """The API app; with `ui_dir`, a combined app serving the dashboard at / and the API at /api."""
    if ui_dir is None:
        return app
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    root = FastAPI(title="Codebase Intelligence", version=app.version)
    root.mount("/api", app)
    ui_dir = ui_dir.resolve()
    if (ui_dir / "assets").is_dir():
        root.mount("/assets", StaticFiles(directory=ui_dir / "assets"), name="assets")

    @root.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (ui_dir / path).resolve()
        if path and candidate.is_file() and ui_dir in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(ui_dir / "index.html")  # client-side routes (deep links)

    return root
