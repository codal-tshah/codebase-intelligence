from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores naive datetimes)."""
    return datetime.now(UTC).replace(tzinfo=None)


class NodeType(StrEnum):
    PROJECT = "Project"
    PACKAGE = "Package"
    MODULE = "Module"
    CLASS = "Class"
    FUNCTION = "Function"
    ENDPOINT = "Endpoint"
    MIDDLEWARE = "Middleware"
    COMPONENT = "Component"
    MODEL = "Model"
    TABLE = "Table"
    FIELD = "Field"
    MIGRATION = "Migration"
    EXTERNAL_SERVICE = "ExternalService"
    CONFIG_REF = "ConfigRef"


class EdgeType(StrEnum):
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    ROUTES_TO = "ROUTES_TO"
    HANDLES = "HANDLES"
    READS_MODEL = "READS_MODEL"
    WRITES_MODEL = "WRITES_MODEL"
    FK_TO = "FK_TO"
    QUERIES = "QUERIES"
    DEPENDS_ON = "DEPENDS_ON"
    SUBSCRIBES = "SUBSCRIBES"
    MIDDLEWARE = "MIDDLEWARE"
    RENDERS = "RENDERS"  # UI component renders another component
    HTTP_CALLS = "HTTP_CALLS"  # code issues an HTTP request handled by an endpoint
    INJECTS = "INJECTS"  # dependency injection (FastAPI Depends, Nest providers)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Provenance(BaseModel):
    source_path: str
    start_line: int = 1
    end_line: int = 1
    extractor: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class NodeRecord(BaseModel):
    id: str
    project_id: str
    node_type: NodeType
    name: str
    qualified_name: str | None = None
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    extractor: str
    confidence: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utcnow)


class EdgeRecord(BaseModel):
    id: str
    project_id: str
    edge_type: EdgeType
    source_id: str
    target_id: str
    source_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    extractor: str
    confidence: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utcnow)


class ProjectRecord(BaseModel):
    id: str
    name: str
    root_path: str
    git_url: str | None = None
    commit_sha: str | None = None
    framework: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Citation(BaseModel):
    path: str
    start_line: int
    end_line: int
    node_id: str | None = None
    view: str | None = None
    highlight_path: list[str] = Field(default_factory=list)


class GraphNodeView(BaseModel):
    id: str
    label: str
    node_type: str
    source_path: str | None = None
    layer: str | None = None
    complexity: str | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeView(BaseModel):
    id: str
    source: str
    target: str
    edge_type: str
    confidence: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphViewPayload(BaseModel):
    view: str
    nodes: list[GraphNodeView]
    edges: list[GraphEdgeView]
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexJobRecord(BaseModel):
    id: str
    project_id: str
    status: JobStatus
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
