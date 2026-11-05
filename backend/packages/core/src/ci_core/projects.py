"""Resolve a user-supplied project reference (id, name, or a path inside the repo)."""

from __future__ import annotations

from pathlib import Path

from ci_core.models import ProjectRecord
from ci_core.registry import load_registry


def resolve_project(ref: str | None) -> ProjectRecord | None:
    """Registered project for `ref`, or None. Never indexes anything.

    Order: exact id, exact name, then the project whose root contains the path (deepest root wins).
    """
    ref = (ref or "").strip()
    if not ref:
        return None
    projects = load_registry()
    for p in projects:
        if ref in (p.id, p.name):
            return p
    path = Path(ref).expanduser()
    if not path.exists():
        return None
    path = path.resolve()
    owners = [p for p in projects if path == Path(p.root_path) or Path(p.root_path) in path.parents]
    return max(owners, key=lambda p: len(p.root_path), default=None)
