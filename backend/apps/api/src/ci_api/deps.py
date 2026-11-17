"""Shared request helpers for the API routers: project resolution, input bounds, audit actor."""

from __future__ import annotations

import re

from fastapi import HTTPException, Request

from ci_core.models import ProjectRecord
from ci_core.projects import resolve_project
from ci_core.settings import get_settings

# Bounds for graph/source query params: node ids are short hashes or dotted names, and the
# dashboard never expands more than a few hundred groups. Anything larger is a mistake or abuse.
MAX_ID = 512
MAX_EXPANDED = 500
MAX_OFFSETS = 200

GITHUB_URL = re.compile(r"^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?(\.git)?$", re.I)


def check_expanded(expanded: str | None, offsets: list[str] | None) -> None:
    if expanded and expanded.count(",") + 1 > MAX_EXPANDED:
        raise HTTPException(status_code=422, detail=f"expanded: at most {MAX_EXPANDED} node ids")
    if offsets and len(offsets) > MAX_OFFSETS:
        raise HTTPException(status_code=422, detail=f"extra_child_offsets: at most {MAX_OFFSETS} entries")


def require_project(project_ref: str) -> ProjectRecord:
    project = resolve_project(project_ref)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def pid(ref: str) -> str:
    return require_project(ref).id


def actor(request: Request) -> str:
    """Who performed a mutating action, for the audit log (never the key itself)."""
    who = "api-key" if get_settings().mode == "server" else "local"
    host = request.client.host if request.client else None
    return f"{who}@{host}" if host else who
