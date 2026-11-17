"""Project lifecycle: list, add, index, rename, settings, saved views and removal."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from ci_ai import build_project_summary
from ci_api.deps import actor, pid, require_project
from ci_api.schemas import AnalyzeBody, CreateProjectBody, RenameBody, SavedViewBody, SettingsBody
from ci_core import audit
from ci_core.db import GraphStore
from ci_core.models import ProjectRecord
from ci_core.project_admin import (
    add_saved_view,
    delete_saved_view,
    list_saved_views,
    load_settings,
    project_overview,
    remove_project,
    removal_plan,
    rename_project,
    repo_ignore_file,
    save_settings,
)
from ci_core.projects import resolve_project
from ci_core.registry import load_registry
from ci_core.settings import get_settings
from ci_core.views import view_catalog
from ci_indexer import compute_freshness, create_project_from_git, create_project_from_path, index_in_progress, run_index_job
from ci_parsers import GitCloneError

router = APIRouter()


def _register(body: CreateProjectBody) -> ProjectRecord:
    """Create a project from a path or GitHub URL (server mode confines paths to CI_PROJECT_ROOTS)."""
    if body.path:
        path = Path(body.path)
        if not get_settings().path_allowed(path):
            raise HTTPException(status_code=403, detail="path is outside the allowed project roots (CI_PROJECT_ROOTS)")
        if not path.expanduser().is_dir():
            raise HTTPException(status_code=400, detail=f"not a directory: {body.path}")
        return create_project_from_path(path)
    if body.git_url:
        if get_settings().mode == "server":
            raise HTTPException(
                status_code=403,
                detail="git_url ingest is disabled in server mode; clone under CI_PROJECT_ROOTS and use path",
            )
        try:
            return create_project_from_git(body.git_url)
        except GitCloneError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail="path or git_url required")


@router.get("/projects")
def list_projects() -> list[dict]:
    return [p.model_dump(mode="json") for p in load_registry()]


@router.get("/projects/overview")
def projects_overview() -> list[dict]:
    """Every project with index stats, last-indexed time and whether git HEAD moved since (stale)."""
    out = []
    for p in load_registry():
        item = project_overview(p)
        item["indexing"] = index_in_progress(p.id)
        out.append(item)
    return out


@router.get("/projects/resolve")
def resolve(ref: str = Query(..., min_length=1, max_length=1024)) -> dict:
    """Resolve an id, name, or a path inside a repo to its registered project (same rules as the CLI and MCP)."""
    record = resolve_project(ref)
    if record is None:
        raise HTTPException(status_code=404, detail="no matching project")
    return record.model_dump(mode="json")


@router.post("/projects")
def create_project(body: CreateProjectBody, request: Request) -> dict:
    record = _register(body)
    audit.record("project.add", project_id=record.id, project_name=record.name, actor=actor(request),
                 detail={"source": "git" if body.git_url else "path"})
    return record.model_dump(mode="json")


@router.post("/projects/analyze")
def analyze_project(body: AnalyzeBody, request: Request) -> dict:
    """Ingest-style flow: register project, index synchronously, return summary."""
    record = _register(body)
    job = run_index_job(record.id)
    audit.record("project.analyze", project_id=record.id, project_name=record.name, actor=actor(request),
                 outcome=job.status.value, detail={"source": "git" if body.git_url else "path", "job_id": job.id})
    if job.status.value == "failed":
        raise HTTPException(status_code=500, detail=job.error or "Index failed")
    summary = build_project_summary(record.id)
    return {
        "project": record.model_dump(mode="json"),
        "job": job.model_dump(mode="json"),
        "summary": summary,
    }


@router.get("/projects/{project_ref:path}/removal-plan")
def project_removal_plan(project_ref: str) -> dict:
    """What DELETE would remove (index data, managed clone) and what it never touches (your source)."""
    project = require_project(project_ref)
    return {**removal_plan(project), "indexing": index_in_progress(project.id)}


@router.get("/projects/{project_ref:path}/settings")
def get_project_settings(project_ref: str) -> dict:
    project = require_project(project_ref)
    return {**load_settings(project.id), "repo_ciignore": repo_ignore_file(project)}


@router.put("/projects/{project_ref:path}/settings")
def put_project_settings(project_ref: str, body: SettingsBody, request: Request) -> dict:
    """Ignore patterns apply on the next index (they are stored here, not written into the repo)."""
    project = require_project(project_ref)
    saved = save_settings(project.id, ignore=body.ignore, auto_refresh=body.auto_refresh)
    audit.record("project.settings", project_id=project.id, project_name=project.name, actor=actor(request),
                 detail={"ignore_patterns": len(saved["ignore"]), "auto_refresh": saved["auto_refresh"]})
    return {**saved, "repo_ciignore": repo_ignore_file(project)}


@router.get("/projects/{project_ref:path}/saved-views")
def get_saved_views(project_ref: str) -> dict:
    items = list_saved_views(pid(project_ref))
    return {"count": len(items), "views": items}


@router.post("/projects/{project_ref:path}/saved-views")
def post_saved_view(project_ref: str, body: SavedViewBody) -> dict:
    try:
        return add_saved_view(pid(project_ref), body.name, body.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/projects/{project_ref:path}/saved-views/{view_id}")
def remove_saved_view(project_ref: str, view_id: str) -> dict:
    if not delete_saved_view(pid(project_ref), view_id[:64]):
        raise HTTPException(status_code=404, detail="saved view not found")
    return {"deleted": True}


@router.get("/projects/{project_ref:path}/views")
def project_views(project_ref: str) -> list[dict]:
    """Diagram modules with availability and counts for this project's graph."""
    return view_catalog(GraphStore(pid(project_ref)).load_index())


