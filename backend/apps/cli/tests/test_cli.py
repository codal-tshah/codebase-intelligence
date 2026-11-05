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
