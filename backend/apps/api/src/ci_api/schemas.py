"""Request bodies shared by the API routers."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from ci_api.deps import GITHUB_URL


class ChatMessage(BaseModel):
    role: str
    content: str


class CreateProjectBody(BaseModel):
    path: str | None = None
    git_url: str | None = Field(default=None, description="GitHub repository URL (private repos need CI_GITHUB_TOKEN)")

    @field_validator("git_url")
    @classmethod
    def validate_git_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not GITHUB_URL.match(v):
            raise ValueError("Must be a valid GitHub repository URL (https://github.com/owner/repo)")
        return v


class AnalyzeBody(CreateProjectBody):
    """Create project and run a full index (ingest + graph + embeddings)."""


class RenameBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class SettingsBody(BaseModel):
    """Per-project settings stored in the data directory (never written into the repository)."""

    ignore: list[str] | None = Field(
        default=None, max_length=200, description="gitignore-style patterns, one per entry"
    )
    auto_refresh: bool | None = Field(
        default=None, description="Re-index changed files automatically when git HEAD moves"
    )


class SavedViewBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    state: dict[str, str] = Field(default_factory=dict, description="Same keys as the dashboard URL hash: v, n, f, e")


class ImpactBody(BaseModel):
    """Blast radius of a change. With no files/nodes, the working tree's changed files are used."""

    files: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    base: str | None = Field(
        default=None, description="Git ref to diff against (e.g. origin/main); ignored if files set"
    )
    depth: int = Field(default=3, ge=1, le=6)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    focus_node_id: str | None = None
    conversation_history: list[ChatMessage] = Field(default_factory=list)
