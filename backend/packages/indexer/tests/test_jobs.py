"""Background/scheduled jobs are detected (Python + TS) and the Jobs view traces them to model writes."""

from __future__ import annotations

import shutil
from pathlib import Path

from ci_core.insights import GraphIndex
from ci_core.views import build_view, view_catalog
from ci_indexer import analyze_project

FIXTURE_DB = Path(__file__).resolve().parents[3] / "benchmarks/fixtures/fullstack_app/api/app/db.py"


def _project(root: Path) -> Path:
    app = root / "app"
    (app / "management/commands").mkdir(parents=True)
    shutil.copy(FIXTURE_DB, app / "db.py")
    (app / "__init__.py").write_text("")
    (app / "tasks.py").write_text(
        "from celery import shared_task\n"
        "from celery.schedules import crontab\n"
        "from apscheduler.schedulers.background import BackgroundScheduler\n"
        "from sqlalchemy.orm import Session\n"
        "from app.db import Order\n\n"
        "scheduler = BackgroundScheduler()\n\n"
        "def save_order(item_id):\n"
        "    session = Session()\n"
        "    session.add(Order(item_id=item_id))\n\n"
        "@shared_task(run_every=crontab(minute=0))\n"
        "def sync_orders():\n"
        "    save_order(1)\n\n"
        "@scheduler.scheduled_job('cron', hour=3)\n"
        "def nightly_report():\n"
        "    return None\n"
    )
    (app / "management/commands/cleanup.py").write_text(
        "from django.core.management.base import BaseCommand\n\n"
        "class Command(BaseCommand):\n"
        "    def handle(self, *args, **options):\n"
        "        return None\n"
    )
    web = root / "web/src"
    web.mkdir(parents=True)
    (web / "report.service.ts").write_text(
        "import { Injectable } from '@nestjs/common';\n"
        "import { Cron } from '@nestjs/schedule';\n\n"
        "@Injectable()\n"
        "export class ReportService {\n"
        "  @Cron('0 3 * * *')\n"
        "  nightly() { return 1; }\n"
        "}\n"
    )
    return root


def test_jobs_detected_and_traced_to_model_writes(tmp_path):
    res = analyze_project("p", _project(tmp_path)).result
    jobs = {n.name: n.properties["job"] for n in res.nodes if n.properties.get("job")}
    assert jobs["sync_orders"]["framework"] == "celery"
    assert jobs["sync_orders"]["kind"] == "scheduled" and "crontab" in jobs["sync_orders"]["schedule"]
    assert jobs["nightly_report"] == {"kind": "scheduled", "framework": "apscheduler", "schedule": "cron hour=3"}
    assert jobs["Command.handle"]["command"] == "cleanup"
    assert jobs["ReportService.nightly"] == {"kind": "scheduled", "framework": "nestjs-schedule", "schedule": "0 3 * * *"}
    assert all("job" in (n.properties.get("tags") or []) for n in res.nodes if n.properties.get("job"))

    index = GraphIndex.build(res.nodes, res.edges)
    catalog = {v["id"]: v for v in view_catalog(index)}
    assert catalog["jobs"]["available"] and catalog["jobs"]["count"] == 4

    payload = build_view(index, "jobs")
    labels = {n.label for n in payload.nodes}
    assert {"sync_orders", "save_order", "Order"} <= labels
    by_id = {n.id: n.label for n in payload.nodes}
    writes = {(by_id[e.source], by_id[e.target]) for e in payload.edges if e.edge_type == "WRITES_MODEL"}
    assert ("save_order", "Order") in writes
    assert payload.metadata["job_count"] == 4


def test_jobs_view_unavailable_without_jobs():
    index = GraphIndex.build([], [])
    assert next(v for v in view_catalog(index) if v["id"] == "jobs")["available"] is False


def test_docs_render_mermaid_with_helper_text_and_stay_in_repo(tmp_path):
    import pytest
    from ci_core.docgen import render_docs, write_docs

    root = _project(tmp_path)
    res = analyze_project("p", root).result
    index = GraphIndex.build(res.nodes, res.edges)
    files = render_docs(index, "demo")
    assert {"README.md", "architecture.md", "jobs.md", "data-model.md", "suggestions.md"} <= set(files)
    assert "```mermaid\nflowchart LR" in files["jobs.md"] and "|writes|" in files["jobs.md"]
    assert "sync_orders" in files["jobs.md"] and "crontab" in files["jobs.md"]
    assert "erDiagram" in files["data-model.md"] and "orders" in files["data-model.md"]
    written = write_docs(index, "demo", root, "docs/map")
    assert (root / "docs/map/README.md") in written
    with pytest.raises(ValueError):
        write_docs(index, "demo", root, "../outside")


def test_suggestions_flag_duplicates_hubs_and_unused():
    from ci_core.models import EdgeRecord, EdgeType, NodeRecord, NodeType
    from ci_core.suggestions import suggest

    def fn(i, name, path, **props):
        return NodeRecord(id=i, project_id="p", node_type=NodeType.FUNCTION, name=name, qualified_name=name,
                          source_path=path, start_line=1, end_line=5, extractor="t", confidence=1, properties=props)

    nodes = [fn("h", "core_helper", "a.py"), fn("d1", "format_money", "b.py"), fn("d2", "format_money", "c.py"),
             fn("u", "orphan_util", "d.py")]
    callers = [fn(f"c{i}", f"caller{i}", f"x{i}.py", role="views") for i in range(12)]
    edges = [EdgeRecord(id=f"e{i}", project_id="p", source_id=c.id, target_id="h", edge_type=EdgeType.CALLS,
                        extractor="t", confidence=1) for i, c in enumerate(callers)]
    edges += [EdgeRecord(id=f"f{i}", project_id="p", source_id="h", target_id=t, edge_type=EdgeType.CALLS,
                         extractor="t", confidence=1) for i, t in enumerate(["d1", "d2"])]
    kinds = {s["kind"]: s for s in suggest(GraphIndex.build([*nodes, *callers], edges))}
    assert "core_helper" in kinds["hotspot"]["title"]
    assert "format_money" in kinds["duplication"]["title"]
    assert [n["name"] for n in kinds["unused"]["nodes"]] == ["orphan_util"]
