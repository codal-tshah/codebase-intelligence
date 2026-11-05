from __future__ import annotations

import json
import logging
from pathlib import Path

from ci_core.config import project_dir
from ci_core.db import GraphStore, new_id
from ci_core.models import IndexJobRecord, JobStatus, ProjectRecord, utcnow
from ci_core.registry import load_registry, register_project
from ci_core.fingerprints import load_fingerprints, save_fingerprints
from ci_indexer.analyzers import analyze_project
from ci_indexer.changes import ChangeSet, classify_changes
from ci_parsers import git_head_sha

log = logging.getLogger("ci_indexer")


class IndexPipeline:
    """Analyse -> classify changes -> rewrite graph -> refresh embeddings for touched files.

    Analysis is a whole-project AST pass (cheap and required for correct cross-file
    edges), so the graph is always rewritten atomically from a fresh analysis.
    Fingerprints decide whether to rewrite at all and which files need new embeddings.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.store = GraphStore(project_id)

    def run(self, job: IndexJobRecord, *, force: bool = False, embed: bool = True) -> ChangeSet:
        project = self.store.get_project()
        if project is None:
            raise ValueError("project not found")
        root = Path(project.root_path)
        if not root.exists():
            raise FileNotFoundError(f"project path does not exist: {root}")

        job.status = JobStatus.RUNNING
        job.message = "Analyzing project"
        job.progress = 0.1
        self.store.update_job(job)

        project_analysis = analyze_project(self.project_id, root)
        analysis = project_analysis.result
        log.info("analyzed %s: %d files, %d nodes, %d edges", project.name, len(analysis.files), len(analysis.nodes), len(analysis.edges), extra={"project_id": self.project_id, "phase": "analyze"})
        version = project_analysis.version
        previous = load_fingerprints(self.project_id)
        counts = self.store.counts()
        changes = classify_changes(
            previous,
            analysis.files,
            adapter_version=version,
            force=force,
            graph_is_empty=counts["nodes"] == 0,
        )
        commit = git_head_sha(root)
        log.info("change level %s: %s", changes.level, changes.reason, extra={"project_id": self.project_id, "phase": "classify"})

        if changes.level == "SKIP":
            project.commit_sha = commit
            project.updated_at = utcnow()
            self.store.upsert_project(project)
            register_project(project)
            if previous:
                save_fingerprints(
                    self.project_id, previous["files"], adapter_version=version, commit_sha=commit
                )
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.message = "Index already up to date (no file changes)"
            self.store.update_job(job)
            return changes

        job.message = f"{changes.level.title()} index: {changes.reason}"
        job.progress = 0.5
        self.store.update_job(job)

        project.framework = ", ".join(analysis.frameworks) or (", ".join(project_analysis.analyzers) or None)
        project.commit_sha = commit
        project.updated_at = utcnow()
        self.store.upsert_project(project)
        register_project(project)  # the registry is what the API/CLI list

        keep_chunks = changes.level != "FULL"
        self.store.clear_graph(keep_chunks=keep_chunks)
        self.store.replace_graph(analysis.nodes, analysis.edges)

        (project_dir(self.project_id) / "meta.json").write_text(
            json.dumps(
                {
                    **analysis.meta,
                    "installed_apps": analysis.meta.get("installed_apps", []),
                    "middleware": analysis.meta.get("middleware", []),
                    "root_urlconf": analysis.meta.get("root_urlconf"),
                    "frameworks": analysis.frameworks,
                    "analyzers": project_analysis.analyzers,
                    "analysis_version": version,
                    "languages": sorted({str(f.get("language")) for f in analysis.files.values() if f.get("language")}),
                    "indexed_files": len(analysis.files),
                    "warnings": analysis.warnings[:50],
                    "stats": analysis.stats,
                    "last_change": changes.to_dict(),
                }
            ),
            encoding="utf-8",
        )

        if embed:
            from ci_ai.embeddings import embed_project_chunks

            job.message = "Building embeddings"
            job.progress = 0.8
            self.store.update_job(job)
            if changes.level == "FULL":
                embed_project_chunks(self.project_id, root)
            else:
                self.store.delete_chunks(changes.touched)
                embed_project_chunks(self.project_id, root, only_paths={*changes.added, *changes.modified})

        save_fingerprints(self.project_id, analysis.files, adapter_version=version, commit_sha=commit)

        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        suffix = f" ({len(analysis.warnings)} file(s) could not be parsed)" if analysis.warnings else ""
        job.message = f"Index complete: {len(analysis.nodes)} nodes, {len(analysis.edges)} edges{suffix}"
        self.store.update_job(job)
        return changes


def create_project_from_path(
    path: Path, *, git_url: str | None = None, project_id: str | None = None
) -> ProjectRecord:
    path = path.resolve()
    if project_id is None:
        existing = next((p for p in load_registry() if p.root_path == str(path)), None)
        project_id = existing.id if existing else new_id()
    store = GraphStore(project_id)
    previous = store.get_project()
    record = ProjectRecord(
        id=project_id,
        name=path.name,
        root_path=str(path),
        git_url=git_url or (previous.git_url if previous else None),
        commit_sha=previous.commit_sha if previous else None,
        framework=previous.framework if previous else None,
        created_at=previous.created_at if previous else utcnow(),
    )
    store.upsert_project(record)
    register_project(record)
    return record


def create_project_from_git(git_url: str, work_root: Path | None = None) -> ProjectRecord:
    from ci_core.config import get_data_dir
    from ci_parsers import clone_git_repo

    slug = git_url.rstrip("/").split("/")[-1].replace(".git", "")
    dest = (work_root or get_data_dir() / "sources") / slug
    clone_git_repo(git_url, dest)
    return create_project_from_path(dest, git_url=git_url)


def run_index_job(
    project_id: str, *, incremental: bool = False, job_id: str | None = None
) -> IndexJobRecord:
    """Run an index job. `incremental=False` forces a full rebuild; True skips unchanged work."""
    store = GraphStore(project_id)
    job = (store.get_job(job_id) if job_id else None) or store.create_job()
    project = store.get_project()
    if project is None:
        job.status = JobStatus.FAILED
        job.error = "project not found"
        store.update_job(job)
        return job

    try:
        IndexPipeline(project_id).run(job, force=not incremental)
    except Exception as exc:  # noqa: BLE001
        log.exception("index failed", extra={"project_id": project_id, "job_id": job.id})
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.message = "Index failed"
        store.update_job(job)
    return job
