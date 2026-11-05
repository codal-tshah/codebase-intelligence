"""Fingerprint persistence, change classification, and graph freshness.

Two hashes are kept per file:
  sha         content hash (any byte change)
  structural  shape hash (symbols, signatures, imports, call targets, module-level values)

NONE      sha unchanged
COSMETIC  sha changed, structural unchanged (comments, docstrings, formatting, body tweaks)
STRUCTURAL  structural changed, or the file was added/removed

Aggregate decision (how much to rebuild):
  SKIP          nothing changed
  PARTIAL       only a few non-architectural files changed
  ARCHITECTURE  added/removed files or structural edits to settings/urls/models/middleware
  FULL          no baseline, adapter version changed, or most files changed
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ci_core.fingerprints import load_fingerprints
from ci_parsers import file_sha256, git_dirty_files, git_head_sha

ARCHITECTURE_ROLES = {"settings", "urls", "models", "middleware", "apps", "manage", "wsgi", "asgi"}
FULL_REBUILD_RATIO = 0.5


@dataclass
class ChangeSet:
    level: str  # SKIP | PARTIAL | ARCHITECTURE | FULL
    reason: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    structural: list[str] = field(default_factory=list)
    cosmetic: list[str] = field(default_factory=list)

    @property
    def modified(self) -> list[str]:
        return [*self.structural, *self.cosmetic]

    @property
    def touched(self) -> set[str]:
        return {*self.added, *self.removed, *self.structural, *self.cosmetic}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["touched_count"] = len(self.touched)
        return data


def classify_changes(
    previous: dict[str, Any] | None,
    current: dict[str, dict[str, Any]],
    *,
    adapter_version: str,
    force: bool = False,
    graph_is_empty: bool = False,
) -> ChangeSet:
    if force:
        return ChangeSet("FULL", "full re-index requested", added=sorted(current))
    if previous is None or graph_is_empty:
        return ChangeSet("FULL", "no previous index", added=sorted(current))
    if previous.get("adapter_version") != adapter_version:
        return ChangeSet("FULL", "analysis version changed", added=sorted(current))

    old: dict[str, dict[str, Any]] = previous.get("files", {})
    added = sorted(set(current) - set(old))
    removed = sorted(set(old) - set(current))
    structural: list[str] = []
    cosmetic: list[str] = []
    for rel in sorted(set(current) & set(old)):
        if current[rel]["sha"] == old[rel]["sha"]:
            continue
        if current[rel]["structural"] != old[rel]["structural"]:
            structural.append(rel)
        else:
            cosmetic.append(rel)

    changes = ChangeSet("SKIP", "no changes", added, removed, structural, cosmetic)
    if not changes.touched:
        return changes

    total = max(len(current), 1)
    if len(changes.touched) / total > FULL_REBUILD_RATIO and len(changes.touched) > 5:
        changes.level, changes.reason = "FULL", f"{len(changes.touched)} of {total} files changed"
        return changes

    arch_files = [
        rel
        for rel in [*added, *removed, *structural]
        if (current.get(rel) or old.get(rel) or {}).get("role") in ARCHITECTURE_ROLES
    ]
    if added or removed or arch_files:
        changes.level = "ARCHITECTURE"
        what = "files added/removed" if (added or removed) else "architectural files changed structurally"
        changes.reason = f"{what} ({len(changes.touched)} touched)"
    else:
        changes.level = "PARTIAL"
        changes.reason = f"{len(changes.touched)} file(s) changed"
    return changes


# --------------------------------------------------------------------- freshness


def compute_freshness(project_id: str, root: Path) -> dict[str, Any]:
    """Compare the on-disk project to the stored index.

    fresh    index matches the working tree
    dirty    same commit as indexed, but uncommitted edits differ from the index
    stale    the project moved on (new commits / files) since indexing
    unknown  never indexed
    """
    previous = load_fingerprints(project_id)
    if previous is None:
        return {"status": "unknown", "message": "Project has not been indexed yet.", "changed_files": []}
    if not root.exists():
        return {"status": "unknown", "message": f"Project path no longer exists: {root}", "changed_files": []}

    old: dict[str, dict[str, Any]] = previous.get("files", {})
    current: dict[str, str] = {}
    from ci_indexer.analyzers import list_project_files

    for f in list_project_files(root):
        current[f.relative_to(root).as_posix()] = file_sha256(f)

    changed = sorted(
        {rel for rel in current if rel not in old or old[rel]["sha"] != current[rel]}
        | {rel for rel in old if rel not in current}
    )
    head = git_head_sha(root)
    indexed_commit = previous.get("commit_sha")
    base: dict[str, Any] = {
        "indexed_at": previous.get("indexed_at"),
        "indexed_commit": indexed_commit,
        "head_commit": head,
        "files_indexed": len(old),
        "changed_files": changed[:200],
        "changed_count": len(changed),
    }
    if not changed and head == indexed_commit:
        return {**base, "status": "fresh", "message": "Index matches the current code."}
    if not changed:
        return {**base, "status": "fresh", "message": "Index matches the current code (commit moved without source changes)."}

    uncommitted = git_dirty_files(root)
    if head and head == indexed_commit and uncommitted is not None:
        return {
            **base,
            "status": "dirty",
            "message": f"{len(changed)} file(s) have uncommitted changes since indexing.",
        }
    return {
        **base,
        "status": "stale",
        "message": f"{len(changed)} file(s) changed since the last index"
        + (" (new commits)." if head and head != indexed_commit else "."),
    }
