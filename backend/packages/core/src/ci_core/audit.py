"""Append-only audit log of mutating actions (add, index, rename, settings, delete).

One JSON object per line in ``<data dir>/audit.jsonl``. Entries record what happened to which
project and when; they never contain source code, file contents or secrets.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from ci_core.config import get_data_dir

_LOCK = threading.Lock()
MAX_READ = 1000


def _path():
    return get_data_dir() / "audit.jsonl"


def record(action: str, *, project_id: str | None = None, project_name: str | None = None, actor: str | None = None,
           detail: dict[str, Any] | None = None, outcome: str = "ok") -> dict[str, Any]:
    """Append one entry. Failures to write never break the action being audited."""
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "action": action,
        "project_id": project_id,
        "project_name": project_name,
        "actor": actor or "local",
        "outcome": outcome,
        "detail": detail or {},
    }
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass
    return entry


def read(limit: int = 200, project_id: str | None = None, action: str | None = None) -> list[dict[str, Any]]:
    """Newest first."""
    path = _path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in reversed(lines):
        if len(out) >= min(limit, MAX_READ):
            break
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if project_id and item.get("project_id") != project_id:
            continue
        if action and item.get("action") != action:
            continue
        out.append(item)
    return out
