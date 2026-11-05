"""File discovery, ignore rules, and git helpers."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from pathlib import Path

DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "site-packages",
        "staticfiles",
        ".idea",
        ".vscode",
    }
)

MAX_FILE_BYTES = 1_000_000
IGNORE_FILENAMES = (".ciignore",)


def load_ignore_patterns(root: Path) -> list[str]:
    """Read gitignore-style patterns from `.ciignore` (one per line, `#` comments)."""
    patterns: list[str] = []
    for name in IGNORE_FILENAMES:
        path = root / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return patterns


def is_ignored(rel_posix: str, is_dir: bool, patterns: list[str]) -> bool:
    name = rel_posix.rsplit("/", 1)[-1]
    for pat in patterns:
        dir_only = pat.endswith("/")
        clean = pat.rstrip("/").lstrip("/")
        if not clean:
            continue
        if dir_only and not is_dir:
            # a directory pattern also ignores everything beneath it
            if any(fnmatch.fnmatch(part, clean) for part in rel_posix.split("/")[:-1]):
                return True
            continue
        if fnmatch.fnmatch(name, clean) or fnmatch.fnmatch(rel_posix, clean):
            return True
        if fnmatch.fnmatch(rel_posix, clean + "/*"):
            return True
    return False


SKIP_FILE_SUFFIXES = (".min.js", ".bundle.js", ".d.ts", ".map")


def list_python_files(root: Path, *, extra_ignore: list[str] | None = None) -> list[Path]:
    """Every analysable `.py` file under `root` (see :func:`list_source_files`)."""
    return list_source_files(root, (".py",), extra_ignore=extra_ignore)


def list_source_files(
    root: Path, extensions: tuple[str, ...] | frozenset[str], *, extra_ignore: list[str] | None = None
) -> list[Path]:
    """Walk `root` once, pruning vendored/build dirs, honouring `.ciignore`, skipping huge
    and generated files, and return files whose suffix is in `extensions`."""
    wanted = {e.lower() for e in extensions}
    patterns = [*load_ignore_patterns(root), *(extra_ignore or [])]
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        rel_dir = base.relative_to(root).as_posix()
        kept: list[str] = []
        for d in dirnames:
            if d in DEFAULT_SKIP_DIRS or d.endswith(".egg-info"):
                continue
            rel = d if rel_dir == "." else f"{rel_dir}/{d}"
            if is_ignored(rel, True, patterns):
                continue
            kept.append(d)
        dirnames[:] = sorted(kept)
        for fname in filenames:
            lower = fname.lower()
            dot = lower.rfind(".")
            if dot < 0 or lower[dot:] not in wanted or lower.endswith(SKIP_FILE_SUFFIXES):
                continue
            rel = fname if rel_dir == "." else f"{rel_dir}/{fname}"
            if is_ignored(rel, False, patterns):
                continue
            path = base / fname
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            files.append(path)
    return sorted(files)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def clone_git_repo(git_url: str, dest: Path) -> str | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and any(dest.iterdir()):
        result = _git(dest, "rev-parse", "HEAD")
        if result.returncode == 0:
            _git(dest, "pull", "--ff-only")
            return git_head_sha(dest)
    subprocess.run(["git", "clone", "--depth", "1", git_url, str(dest)], check=True)
    return git_head_sha(dest)


def git_head_sha(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    result = _git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else None


def git_dirty_files(root: Path) -> list[str] | None:
    """Paths with uncommitted changes (staged, unstaged, untracked). None if not a git repo."""
    if not (root / ".git").exists():
        return None
    result = _git(root, "status", "--porcelain", "--untracked-files=all")
    if result.returncode != 0:
        return None
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        paths.append(entry.strip().strip('"'))
    return paths


def git_changed_between(root: Path, base_sha: str, head: str = "HEAD") -> list[str] | None:
    if not (root / ".git").exists():
        return None
    result = _git(root, "diff", "--name-only", f"{base_sha}..{head}")
    if result.returncode != 0:
        return None
    return [p for p in result.stdout.splitlines() if p.strip()]