@router.get("/projects/{project_ref:path}/summary")
def project_summary(project_ref: str) -> dict:
    return build_project_summary(pid(project_ref))


@router.get("/projects/{project_ref:path}/freshness")
def freshness(project_ref: str) -> dict:
    """fresh | dirty | stale | unknown, with the files that differ from the index."""
    project = require_project(project_ref)
    return compute_freshness(project.id, Path(project.root_path))


@router.post("/projects/{project_ref:path}/index")
def index_project(project_ref: str, background: BackgroundTasks, request: Request, incremental: bool = False) -> dict:
    """Start an index job. `incremental=true` re-analyses only when files changed; default forces a rebuild."""
    project = require_project(project_ref)
    store = GraphStore(project.id)
    job = store.create_job()
    who = actor(request)

    def _run() -> None:
        done = run_index_job(project.id, incremental=incremental, job_id=job.id)
        audit.record("project.index", project_id=project.id, project_name=project.name, actor=who, outcome=done.status.value,
                     detail={"incremental": incremental, "job_id": job.id, "message": done.message, "error": done.error})

    background.add_task(_run)
    return job.model_dump(mode="json")


@router.get("/projects/{project_ref:path}/jobs/{job_id}")
def get_job(project_ref: str, job_id: str) -> dict:
    job = GraphStore(pid(project_ref)).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.model_dump(mode="json")


@router.get("/projects/{project_ref:path}/index-jobs")
def index_jobs(project_ref: str, limit: int = Query(20, ge=1, le=100)) -> dict:
    """Recent index jobs (newest first)."""
    jobs = GraphStore(pid(project_ref)).recent_jobs(limit=limit)
    return {"count": len(jobs), "jobs": [j.model_dump(mode="json") for j in jobs]}


@router.get("/projects/{project_ref:path}/docs")
def generated_docs(project_ref: str) -> dict:
    """Markdown + Mermaid docs (what `ci docs` writes), returned instead of written to disk."""
    from ci_core.docgen import render_docs

    project = require_project(project_ref)
    return {"files": render_docs(GraphStore(project.id).load_index(), project.name)}


# Declared last: `{project_ref:path}` is greedy, so these must not shadow the
# `/projects/{ref}/…` routes above (e.g. DELETE …/saved-views/{id}).
@router.delete("/projects/{project_ref:path}")
def delete_project(project_ref: str, request: Request) -> dict:
    """Remove a project from this tool. Deletes its index (and the clone this tool made for a git
    URL); a local source folder is never modified. Refused while an index job is running."""
    project = require_project(project_ref)
    if index_in_progress(project.id) or GraphStore(project.id).has_running_job():
        raise HTTPException(status_code=409, detail="an index job is running for this project; try again when it finishes")
    plan = remove_project(project)
    audit.record("project.delete", project_id=project.id, project_name=project.name, actor=actor(request),
                 detail={"deleted": plan["delete"], "source_untouched": plan["source_untouched"]})
    return {"deleted": True, **plan}


@router.patch("/projects/{project_ref:path}")
def patch_project(project_ref: str, body: RenameBody, request: Request) -> dict:
    """Rename a project (display name; also usable as a CLI/MCP reference). Names must be unique."""
    project = require_project(project_ref)
    name = " ".join(body.name.split())
    if any(p.name == name and p.id != project.id for p in load_registry()):
        raise HTTPException(status_code=409, detail=f"another project is already named {name!r}")
    updated = rename_project(project, name)
    audit.record("project.rename", project_id=project.id, project_name=updated.name, actor=actor(request),
                 detail={"from": project.name, "to": updated.name})
    return updated.model_dump(mode="json")
