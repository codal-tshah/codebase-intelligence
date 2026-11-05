"""Persisted per-file fingerprints (content hash + structural hash) for an indexed project."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from ci_core.config import project_dir


def fingerprints_path(project_id: str) -> Path:
    return project_dir(project_id) / "fingerprints.json"


def load_fingerprints(project_id: str) -> dict[str, Any] | None:
    path = fingerprints_path(project_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_fingerprints(
    project_id: str, files: dict[str, dict[str, Any]], *, adapter_version: str, commit_sha: str | None
) -> None:
    payload = {
        "adapter_version": adapter_version,
        "commit_sha": commit_sha,
        "indexed_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    fingerprints_path(project_id).write_text(json.dumps(payload), encoding="utf-8")
