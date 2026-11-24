from __future__ import annotations

from pathlib import Path

from ci_indexer.analyzers import analyze_project
from ci_indexer.changes import classify_changes


def test_typescript_analyzer_version_includes_v3():
    root = Path(__file__).resolve().parents[3] / "benchmarks" / "fixtures" / "next_app_router_min"
    version = analyze_project("ver", root).version
    assert "typescript:3" in version


def test_version_bump_forces_full_rebuild():
    files = {"app/page.tsx": {"sha": "1", "structural": "s", "role": "pages"}}
    prev = {"adapter_version": "python:6+typescript:2", "files": files}
    assert classify_changes(prev, files, adapter_version="python:6+typescript:3").level == "FULL"
    assert classify_changes(prev, files, adapter_version="python:6+typescript:3").reason == "analysis version changed"
