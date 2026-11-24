"""Discover npm/pnpm/Yarn workspace package roots under a repository root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_resolve(root: Path, rel: str) -> Path | None:
    """Resolve `rel` under `root`; return None if the result escapes `root`."""
    rel = rel.strip().strip("/")
    if not rel or rel.startswith(".."):
        return None
    target = (root / rel).resolve()
    root_res = root.resolve()
    try:
        target.relative_to(root_res)
    except ValueError:
        return None
    return target


def _expand_patterns(root: Path, patterns: list[str]) -> list[str]:
    """Expand workspace globs to package directory paths relative to `root`."""
    out: list[str] = []
    seen: set[str] = set()
    for pat in patterns:
        if not pat or not isinstance(pat, str):
            continue
        neg = pat.startswith("!")
        clean = pat.lstrip("!")
        if not clean:
            continue
        if "*" in clean or "?" in clean or "[" in clean:
            glob = clean if clean.startswith("**/") else f"**/{clean}"
            for hit in root.glob(glob):
                if not hit.is_dir():
                    continue
                try:
                    rel = hit.relative_to(root).as_posix()
                except ValueError:
                    continue
                if neg:
                    seen.discard(rel)
                    continue
                if rel not in seen and (hit / "package.json").is_file():
                    seen.add(rel)
                    out.append(rel)
        else:
            rel = clean.rstrip("/")
            if neg:
                seen.discard(rel)
                continue
            if _safe_resolve(root, rel) is None and not neg:
                continue
            resolved = _safe_resolve(root, rel)
            if resolved is not None and (root / rel / "package.json").is_file() and rel not in seen:
                seen.add(rel)
                out.append(rel)
    return sorted(seen) if seen else sorted(dict.fromkeys(out))


def _workspace_patterns_from_package(data: dict[str, Any]) -> list[str]:
    ws = data.get("workspaces")
    if isinstance(ws, list):
        return [str(x) for x in ws]
    if isinstance(ws, dict):
        pkgs = ws.get("packages")
        if isinstance(pkgs, list):
            return [str(x) for x in pkgs]
    return []


def _pnpm_patterns(root: Path) -> list[str]:
    path = root / "pnpm-workspace.yaml"
    if not path.is_file():
        return []
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    pkgs = data.get("packages")
    if isinstance(pkgs, list):
        return [str(x) for x in pkgs]
    return []


def discover_workspace_package_dirs(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Return ``{rel_dir: package.json dict}`` for declared workspace packages and warning strings."""
    root = root.resolve()
    warnings: list[str] = []
    patterns: list[str] = []
    root_pj = root / "package.json"
    if root_pj.is_file():
        try:
            data = json.loads(root_pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            patterns.extend(_workspace_patterns_from_package(data))
    patterns.extend(_pnpm_patterns(root))
    patterns = list(dict.fromkeys(patterns))
    if not patterns:
        return {}, warnings

    dirs = _expand_patterns(root, patterns)
    packages: dict[str, dict[str, Any]] = {}
    for rel in dirs:
        pj = root / rel / "package.json"
        if not pj.is_file():
            warnings.append(f"workspace pattern matched missing package.json: {rel}")
            continue
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"{rel}/package.json: {exc}")
            continue
        packages[rel] = data if isinstance(data, dict) else {}
    for pat in patterns:
        if "*" not in pat and "?" not in pat and not pat.startswith("!"):
            rel = pat.rstrip("/")
            if rel and rel not in packages:
                resolved = _safe_resolve(root, rel)
                if resolved is None:
                    warnings.append(f"workspace member outside repository root: {rel}")
                elif not (root / rel / "package.json").is_file():
                    warnings.append(f"workspace member not found: {rel}")
    return packages, warnings


def workspace_name_map(package_dirs: dict[str, dict[str, Any]]) -> dict[str, str]:
    """npm package name -> relative directory."""
    out: dict[str, str] = {}
    for rel, data in package_dirs.items():
        name = data.get("name")
        if isinstance(name, str) and name:
            if name in out and out[name] != rel:
                # keep first; collision is rare
                continue
            out[name] = rel
    return out
