"""All environment-driven configuration in one validated place.

Read with :func:`get_settings` (not cached, so tests and long-running processes see env changes).
See ``.env.example`` at the repo root for every variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_TRUE = {"1", "true", "yes", "on"}
_DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"]


class SettingsError(ValueError):
    """Invalid configuration (raised at startup so misconfiguration fails fast)."""


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    mode: str = "local"  # local: trusted single user | server: API key + path allowlist enforced
    api_key: str | None = None
    project_roots: tuple[Path, ...] = ()
    cors_origins: tuple[str, ...] = tuple(_DEFAULT_ORIGINS)
    analyzers: tuple[str, ...] = ()
    allow_llm: bool = False
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_api_base: str | None = None
    log_level: str = "INFO"
    log_json: bool = False
    extras: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def llm_enabled(self) -> bool:
        return self.allow_llm and bool(self.llm_api_key or self.llm_api_base)

    def path_allowed(self, path: Path) -> bool:
        """In server mode only paths under CI_PROJECT_ROOTS may be indexed."""
        if self.mode != "server":
            return True
        resolved = path.expanduser().resolve()
        return any(resolved == root or root in resolved.parents for root in self.project_roots)


def get_settings() -> Settings:
    mode = os.environ.get("CI_MODE", "local").strip().lower()
    if mode not in ("local", "server"):
        raise SettingsError(f"CI_MODE must be 'local' or 'server', got {mode!r}")
    data_dir = Path(os.environ.get("CI_DATA_DIR") or Path.home() / ".codebase-intelligence").expanduser().resolve()
    roots = tuple(Path(p).expanduser().resolve() for p in _csv("CI_PROJECT_ROOTS"))
    api_key = os.environ.get("CI_API_KEY") or None
    if mode == "server" and not api_key:
        raise SettingsError("CI_MODE=server requires CI_API_KEY")
    if mode == "server" and not roots:
        raise SettingsError("CI_MODE=server requires CI_PROJECT_ROOTS (comma-separated directories that may be indexed)")
    level = os.environ.get("CI_LOG_LEVEL", "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise SettingsError(f"CI_LOG_LEVEL must be DEBUG|INFO|WARNING|ERROR, got {level!r}")
    return Settings(
        data_dir=data_dir,
        mode=mode,
        api_key=api_key,
        project_roots=roots,
        cors_origins=tuple(_csv("CI_CORS_ORIGINS")) or tuple(_DEFAULT_ORIGINS),
        analyzers=tuple(_csv("CI_ANALYZERS")),
        allow_llm=os.environ.get("ALLOW_LLM", "").lower() in _TRUE,
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        llm_api_key=os.environ.get("LLM_API_KEY") or None,
        llm_api_base=os.environ.get("LLM_API_BASE") or None,
        log_level=level,
        log_json=os.environ.get("CI_LOG_JSON", "").lower() in _TRUE,
    )
