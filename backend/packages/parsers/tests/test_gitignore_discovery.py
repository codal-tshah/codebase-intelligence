"""File discovery honours repository `.gitignore`, `.ciignore`, and built-in skips."""

from __future__ import annotations

from pathlib import Path

from ci_parsers.files import DEFAULT_SKIP_DIRS, list_python_files


def test_gitignore_excludes_ignored_python_files(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("tests/\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_x(): pass\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"app/main.py"}


def test_gitignore_negation_unignores_file(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("scratch/\n!scratch/keep.py\n", encoding="utf-8")
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch" / "drop.py").write_text("x = 0\n", encoding="utf-8")
    (tmp_path / "scratch" / "keep.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("z = 2\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"app.py", "scratch/keep.py"}


def test_gitignore_directory_only_pattern(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("vendor/\n", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("v = 1\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("m = 1\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"src/main.py"}


def test_no_gitignore_still_discovers_python(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("b = 2\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"pkg/a.py", "pkg/b.py"}


def test_ciignore_patterns_still_apply(tmp_path: Path) -> None:
    (tmp_path / ".ciignore").write_text("legacy/\n", encoding="utf-8")
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "old.py").write_text("o = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("a = 1\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"app.py"}


def test_default_skip_dirs_exclude_node_modules(tmp_path: Path) -> None:
    assert "node_modules" in DEFAULT_SKIP_DIRS
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.py").write_text("d = 1\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("m = 1\n", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in list_python_files(tmp_path)}
    assert found == {"main.py"}
