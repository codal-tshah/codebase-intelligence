"""Opt-in background refresh: re-index a project when its git HEAD moves (pull, commit, checkout).

Enabled per project with ``PUT /projects/{ref}/settings {"auto_refresh": true}`` (or the switch in
the dashboard's project settings). The check is cheap (``git rev-parse HEAD`` against the commit
recorded at the last index), runs every ``CI_AUTO_REFRESH_SECONDS`` (default 60, 0 disables), and
runs an incremental index, so unchanged files are not re-analysed. Uncommitted edits do not
trigger it; use "Re-index" (or the git hooks from ``ci hook install``) for those.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ci_core import audit
from ci_core.fingerprints import load_fingerprints
from ci_core.project_admin import git_head, load_settings
from ci_core.registry import load_registry
from ci_indexer import index_in_progress, run_index_job

log = logging.getLogger("ci_api.autorefresh")


def interval_seconds() -> int:
    try:
        return max(0, int(os.environ.get("CI_AUTO_REFRESH_SECONDS", "60")))
    except ValueError:
        return 60


def due_projects() -> list[tuple[str, str, str]]:
    """(project id, name, new head) for opted-in projects whose HEAD differs from the indexed commit."""
    out = []
    for p in load_registry():
        if not load_settings(p.id)["auto_refresh"]:
            continue
        root = Path(p.root_path)
        if not root.exists():
            continue
        head = git_head(root)
        indexed = (load_fingerprints(p.id) or {}).get("commit_sha")
        if head and indexed and head != indexed and not index_in_progress(p.id):
            out.append((p.id, p.name, head))
    return out


def refresh_once() -> int:
    n = 0
    for project_id, name, head in due_projects():
        job = run_index_job(project_id, incremental=True)
        audit.record("project.auto_refresh", project_id=project_id, project_name=name, actor="auto-refresh",
                     outcome=job.status.value, detail={"head": head[:12], "message": job.message, "error": job.error})
        n += 1
    return n


async def run_forever() -> None:
    every = interval_seconds()
    if not every:
        return
    while True:
        await asyncio.sleep(every)
        try:
            await asyncio.to_thread(refresh_once)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("auto-refresh failed")
