"""Health, status page data, catalogs, git preflight and the audit log."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ci_api.deps import GITHUB_URL
from ci_core import audit
from ci_core.db import GraphStore
from ci_core.layers import layer_catalog
from ci_core.registry import load_registry
from ci_core.settings import get_settings
from ci_core.views import view_catalog
from ci_indexer import analyzer_catalog
from ci_parsers import check_git_access

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict:
    """Operational status for the dashboard's status page: mode, analyzers, projects and jobs."""
    from ci_api import __version__

    settings = get_settings()
    projects = load_registry()
    running = []
    for p in projects:
        try:
            for j in GraphStore(p.id).recent_jobs(limit=3):
                if j.status.value in ("pending", "running"):
                    running.append({"project_id": p.id, "project_name": p.name, **j.model_dump(mode="json")})
        except Exception:
            pass  # stale registry row or missing store; skip this project
    out = {
        "status": "ok",
        "version": __version__,
        "mode": settings.mode,
        "auth_required": settings.mode == "server",
        "llm_enabled": settings.llm_enabled,
        "github_token_configured": bool(settings.github_token),
        "project_count": len(projects),
        "active_jobs": running,
        "analyzers": analyzer_catalog(),
    }
    if settings.mode != "server":  # don't reveal the server's filesystem layout to API clients
        out["data_dir"] = str(settings.data_dir)
    else:
        out["project_roots_configured"] = len(settings.project_roots)
    return out


@router.get("/layers")
def layers() -> list[dict]:
    """The framework-neutral architectural layer taxonomy (id, name, description, colour)."""
    return layer_catalog()


@router.get("/analyzers")
def analyzers() -> list[dict]:
    """Installed language/framework analyzers (built-ins plus entry-point plugins)."""
    return analyzer_catalog()


@router.get("/views")
def views() -> list[dict]:
    """Registered diagram modules (without project-specific availability)."""
    return view_catalog()


@router.get("/git/check")
def git_check(url: str = Query(..., min_length=1, max_length=512)) -> dict:
    """Preflight for the ingest form: can this server read the GitHub repo (with CI_GITHUB_TOKEN if set)?"""
    if not GITHUB_URL.match(url.strip()):
        raise HTTPException(
            status_code=422, detail="Must be a valid GitHub repository URL (https://github.com/owner/repo)"
        )
    if get_settings().mode == "server":
        raise HTTPException(status_code=403, detail="git_url ingest is disabled in server mode")
    settings = get_settings()
    return {
        **check_git_access(url.strip(), token=settings.github_token),
        "token_configured": bool(settings.github_token),
    }


@router.get("/audit")
def audit_log(
    limit: int = Query(200, ge=1, le=1000),
    project_id: str | None = Query(default=None, max_length=128),
    action: str | None = Query(default=None, max_length=64),
) -> dict:
    """Mutating actions (add, index, rename, settings, delete), newest first."""
    items = audit.read(limit=limit, project_id=project_id, action=action)
    return {"count": len(items), "entries": items}
