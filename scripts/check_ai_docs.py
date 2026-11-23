#!/usr/bin/env python3
"""Validate AI agent documentation: path references, .mdc frontmatter, line budgets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = [
    ROOT / "CLAUDE.md",
    ROOT / "AGENTS.md",
    ROOT / ".cursor" / "rules",
    ROOT / "docs" / "ai",
]

MAX_LINES = {"CLAUDE.md": 150, "AGENTS.md": 120}
MAX_MDC_LINES = 80

LINK_RE = re.compile(r"\]\(([^)]+)\)")
BACKTICK_RE = re.compile(r"`([^`]+)`")

# Paths we expect in docs (must exist under ROOT).
PATHLIKE = re.compile(
    r"^(?:\.{1,2}/|backend/|frontend/|docs/|scripts/|integrations/|\.cursor/|\.github/|\.env\.example|[A-Z][A-Z0-9_.-]*\.md)"
)

SKIP_LINK_PREFIXES = ("http://", "https://", "mailto:", "#")


def iter_md_files() -> list[Path]:
    out: list[Path] = []
    for base in SCAN_ROOTS:
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            out.extend(sorted(base.glob("*.md")))
            out.extend(sorted(base.glob("*.mdc")))
    return out


def normalize_path(raw: str) -> str | None:
    s = raw.strip()
    if not s or any(s.startswith(p) for p in SKIP_LINK_PREFIXES):
        return None
    if s.endswith(".md") and s.startswith("@docs/"):
        s = s.removeprefix("@docs/")
        s = f"docs/{s}" if not s.startswith("docs/") else s
    if "#" in s and not s.startswith("#"):
        s = s.split("#", 1)[0]
    if "*" in s or "{" in s:
        return None
    if not PATHLIKE.match(s):
        return None
    s = s.rstrip(".,;:")
    return s


def resolve_ref(ref: str, source: Path) -> Path | None:
    raw = normalize_path(ref)
    if raw is None:
        return None
    root_anchored = (
        "backend/",
        "frontend/",
        "docs/",
        "scripts/",
        "integrations/",
        ".cursor/",
        ".github/",
        ".env.example",
    )
    if raw.startswith(root_anchored):
        candidate = (ROOT / raw).resolve()
    elif raw.startswith(("./", "../")):
        candidate = (source.parent / raw).resolve()
    else:
        candidate = (ROOT / raw).resolve()
    root = ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate.relative_to(root)


def collect_refs(text: str, source: Path) -> set[Path]:
    found: set[Path] = set()
    for m in LINK_RE.finditer(text):
        rel = resolve_ref(m.group(1), source)
        if rel is not None:
            found.add(rel)
    for m in BACKTICK_RE.finditer(text):
        inner = m.group(1).strip()
        if (
            "/" in inner
            or inner.endswith((".md", ".mdc", ".py", ".tsx", ".ts", ".yml", ".yaml", ".toml"))
            or inner.startswith(("backend/", "frontend/", "docs/", ".cursor/", "scripts/"))
        ):
            rel = resolve_ref(inner, source)
            if rel is not None:
                found.add(rel)
    return found


def check_paths(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        for rel in sorted(collect_refs(text, fp), key=lambda p: str(p)):
            target = ROOT / rel
            if not target.exists():
                errors.append(f"{fp.relative_to(ROOT)}: missing path {rel.as_posix()!r}")
    return errors


def parse_mdc_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    block = text[4:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        data[key.strip()] = val.strip()
    return data


def check_mdc_rules() -> list[str]:
    errors: list[str] = []
    rules_dir = ROOT / ".cursor" / "rules"
    if not rules_dir.is_dir():
        return ["missing directory .cursor/rules"]
    for fp in sorted(rules_dir.glob("*.mdc")):
        text = fp.read_text(encoding="utf-8")
        if text.count("\n") + 1 > MAX_MDC_LINES:
            errors.append(f"{fp.name}: {text.count(chr(10)) + 1} lines (max {MAX_MDC_LINES})")
        meta = parse_mdc_frontmatter(text)
        if meta is None:
            errors.append(f"{fp.name}: missing or invalid YAML frontmatter")
            continue
        if "description" not in meta:
            errors.append(f"{fp.name}: frontmatter missing description")
        if meta.get("alwaysApply") not in ("true", "false"):
            errors.append(f"{fp.name}: alwaysApply must be true or false")
        if meta.get("alwaysApply") == "false" and "globs" not in meta:
            errors.append(f"{fp.name}: non-global rule must set globs")
    return errors


def check_line_budgets() -> list[str]:
    errors: list[str] = []
    for name, limit in MAX_LINES.items():
        fp = ROOT / name
        if not fp.is_file():
            errors.append(f"missing {name}")
            continue
        n = fp.read_text(encoding="utf-8").count("\n") + 1
        if n > limit:
            errors.append(f"{name}: {n} lines (max {limit})")
    return errors


def main() -> int:
    md_files = iter_md_files()
    errors = []
    errors.extend(check_paths(md_files))
    errors.extend(check_mdc_rules())
    errors.extend(check_line_budgets())
    if errors:
        print("check_ai_docs: FAILED", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("check_ai_docs: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
