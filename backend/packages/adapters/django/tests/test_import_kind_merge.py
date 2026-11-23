"""Merged IMPORTS edges: runtime import_kind wins over TYPE_CHECKING duplicates."""

from __future__ import annotations

from pathlib import Path

import pytest

from ci_adapters_django import analyze_django_project
from ci_core.models import EdgeType


def _import_edge(result, src: str, tgt: str):
    names = {n.id: n.name for n in result.nodes}
    for e in result.edges:
        if e.edge_type != EdgeType.IMPORTS:
            continue
        if names.get(e.source_id) == src and names.get(e.target_id) == tgt:
            return e.properties
    return None


@pytest.fixture
def imkind_root(tmp_path: Path) -> Path:
    pkg = tmp_path / "imkind"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "b.py").write_text('"""target module"""\n')
    (pkg / "a.py").write_text(
        "import imkind.b\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import imkind.b\n"
    )
    (pkg / "c.py").write_text(
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import imkind.b\nimport imkind.b\n"
    )
    (pkg / "d.py").write_text("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import imkind.b\n")
    return tmp_path


def test_runtime_wins_when_merged_with_type_checking(imkind_root: Path):
    res = analyze_django_project("imkind", imkind_root)
    for src in ("imkind/a", "imkind/c"):
        props = _import_edge(res, src, "imkind/b")
        assert props is not None and props.get("import_kind") is None and props.get("has_runtime_import") is True
    d_props = _import_edge(res, "imkind/d", "imkind/b")
    assert d_props is not None and d_props.get("import_kind") == "type_only"
    assert "has_runtime_import" not in d_props
