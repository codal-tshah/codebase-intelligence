#!/usr/bin/env python3
"""Lightweight benchmark scorer for tool-only answers."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from ci_ai.tools import GraphTools
from ci_indexer import create_project_from_path, run_index_job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--questions", type=Path, default=Path("benchmarks/questions.yaml"))
    args = parser.parse_args()

    project = create_project_from_path(args.fixture.resolve())
    run_index_job(project.id)
    tools = GraphTools(project.id)
    data = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    passed = 0
    total = len(data["questions"])
    for q in data["questions"]:
        text = q["text"].lower()
        ok = False
        if "api/items" in text:
            trace = tools.trace_endpoint("api/items/")
            ok = any(
                (step.get("path") or "").endswith(q["expect_path_contains"])
                for step in trace.get("chain", [])
            )
        elif "list_items" in text:
            models = tools.list_models_for_view("list_items")
            ok = bool(models) or bool(tools.search_code("Item.objects"))
        elif "get_item" in text:
            hits = tools.search_code("get_item")
            ok = any(q["expect_path_contains"] in h["path"] for h in hits)
        if ok:
            passed += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {q['id']}: {q['text']}")
    print(f"Score: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
