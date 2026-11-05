"""Safe, allowlisted access to project source files."""

from __future__ import annotations

from pathlib import Path


def resolve_source_path(root: Path, rel: str, allowed: set[str]) -> Path | None:
    """Return the absolute path for `rel` only if it is inside `root` and was indexed.

    Allowlisting by index (rather than "anything under root") keeps `.env` files,
    keys, and other unindexed material unreachable through the API or the AI tools.
    """
    rel = rel.replace("\\", "/").lstrip("/")
    if rel not in allowed:
        return None
    root = root.resolve()
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
