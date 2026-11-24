from __future__ import annotations

import json
from pathlib import Path

from ci_adapters_typescript import ANALYZER
from ci_core.models import EdgeType
from ci_parsers import list_source_files
from ci_parsers.workspaces import discover_workspace_package_dirs, workspace_name_map


def _write_pkg(base: Path, rel: str, name: str) -> None:
    d = base / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / "package.json").write_text(json.dumps({"name": name, "version": "1.0.0"}), encoding="utf-8")


def test_npm_workspaces_array_glob(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "packages/shared", "@acme/shared")
    _write_pkg(tmp_path, "apps/web", "@acme/web")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*", "apps/*"]}),
        encoding="utf-8",
    )
    pkgs, warnings = discover_workspace_package_dirs(tmp_path)
    assert warnings == []
    assert set(pkgs) == {"packages/shared", "apps/web"}


def test_npm_workspaces_object_style(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "packages/a", "@acme/a")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": {"packages": ["packages/*"]}}),
        encoding="utf-8",
    )
    pkgs, _ = discover_workspace_package_dirs(tmp_path)
    assert "packages/a" in pkgs


def test_pnpm_workspace_yaml(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "libs/util", "@acme/util")
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'libs/*'\n", encoding="utf-8")
    pkgs, _ = discover_workspace_package_dirs(tmp_path)
    assert "libs/util" in pkgs


def test_workspace_exclusion_pattern(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "packages/keep", "@acme/keep")
    _write_pkg(tmp_path, "packages/skip", "@acme/skip")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/*", "!packages/skip"]}),
        encoding="utf-8",
    )
    pkgs, _ = discover_workspace_package_dirs(tmp_path)
    assert "packages/keep" in pkgs
    assert "packages/skip" not in pkgs


def test_workspace_missing_member_warns(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/missing"]}),
        encoding="utf-8",
    )
    pkgs, warnings = discover_workspace_package_dirs(tmp_path)
    assert not pkgs
    assert any("not found" in w for w in warnings)


def test_workspace_outside_root_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "other_pkg"
    outside.mkdir(exist_ok=True)
    (outside / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["../other_pkg"]}), encoding="utf-8")
    pkgs, warnings = discover_workspace_package_dirs(tmp_path)
    assert not pkgs
    assert any("outside" in w for w in warnings)


def test_workspace_dedupes_literal_and_glob(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "packages/shared", "@acme/shared")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["packages/shared", "packages/*"]}),
        encoding="utf-8",
    )
    pkgs, _ = discover_workspace_package_dirs(tmp_path)
    assert list(pkgs.keys()).count("packages/shared") == 1


def test_workspace_ignores_node_modules_tree(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "packages/real", "@acme/real")
    nm = tmp_path / "packages/real/node_modules/@scope/ghost"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text(json.dumps({"name": "@scope/ghost"}), encoding="utf-8")
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["packages/*"]}), encoding="utf-8")
    pkgs, _ = discover_workspace_package_dirs(tmp_path)
    assert set(pkgs) == {"packages/real"}


def test_workspace_name_map_collision_keeps_first(tmp_path: Path) -> None:
    _write_pkg(tmp_path, "a/pkg", "dup")
    _write_pkg(tmp_path, "b/pkg", "dup")
    data = {"a/pkg": {"name": "dup"}, "b/pkg": {"name": "dup"}}
    assert workspace_name_map(data)["dup"] == "a/pkg"


def test_package_name_import_via_workspace(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3] / "benchmarks" / "fixtures" / "workspace_npm"
    files = list_source_files(root, ANALYZER.extensions)
    result = ANALYZER.analyze("ws-import", root, files)
    imports = [e for e in result.edges if e.edge_type == EdgeType.IMPORTS]
    assert imports
    assert workspace_name_map(discover_workspace_package_dirs(root)[0]).get("@fixture/shared")
