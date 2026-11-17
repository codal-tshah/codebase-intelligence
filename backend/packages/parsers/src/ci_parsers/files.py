"""File discovery, ignore rules, and git helpers."""

from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import base64
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
        # generated output (coverage reports, framework build caches): never source
        "htmlcov",
        "coverage",
        ".nyc_output",
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".turbo",
        ".parcel-cache",
        ".cache",
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


class GitCloneError(RuntimeError):
    """Clone or pull failed (message is safe to show: it never contains the token)."""


def _git_auth_env(token: str | None) -> dict[str, str]:
    """Env that sends a GitHub token as an HTTP header for this one git process.

    The token is passed via GIT_CONFIG_* env vars, so it is not in argv, the remote URL,
    or ``.git/config`` of the clone. GIT_TERMINAL_PROMPT=0 makes auth failures fail fast.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(
            GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
            GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}",
        )
    return env


_GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", re.I)


def parse_github_url(git_url: str) -> tuple[str, str] | None:
    """(owner, repo) for a github.com repository URL, else None."""
    m = _GITHUB_REPO.match(git_url.strip())
    return (m.group(1), m.group(2)) if m else None


def normalize_github_url(git_url: str) -> str:
    """Canonical ``https://github.com/owner/repo`` (the form the token header is scoped to)."""
    parsed = parse_github_url(git_url)
    return f"https://github.com/{parsed[0]}/{parsed[1]}" if parsed else git_url.strip()


def _auth_failed(stderr: str) -> bool:
    err = stderr.lower()
    return any(s in err for s in ("not found", "authentication", "could not read username", "403", "401"))


def check_git_access(git_url: str, *, token: str | None = None, timeout: float = 20.0) -> dict[str, object]:
    """Cheap reachability check (``git ls-remote``) before cloning.

    Returns ``{"ok": True, "default_branch": ...}`` or ``{"ok": False, "reason": ..., "needs_token": bool}``.
    A rejected token falls back to anonymous access (public repos keep working with a stale token).
    Never includes the token.
    """
    git_url = normalize_github_url(git_url)
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--symref", git_url, "HEAD"],
            capture_output=True, text=True, env=_git_auth_env(token), timeout=timeout, check=False,
        )
        if result.returncode != 0 and token and _auth_failed(result.stderr or ""):
            anonymous = check_git_access(git_url, token=None, timeout=timeout)
            if anonymous["ok"]:
                return {**anonymous, "warning": "CI_GITHUB_TOKEN was rejected; the repository is public"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "timed out reaching the repository", "needs_token": False}
    if result.returncode == 0:
        branch = None
        for line in result.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                branch = line.split("\t", 1)[0].removeprefix("ref: refs/heads/")
        return {"ok": True, "default_branch": branch, "authenticated": bool(token)}
    if _auth_failed(result.stderr or ""):
        reason = (
            "repository not found or the token can't read it"
            if token
            else "repository not found or private: set CI_GITHUB_TOKEN on the server"
        )
        return {"ok": False, "reason": reason, "needs_token": not token}
    last = (result.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
    return {"ok": False, "reason": last[0], "needs_token": False}


def clone_git_repo(git_url: str, dest: Path, *, token: str | None = None) -> str | None:
    """Shallow-clone (or fast-forward an existing clone of) a GitHub repo.

    ``token`` (CI_GITHUB_TOKEN / GITHUB_TOKEN) enables private repositories.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = _git_auth_env(token)
    if dest.exists() and any(dest.iterdir()):
        result = _git(dest, "rev-parse", "HEAD")
        if result.returncode == 0:
            subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"], capture_output=True, env=env, check=False)
            return git_head_sha(dest)
    git_url = normalize_github_url(git_url)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", git_url, str(dest)], capture_output=True, text=True, env=env, check=False
    )
    if result.returncode != 0 and token and _auth_failed(result.stderr or ""):
        # stale/over-scoped token: a public repo should still clone anonymously
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(dest)],
            capture_output=True, text=True, env=_git_auth_env(None), check=False,
        )
    if result.returncode != 0:
        detail = (result.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        hint = "" if token else " If the repository is private, set CI_GITHUB_TOKEN (see docs/private-repos.md)."
        raise GitCloneError(f"git clone failed: {detail[0]}.{hint}")
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
    # `base` comes from API/MCP callers: a leading "-" would be parsed as a git option
    # (e.g. --output=<file> writes anywhere), so only accept refs.
    if base_sha.startswith("-") or head.startswith("-"):
        return None
    result = _git(root, "diff", "--name-only", f"{base_sha}..{head}")
    if result.returncode != 0:
        return None
    return [p for p in result.stdout.splitlines() if p.strip()]
