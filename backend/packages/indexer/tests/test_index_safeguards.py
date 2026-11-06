from __future__ import annotations

from ci_core.db import GraphStore
from ci_core.models import JobStatus
from ci_indexer import create_project_from_path, run_index_job
from ci_indexer.pipeline import _index_lock


def test_second_index_job_fails_while_lock_held(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    lock = _index_lock(project.id)
    assert lock.acquire(blocking=False)
    try:
        job = run_index_job(project.id)
        assert job.status == JobStatus.FAILED
        assert "already running" in (job.error or "")
    finally:
        lock.release()


def test_fail_orphaned_running_jobs_leaves_completed(data_dir, project_copy):
    project = create_project_from_path(project_copy)
    store = GraphStore(project.id)
    running = store.create_job()
    running.status = JobStatus.RUNNING
    running.message = "stuck"
    store.update_job(running)
    done = store.create_job()
    done.status = JobStatus.COMPLETED
    store.update_job(done)

    assert store.fail_orphaned_running_jobs() == 1
    assert store.get_job(running.id).status == JobStatus.FAILED
    assert store.get_job(done.id).status == JobStatus.COMPLETED


def test_api_lifespan_reconciles_orphaned_jobs(data_dir, project_copy):
    from fastapi.testclient import TestClient

    from ci_api.main import app

    project = create_project_from_path(project_copy)
    store = GraphStore(project.id)
    job = store.create_job()
    job.status = JobStatus.RUNNING
    store.update_job(job)

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
    assert store.get_job(job.id).status == JobStatus.FAILED
