from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any
from collections.abc import Iterable

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ci_core.config import project_dir
from ci_core.insights import GraphIndex
from ci_core.models import (
    EdgeRecord,
    EdgeType,
    GraphViewPayload,
    IndexJobRecord,
    JobStatus,
    NodeRecord,
    NodeType,
    ProjectRecord,
    utcnow,
)
from ci_core.views import build_view


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    root_path = Column(String, nullable=False)
    git_url = Column(String, nullable=True)
    commit_sha = Column(String, nullable=True)
    framework = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class NodeRow(Base):
    __tablename__ = "nodes"
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), index=True, nullable=False)
    node_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    qualified_name = Column(String, nullable=True, index=True)
    source_path = Column(String, nullable=True)
    start_line = Column(Float, nullable=True)
    end_line = Column(Float, nullable=True)
    extractor = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    properties_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, nullable=False)


class EdgeRow(Base):
    __tablename__ = "edges"
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), index=True, nullable=False)
    edge_type = Column(String, nullable=False, index=True)
    source_id = Column(String, ForeignKey("nodes.id"), index=True, nullable=False)
    target_id = Column(String, ForeignKey("nodes.id"), index=True, nullable=False)
    source_path = Column(String, nullable=True)
    start_line = Column(Float, nullable=True)
    end_line = Column(Float, nullable=True)
    extractor = Column(String, nullable=False)
    confidence = Column(Float, nullable=False, default=1.0)
    properties_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), index=True, nullable=False)
    status = Column(String, nullable=False)
    progress = Column(Float, nullable=False, default=0.0)
    message = Column(Text, nullable=False, default="")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class ChunkRow(Base):
    __tablename__ = "chunks"
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), index=True, nullable=False)
    node_id = Column(String, ForeignKey("nodes.id"), nullable=True)
    source_path = Column(String, nullable=False)
    start_line = Column(Float, nullable=False)
    end_line = Column(Float, nullable=False)
    content = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, nullable=False)


class LLMRequestRow(Base):
    __tablename__ = "llm_requests"
    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("projects.id"), index=True, nullable=False)
    token_estimate = Column(Float, nullable=False, default=0)
    redaction_count = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)


def db_path_for_project(project_id: str) -> Path:
    return project_dir(project_id) / "index.db"


_ENGINES: dict[str, sessionmaker[Session]] = {}
_ENGINE_LOCK = threading.Lock()
# (db path) -> (file signature, GraphIndex). Requests reuse the parsed graph until the DB changes.
_INDEX_CACHE: dict[str, tuple[tuple[int, int], GraphIndex]] = {}


def get_engine(project_id: str):
    path = db_path_for_project(project_id)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(project_id: str) -> sessionmaker[Session]:
    """One engine + schema check per database file (engines are expensive; requests are not)."""
    key = str(db_path_for_project(project_id))
    factory = _ENGINES.get(key)
    if factory is not None and Path(key).exists():
        return factory
    with _ENGINE_LOCK:
        factory = _ENGINES.get(key)
        if factory is None or not Path(key).exists():
            engine = get_engine(project_id)
            Base.metadata.create_all(engine)
            factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            _ENGINES[key] = factory
    return factory


