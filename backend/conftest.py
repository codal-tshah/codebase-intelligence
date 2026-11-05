from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "benchmarks" / "fixtures" / "synthetic_django"
FULLSTACK = Path(__file__).resolve().parent / "benchmarks" / "fixtures" / "fullstack_app"


@pytest.fixture
def fixture_root() -> Path:
    return FIXTURE


@pytest.fixture
def fullstack_root() -> Path:
    return FULLSTACK


@pytest.fixture
def fullstack_copy(tmp_path) -> Path:
    """A writable copy of the multi-language (FastAPI + React + Express/Nest) fixture."""
    dest = tmp_path / "fullstack"
    shutil.copytree(FULLSTACK, dest, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    return dest


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    """Isolated index storage so tests never touch ~/.codebase-intelligence."""
    path = tmp_path / "data"
    monkeypatch.setenv("CI_DATA_DIR", str(path))
    return path


@pytest.fixture
def project_copy(tmp_path) -> Path:
    """A writable copy of the synthetic Django project."""
    dest = tmp_path / "project"
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest
