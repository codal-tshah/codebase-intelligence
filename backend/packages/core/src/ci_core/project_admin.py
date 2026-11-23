"""Project lifecycle and per-project state kept in this tool's data directory.

Nothing here writes to a project's source folder. Removing a project deletes only:
  * ``<data dir>/projects/<id>/``   (index database, fingerprints, settings, saved views)
  * ``<data dir>/sources/<clone>/`` when the project is a managed clone created by this tool
and the registry entry. A local folder that was indexed in place is never touched.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ci_core.config import get_data_dir
from ci_core.models import ProjectRecord
from ci_core.registry import load_registry, register_project, save_registry

MAX_IGNORE_PATTERNS = 200
MAX_SAVED_VIEWS = 100


def _project_data_dir(project_id: str) -> Path:
    return get_data_dir() / "projects" / project_id


def managed_clone_dir(project: ProjectRecord) -> Path | None:
    """The clone folder if this tool created it (under ``<data dir>/sources``), else None."""
    sources = (get_data_dir() / "sources").resolve()
    try:
        root = Path(project.root_path).resolve()
    except OSError:
        return None
    return root if sources in root.parents else None


def removal_plan(project: ProjectRecord) -> dict[str, Any]:
    """Exactly what `remove_project` would delete (shown in the confirm dialog and by the CLI)."""
    data = _project_data_dir(project.id)
    clone = managed_clone_dir(project)
    return {
        "project": {"id": project.id, "name": project.name, "root_path": project.root_path},
        "delete": [str(p) for p in (data, clone) if p is not None],
        "index_data": str(data),
        "managed_clone": str(clone) if clone else None,
        "source_untouched": None if clone else project.root_path,
    }


def remove_project(project: ProjectRecord) -> dict[str, Any]:
    """Unregister the project and delete its index (and managed clone). Returns the plan executed."""
    from ci_core import db

    plan = removal_plan(project)
    save_registry([p for p in load_registry() if p.id != project.id])
    # drop in-process caches/engines before deleting the database file
    data = _project_data_dir(project.id)
    key = str(data / "index.db")
    db._INDEX_CACHE.pop(key, None)
    factory = db._ENGINES.pop(key, None)
    if factory is not None:
        try:
            factory.kw["bind"].dispose()
        except Exception:  # noqa: BLE001 - best effort
            pass
    data_root = (get_data_dir() / "projects").resolve()
    if data.exists() and data.resolve().parent == data_root:
        shutil.rmtree(data, ignore_errors=True)
    clone = managed_clone_dir(project)
    if clone and clone.exists():
        shutil.rmtree(clone, ignore_errors=True)
    try:
        from ci_ai.summarize import _SUMMARY_CACHE

        _SUMMARY_CACHE.pop(project.id, None)
    except Exception:  # noqa: BLE001 - optional package
        pass
    return plan


def rename_project(project: ProjectRecord, name: str) -> ProjectRecord:
    from ci_core.db import GraphStore

    name = " ".join(name.split())[:120]
    if not name:
        raise ValueError("name must not be empty")
    updated = project.model_copy(update={"name": name, "updated_at": datetime.now(UTC).replace(tzinfo=None)})
    GraphStore(project.id).upsert_project(updated)
    register_project(updated)
    return updated


# ------------------------------------------------------------------------- settings


def _settings_path(project_id: str) -> Path:
    return _project_data_dir(project_id) / "settings.json"


def load_settings(project_id: str) -> dict[str, Any]:
    path = _settings_path(project_id)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    return {"ignore": [str(p) for p in data.get("ignore", [])], "auto_refresh": bool(data.get("auto_refresh", False))}


def save_settings(project_id: str, *, ignore: list[str] | None = None, auto_refresh: bool | None = None) -> dict[str, Any]:
    current = load_settings(project_id)
    if ignore is not None:
        clean = []
        for raw in ignore[:MAX_IGNORE_PATTERNS]:
            line = str(raw).strip()
            if line and not line.startswith("#") and len(line) <= 300 and "\x00" not in line:
                clean.append(line)
        current["ignore"] = list(dict.fromkeys(clean))
    if auto_refresh is not None:
        current["auto_refresh"] = bool(auto_refresh)
    path = _settings_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def repo_ignore_file(project: ProjectRecord) -> str | None:
    """The repository's own `.ciignore` (read-only here), if it has one."""
    path = Path(project.root_path) / ".ciignore"
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:20000] if path.is_file() else None
    except OSError:
        return None


# ------------------------------------------------------------------------- saved views


def _views_path(project_id: str) -> Path:
    return _project_data_dir(project_id) / "saved_views.json"


def list_saved_views(project_id: str) -> list[dict[str, Any]]:
    path = _views_path(project_id)
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [v for v in items if isinstance(v, dict)]


def add_saved_view(project_id: str, name: str, state: dict[str, Any]) -> dict[str, Any]:
    items = list_saved_views(project_id)
    if len(items) >= MAX_SAVED_VIEWS:
        raise ValueError(f"at most {MAX_SAVED_VIEWS} saved views per project")
    allowed = {"v", "n", "f", "e"}  # view, selected node, focus node, expanded ids (same keys as the URL hash)
    view = {
        "id": uuid.uuid4().hex[:12],
        "name": " ".join(name.split())[:120] or "Untitled view",
        "state": {k: str(v)[:20000] for k, v in state.items() if k in allowed and v},
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    items.append(view)
    path = _views_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return view


def delete_saved_view(project_id: str, view_id: str) -> bool:
    items = list_saved_views(project_id)
    keep = [v for v in items if v.get("id") != view_id]
    if len(keep) == len(items):
        return False
    _views_path(project_id).write_text(json.dumps(keep, indent=2), encoding="utf-8")
    return True


# ------------------------------------------------------------------------- overview


def git_head(root: Path) -> str | None:
    try:
        res = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def project_overview(project: ProjectRecord) -> dict[str, Any]:
    """Cheap per-project status for the project list (no file walk): stats from the last index,
    and whether git HEAD moved since (``stale``)."""
    from ci_core.fingerprints import load_fingerprints

    meta_path = _project_data_dir(project.id) / "meta.json"
    stats: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stats = dict(meta.get("stats") or {})
        except (OSError, json.JSONDecodeError):
            stats = {}
    fp = load_fingerprints(project.id) or {}
    root = Path(project.root_path)
    exists = root.exists()
    head = git_head(root) if exists else None
    indexed_commit = fp.get("commit_sha")
    return {
        **project.model_dump(mode="json"),
        "indexed_at": fp.get("indexed_at"),
        "indexed_commit": indexed_commit,
        "head_commit": head,
        "stale": bool(head and indexed_commit and head != indexed_commit),
        "source_missing": not exists,
        "files": len(fp.get("files", {})) or stats.get("files"),
        "stats": stats,
        "managed_clone": managed_clone_dir(project) is not None,
    }