def _db_signature(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _json_loads(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


def _json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data)


class GraphStore:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self._session_factory = init_db(project_id)

    def session(self) -> Session:
        return self._session_factory()

    def upsert_project(self, project: ProjectRecord) -> None:
        with self.session() as session:
            row = session.get(ProjectRow, project.id)
            if row is None:
                row = ProjectRow(id=project.id)
                session.add(row)
            row.name = project.name
            row.root_path = project.root_path
            row.git_url = project.git_url
            row.commit_sha = project.commit_sha
            row.framework = project.framework
            row.created_at = project.created_at
            row.updated_at = project.updated_at
            session.commit()

    def get_project(self) -> ProjectRecord | None:
        with self.session() as session:
            row = session.get(ProjectRow, self.project_id)
            if row is None:
                return None
            return ProjectRecord(
                id=row.id,
                name=row.name,
                root_path=row.root_path,
                git_url=row.git_url,
                commit_sha=row.commit_sha,
                framework=row.framework,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def replace_graph(
        self,
        nodes: Iterable[NodeRecord],
        edges: Iterable[EdgeRecord],
        *,
        delete_paths: set[str] | None = None,
    ) -> None:
        with self.session() as session:
            if delete_paths:
                node_ids = list(
                    session.scalars(
                        select(NodeRow.id).where(
                            NodeRow.project_id == self.project_id,
                            NodeRow.source_path.in_(delete_paths),
                        )
                    ).all()
                )
                if node_ids:
                    session.query(EdgeRow).filter(
                        (EdgeRow.source_id.in_(node_ids)) | (EdgeRow.target_id.in_(node_ids))
                    ).delete(synchronize_session=False)
                    session.query(NodeRow).filter(NodeRow.id.in_(node_ids)).delete(
                        synchronize_session=False
                    )
            now = utcnow()
            for node in nodes:
                row = session.get(NodeRow, node.id)
                if row is None:
                    row = NodeRow(id=node.id, project_id=self.project_id)
                    session.add(row)
                row.node_type = node.node_type.value
                row.name = node.name
                row.qualified_name = node.qualified_name
                row.source_path = node.source_path
                row.start_line = node.start_line
                row.end_line = node.end_line
                row.extractor = node.extractor
                row.confidence = node.confidence
                row.properties_json = _json_dumps(node.properties)
                row.updated_at = now
            for edge in edges:
                row = session.get(EdgeRow, edge.id)
                if row is None:
                    row = EdgeRow(id=edge.id, project_id=self.project_id)
                    session.add(row)
                row.edge_type = edge.edge_type.value
                row.source_id = edge.source_id
                row.target_id = edge.target_id
                row.source_path = edge.source_path
                row.start_line = edge.start_line
                row.end_line = edge.end_line
                row.extractor = edge.extractor
                row.confidence = edge.confidence
                row.properties_json = _json_dumps(edge.properties)
                row.updated_at = now
            session.commit()

    def list_nodes(
        self,
        *,
        node_type: NodeType | None = None,
        name_contains: str | None = None,
        limit: int = 500,
    ) -> list[NodeRecord]:
        with self.session() as session:
            q = select(NodeRow).where(NodeRow.project_id == self.project_id)
            if node_type:
                q = q.where(NodeRow.node_type == node_type.value)
            if name_contains:
                q = q.where(NodeRow.name.contains(name_contains))
            q = q.limit(limit)
            rows = session.scalars(q).all()
            return [_node_from_row(r) for r in rows]

    def get_node(self, node_id: str) -> NodeRecord | None:
        with self.session() as session:
            row = session.get(NodeRow, node_id)
            if row is None or row.project_id != self.project_id:
                return None
            return _node_from_row(row)

    def get_edges_for_node(self, node_id: str) -> list[EdgeRecord]:
        with self.session() as session:
            rows = session.scalars(
                select(EdgeRow).where(
                    EdgeRow.project_id == self.project_id,
                    (EdgeRow.source_id == node_id) | (EdgeRow.target_id == node_id),
                )
            ).all()
            return [_edge_from_row(r) for r in rows]

    def list_edges(self, edge_type: EdgeType | None = None) -> list[EdgeRecord]:
        with self.session() as session:
            q = select(EdgeRow).where(EdgeRow.project_id == self.project_id)
            if edge_type:
                q = q.where(EdgeRow.edge_type == edge_type.value)
            return [_edge_from_row(r) for r in session.scalars(q).all()]

    def create_job(self) -> IndexJobRecord:
        job = IndexJobRecord(
            id=str(uuid.uuid4()),
            project_id=self.project_id,
            status=JobStatus.PENDING,
        )
        with self.session() as session:
            session.add(
                JobRow(
                    id=job.id,
                    project_id=job.project_id,
                    status=job.status.value,
                    progress=job.progress,
                    message=job.message,
                    error=job.error,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )
            session.commit()
        return job

    def update_job(self, job: IndexJobRecord) -> None:
        with self.session() as session:
            row = session.get(JobRow, job.id)
            if row is None:
                return
            row.status = job.status.value
            row.progress = job.progress
            row.message = job.message
            row.error = job.error
            row.updated_at = utcnow()
            session.commit()

    def get_job(self, job_id: str) -> IndexJobRecord | None:
        with self.session() as session:
            row = session.get(JobRow, job_id)
            if row is None:
                return None
            return IndexJobRecord(
                id=row.id,
                project_id=row.project_id,
                status=JobStatus(row.status),
                progress=row.progress,
                message=row.message,
                error=row.error,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def upsert_chunks(self, chunks: list[dict[str, Any]]) -> None:
        with self.session() as session:
            now = utcnow()
            for chunk in chunks:
                row = session.get(ChunkRow, chunk["id"])
                if row is None:
                    row = ChunkRow(id=chunk["id"], project_id=self.project_id)
                    session.add(row)
                row.node_id = chunk.get("node_id")
                row.source_path = chunk["source_path"]
                row.start_line = chunk["start_line"]
                row.end_line = chunk["end_line"]
                row.content = chunk["content"]
                row.embedding_json = chunk.get("embedding_json")
                row.metadata_json = _json_dumps(chunk.get("metadata", {}))
                row.updated_at = now
            session.commit()

    def search_chunks(self, query_embedding: list[float], limit: int = 8) -> list[dict[str, Any]]:
        import numpy as np

        with self.session() as session:
            rows = session.scalars(select(ChunkRow).where(ChunkRow.project_id == self.project_id)).all()
        if not rows:
            return []
        q = np.array(query_embedding, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)
        scored: list[tuple[float, ChunkRow]] = []
        for row in rows:
            if not row.embedding_json:
                continue
            emb = np.array(json.loads(row.embedding_json), dtype=np.float32)
            emb = emb / (np.linalg.norm(emb) + 1e-9)
            scored.append((float(np.dot(q, emb)), row))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, row in scored[:limit]:
            results.append(
                {
                    "score": score,
                    "source_path": row.source_path,
                    "start_line": int(row.start_line),
                    "end_line": int(row.end_line),
                    "content": row.content,
                    "node_id": row.node_id,
                    "metadata": _json_loads(row.metadata_json),
                }
            )
        return results

    def log_llm_request(self, token_estimate: int, redaction_count: int) -> None:
        with self.session() as session:
            session.add(
                LLMRequestRow(
                    id=str(uuid.uuid4()),
                    project_id=self.project_id,
                    token_estimate=token_estimate,
                    redaction_count=redaction_count,
                    created_at=utcnow(),
                )
            )
            session.commit()

    def list_all_nodes(self) -> list[NodeRecord]:
        with self.session() as session:
            rows = session.scalars(select(NodeRow).where(NodeRow.project_id == self.project_id)).all()
            return [_node_from_row(r) for r in rows]

    def load_index(self) -> GraphIndex:
        """The full graph, cached in-process until the database file changes."""
        path = db_path_for_project(self.project_id)
        key = str(path)
        sig = _db_signature(path)
        cached = _INDEX_CACHE.get(key)
        if sig is not None and cached is not None and cached[0] == sig:
            return cached[1]
        index = GraphIndex.build(self.list_all_nodes(), self.list_edges())
        if sig is not None:
            _INDEX_CACHE[key] = (sig, index)
        return index

    def indexed_paths(self) -> set[str]:
        """Relative paths of every indexed source file (the allowlist for source access)."""
        with self.session() as session:
            rows = session.scalars(
                select(NodeRow.source_path).where(
                    NodeRow.project_id == self.project_id,
                    NodeRow.node_type.in_([NodeType.MODULE.value, NodeType.MIGRATION.value]),
                )
            ).all()
        return {r for r in rows if r}

    def counts(self) -> dict[str, int]:
        with self.session() as session:
            nodes = session.scalar(
                select(func.count()).select_from(NodeRow).where(NodeRow.project_id == self.project_id)
            )
            edges = session.scalar(
                select(func.count()).select_from(EdgeRow).where(EdgeRow.project_id == self.project_id)
            )
        return {"nodes": int(nodes or 0), "edges": int(edges or 0)}

    def clear_graph(self, *, keep_chunks: bool = False) -> None:
        """Remove every node and edge (and chunks unless `keep_chunks`) so no stale rows survive."""
        with self.session() as session:
            session.query(EdgeRow).filter(EdgeRow.project_id == self.project_id).delete(
                synchronize_session=False
            )
            if not keep_chunks:
                session.query(ChunkRow).filter(ChunkRow.project_id == self.project_id).delete(
                    synchronize_session=False
                )
            session.query(NodeRow).filter(NodeRow.project_id == self.project_id).delete(
                synchronize_session=False
            )
            session.commit()

    def delete_chunks(self, paths: set[str]) -> None:
        if not paths:
            return
        with self.session() as session:
            session.query(ChunkRow).filter(
                ChunkRow.project_id == self.project_id, ChunkRow.source_path.in_(paths)
            ).delete(synchronize_session=False)
            session.commit()

    def build_graph_view(self, view: str, *, focus_node_id: str | None = None) -> GraphViewPayload:
        return build_view(self.load_index(), view, focus_node_id)


def _node_from_row(row: NodeRow) -> NodeRecord:
    return NodeRecord(
        id=row.id,
        project_id=row.project_id,
        node_type=NodeType(row.node_type),
        name=row.name,
        qualified_name=row.qualified_name,
        source_path=row.source_path,
        start_line=int(row.start_line) if row.start_line is not None else None,
        end_line=int(row.end_line) if row.end_line is not None else None,
        extractor=row.extractor,
        confidence=row.confidence,
        properties=_json_loads(row.properties_json),
        updated_at=row.updated_at,
    )


def _edge_from_row(row: EdgeRow) -> EdgeRecord:
    return EdgeRecord(
        id=row.id,
        project_id=row.project_id,
        edge_type=EdgeType(row.edge_type),
        source_id=row.source_id,
        target_id=row.target_id,
        source_path=row.source_path,
        start_line=int(row.start_line) if row.start_line is not None else None,
        end_line=int(row.end_line) if row.end_line is not None else None,
        extractor=row.extractor,
        confidence=row.confidence,
        properties=_json_loads(row.properties_json),
        updated_at=row.updated_at,
    )


def new_id() -> str:
    return str(uuid.uuid4())
