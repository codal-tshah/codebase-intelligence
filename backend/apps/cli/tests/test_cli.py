from __future__ import annotations

import json

from typer.testing import CliRunner

from ci_cli.main import app

runner = CliRunner()


def test_cli_analyze_then_query_by_path(data_dir, fullstack_copy):
    assert runner.invoke(app, ["analyze", str(fullstack_copy)]).exit_code == 0

    res = runner.invoke(app, ["endpoints", "-p", str(fullstack_copy), "--json"])
    assert res.exit_code == 0, res.output
    routes = {(tuple(e["methods"]), e["route"]) for e in json.loads(res.output)}
    assert (("POST",), "/api/orders") in routes and (("GET",), "/v1/orders") in routes

    res = runner.invoke(app, ["trace", "/api/items/7", "-X", "GET", "-p", str(fullstack_copy / "web"), "--json"])
    assert json.loads(res.output)["handler"]["name"] == "get_item"  # a path inside the repo resolves the project

    res = runner.invoke(app, ["ask", "Which tables exist?", "-p", str(fullstack_copy), "--json"])
    body = json.loads(res.output)
    assert "Item" in body["answer"] and body["citations"]


def test_cli_impact_gate_exits_nonzero_on_high_risk(data_dir, fullstack_copy):
    runner.invoke(app, ["analyze", str(fullstack_copy)])
    db = fullstack_copy / "api" / "app" / "db.py"
    res = runner.invoke(app, ["impact", str(db), "-p", str(fullstack_copy), "--fail-on", "high"])
    assert res.exit_code == 2, res.output
    assert "Risk: high" in res.output
    res = runner.invoke(app, ["impact", "web/src/components/ItemCard.tsx", "-p", str(fullstack_copy), "--fail-on", "high"])
    assert res.exit_code == 0, res.output


def test_cli_unknown_project_is_a_clear_error(data_dir, tmp_path):
    res = runner.invoke(app, ["status", str(tmp_path / "missing")])
    assert res.exit_code == 1 and "ci analyze" in res.output


def test_cli_impact_base_ref_diffs_git_history(data_dir, fullstack_copy):
    import subprocess

    def git(*args):
        subprocess.run(["git", "-C", str(fullstack_copy), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)

    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "base")
    db = fullstack_copy / "api" / "app" / "db.py"
    db.write_text(db.read_text() + "\n# touched\n")
    git("commit", "-qam", "change model file")
    runner.invoke(app, ["analyze", str(fullstack_copy)])
    res = runner.invoke(app, ["impact", "--base", "HEAD~1", "-p", str(fullstack_copy), "--fail-on", "high"])
    assert res.exit_code == 2 and "Risk: high" in res.output, res.output
    assert runner.invoke(app, ["impact", "--base", "no-such-ref", "-p", str(fullstack_copy)]).exit_code == 1


def test_cli_jobs_suggest_and_docs(data_dir, fullstack_copy):
    assert runner.invoke(app, ["analyze", str(fullstack_copy)]).exit_code == 0
    res = runner.invoke(app, ["jobs", "-p", str(fullstack_copy), "--json"])
    assert res.exit_code == 0 and json.loads(res.output) == []
    res = runner.invoke(app, ["suggest", "-p", str(fullstack_copy), "--json"])
    assert res.exit_code == 0 and isinstance(json.loads(res.output), list)
    res = runner.invoke(app, ["docs", "-p", str(fullstack_copy)])
    assert res.exit_code == 0, res.output
    assert (fullstack_copy / "docs/codebase-map/api-flows.md").is_file()
    assert runner.invoke(app, ["docs", "-p", str(fullstack_copy), "-o", "../escape"]).exit_code == 1


