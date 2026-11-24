"""build_context token budgeting and missing_evidence."""

from __future__ import annotations

import pytest

from ci_ai import GraphTools
from ci_indexer import create_project_from_path, run_index_job


@pytest.fixture
def indexed_fullstack(data_dir, fullstack_copy):
    record = create_project_from_path(fullstack_copy)
    assert run_index_job(record.id).status.value == "completed"
    return record.id


def _snippet_char_total(ctx: dict) -> int:
    total = 0
    src = ctx.get("source")
    if src and isinstance(src.get("content"), str):
        total += len(src["content"])
    for sn in ctx.get("related_source") or []:
        if isinstance(sn.get("content"), str):
            total += len(sn["content"])
    return total


def test_build_context_without_token_budget_unchanged(indexed_fullstack):
    tools = GraphTools(indexed_fullstack)
    ctx = tools.build_context("get_item", max_snippets=3)
    assert "token_budget" not in ctx
    assert "snippet_chars_used" not in ctx
    assert ctx["source"] and "def get_item" in ctx["source"]["content"]
    assert not ctx["source"].get("truncated")
    assert isinstance(ctx.get("missing_evidence"), list)


def test_build_context_recognizes_content_and_truncates(indexed_fullstack):
    tools = GraphTools(indexed_fullstack)
    loose = tools.build_context("get_item", token_budget=8000)
    full_len = len(loose["source"]["content"])
    assert full_len > 0

    tight = tools.build_context("get_item", token_budget=8, max_snippets=1)
    assert tight["source"]["truncated"] is True
    assert len(tight["source"]["content"]) < full_len
    assert len(tight["source"]["content"]) <= 32
    assert tight["snippet_chars_used"] <= tight["snippet_char_budget"]
    assert any("truncated" in m for m in tight["missing_evidence"])


def test_build_context_shared_budget_across_snippets(indexed_fullstack):
    tools = GraphTools(indexed_fullstack)
    ctx = tools.build_context("get_item", token_budget=40, max_snippets=6)
    budget = ctx["snippet_char_budget"]
    assert _snippet_char_total(ctx) <= budget
    assert ctx["snippet_chars_used"] == _snippet_char_total(ctx)
    related = ctx.get("related_source") or []
    if related:
        omitted = [sn for sn in related if sn.get("truncated") and sn.get("content") == ""]
        truncated = [sn for sn in related if sn.get("truncated") and sn.get("content")]
        assert omitted or truncated or len(related) == 0


def test_build_context_missing_evidence_list(indexed_fullstack):
    tools = GraphTools(indexed_fullstack)
    ctx = tools.build_context("get_item", token_budget=4, max_snippets=6)
    assert isinstance(ctx["missing_evidence"], list)
    assert ctx["missing_evidence"]


def test_build_context_unknown_symbol_returns_error(indexed_fullstack):
    tools = GraphTools(indexed_fullstack)
    assert "error" in tools.build_context("00000000000000000000000000000000")
