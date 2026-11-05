from __future__ import annotations

from ci_core.db import GraphStore
from ci_core.fingerprints import load_fingerprints
from ci_core.models import JobStatus, NodeType
from ci_indexer import classify_changes, compute_freshness, create_project_from_path, run_index_job
from ci_indexer.pipeline import IndexPipeline


def _index(project, **kw):
    store = GraphStore(project.id)
    job = store.create_job()
    changes = IndexPipeline(project.id).run(job, **kw)
    return changes, store.get_job(job.id)


def test_full_then_skip_then_partial_then_architecture(data_dir, project_copy):
    project = create_project_from_path(project_copy)

    changes, job = _index(project)
    assert changes.level == "FULL" and job.status == JobStatus.COMPLETED

    changes, job = _index(project)
    assert changes.level == "SKIP"
    assert "up to date" in job.message

    # comment-only edit: content changes, structure does not
    views = project_copy / "shop" / "views.py"
    views.write_text(views.read_text() + "\n# a harmless comment\n")
    changes, _ = _index(project)
    assert changes.level == "PARTIAL"
    assert changes.cosmetic == ["shop/views.py"] and not changes.structural

    # structural edit in a non-architectural file (new function + call)
    services = project_copy / "shop" / "services.py"
    services.write_text(services.read_text() + "\n\ndef refund(order):\n    return charge(order)\n")
    changes, _ = _index(project)
    assert changes.level == "PARTIAL" and changes.structural == ["shop/services.py"]

    # new file => architecture-level rebuild; graph reflects it
    (project_copy / "shop" / "pricing.py").write_text("def discount(item):\n    return 0\n")
    changes, _ = _index(project)
    assert changes.level == "ARCHITECTURE" and changes.added == ["shop/pricing.py"]
    names = {n.name for n in GraphStore(project.id).list_all_nodes() if n.node_type == NodeType.FUNCTION}
    assert {"refund", "discount"} <= names


def test_removed_files_leave_no_stale_nodes_or_chunks(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    _index(project)
    (project_copy / "shop" / "signals.py").unlink()
    changes, _ = _index(project)
    assert changes.removed == ["shop/signals.py"]
    store = GraphStore(project.id)
    assert all(n.source_path != "shop/signals.py" for n in store.list_all_nodes())
    assert not any(c["source_path"] == "shop/signals.py" for c in store.search_chunks([1.0] * 256, limit=500))
    ids = {n.id for n in store.list_all_nodes()}
    assert all(e.source_id in ids and e.target_id in ids for e in store.list_edges())


def test_chunks_are_not_duplicated_on_reindex(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    _index(project)
    store = GraphStore(project.id)
    before = len(store.search_chunks([1.0] * 256, limit=10_000))
    (project_copy / "shop" / "views.py").write_text((project_copy / "shop" / "views.py").read_text() + "\n# x\n")
    _index(project)
    after = len(store.search_chunks([1.0] * 256, limit=10_000))
    assert after == before


def test_project_is_reused_for_same_path(data_dir, project_copy):
    a = create_project_from_path(project_copy)
    b = create_project_from_path(project_copy)
    assert a.id == b.id


def test_freshness_transitions(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    assert compute_freshness(project.id, project_copy)["status"] == "unknown"
    run_index_job(project.id)
    assert compute_freshness(project.id, project_copy)["status"] == "fresh"
    (project_copy / "shop" / "views.py").write_text("# rewritten\n")
    fresh = compute_freshness(project.id, project_copy)
    assert fresh["status"] == "stale"  # not a git repo, so "dirty" cannot be proven
    assert fresh["changed_files"] == ["shop/views.py"]


def test_classify_full_when_adapter_version_changes():
    files = {"a.py": {"sha": "1", "structural": "s", "role": "views"}}
    prev = {"adapter_version": "1", "files": files}
    assert classify_changes(prev, files, adapter_version="2").level == "FULL"
    assert classify_changes(prev, files, adapter_version="1").level == "SKIP"
    assert classify_changes(prev, files, adapter_version="1", force=True).level == "FULL"


def test_fingerprints_persist_roles_and_lines(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    run_index_job(project.id)
    files = load_fingerprints(project.id)["files"]
    assert files["shop/models.py"]["role"] == "models"
    assert files["shop/models.py"]["lines"] > 5