def test_cli_hook_install_is_idempotent_and_preserves_existing_hook(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "post-commit").write_text("#!/bin/sh\necho mine\n")
    for _ in range(2):
        assert runner.invoke(app, ["hook", "install", "--path", str(tmp_path)]).exit_code == 0
    text = (hooks / "post-commit").read_text()
    assert "echo mine" in text and text.count(">>> codebase-intelligence") == 1 and "--incremental" in text
    assert runner.invoke(app, ["hook", "status", "--path", str(tmp_path)]).output.strip() == "installed"
    assert runner.invoke(app, ["hook", "uninstall", "--path", str(tmp_path)]).exit_code == 0
    text = (hooks / "post-commit").read_text()
    assert "echo mine" in text and "codebase-intelligence" not in text
    assert runner.invoke(app, ["hook", "install", "--path", str(tmp_path / "nope")]).exit_code == 1


def test_cli_hook_runs_before_existing_exit_and_uninstall_is_side_effect_free(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    assert runner.invoke(app, ["hook", "uninstall", "--path", str(tmp_path)]).exit_code == 0
    assert not (hooks / "post-commit").exists()  # nothing installed: nothing written
    (hooks / "post-commit").write_text("#!/bin/sh\necho mine\nexit 0\n")
    assert runner.invoke(app, ["hook", "install", "--path", str(tmp_path)]).exit_code == 0
    text = (hooks / "post-commit").read_text()
    assert text.index("--incremental") < text.index("exit 0")
    assert runner.invoke(app, ["hook", "uninstall", "--path", str(tmp_path)]).exit_code == 0
    assert (hooks / "post-commit").read_text() == "#!/bin/sh\necho mine\nexit 0\n"
    (hooks / "post-commit").write_text("#!/usr/bin/env python3\nprint('hi')\n")
    assert runner.invoke(app, ["hook", "install", "--path", str(tmp_path)]).exit_code == 1
    assert "codebase-intelligence" not in (hooks / "post-commit").read_text()


def test_cli_jobs_text_output_lists_detected_jobs(data_dir, fullstack_copy):
    (fullstack_copy / "api" / "app" / "tasks.py").write_text(
        "from celery import shared_task\n\n@shared_task\ndef sync_orders():\n    return None\n"
    )
    assert runner.invoke(app, ["analyze", str(fullstack_copy)]).exit_code == 0
    res = runner.invoke(app, ["jobs", "-p", str(fullstack_copy)])
    assert res.exit_code == 0, res.output
    assert "sync_orders" in res.output and "tasks.py" in res.output


def test_cli_hook_covers_pull_checkout_and_rebase(tmp_path):
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True)
    assert runner.invoke(app, ["hook", "install", "--path", str(tmp_path)]).exit_code == 0
    for name in ("post-commit", "post-merge", "post-checkout", "post-rewrite"):
        text = (hooks / name).read_text()
        assert "--incremental" in text, name
    assert '[ "$3" = "1" ]' in (hooks / "post-checkout").read_text()  # branch switches only
    assert runner.invoke(app, ["hook", "uninstall", "--path", str(tmp_path)]).exit_code == 0
    assert not any((hooks / n).exists() for n in ("post-merge", "post-checkout", "post-rewrite"))


def test_cli_projects_rename_and_remove_keeps_source(data_dir, project_copy):
    assert runner.invoke(app, ["analyze", str(project_copy)]).exit_code == 0
    before = sorted(p.relative_to(project_copy).as_posix() for p in project_copy.rglob("*"))
    res = runner.invoke(app, ["projects", "rename", str(project_copy), "Shop"])
    assert res.exit_code == 0, res.output
    assert "Shop" in runner.invoke(app, ["projects"]).output
    res = runner.invoke(app, ["projects", "remove", "Shop"], input="n\n")
    assert res.exit_code == 1 and "NOT touched" in res.output
    res = runner.invoke(app, ["projects", "remove", "Shop", "--yes"])
    assert res.exit_code == 0 and "removed" in res.output
    assert runner.invoke(app, ["projects", "--json"]).output.strip() == "[]"
    assert sorted(p.relative_to(project_copy).as_posix() for p in project_copy.rglob("*")) == before
