"""LLM provider configuration (LiteLLM: hosted APIs or a local OpenAI-compatible server)."""

from __future__ import annotations

from typing import Any

from ci_core.settings import get_settings

DEFAULT_MODEL = "gpt-4o-mini"


def llm_enabled() -> bool:
    """Remote LLM calls need an explicit opt-in (ALLOW_LLM) and a key or a local base URL."""
    return get_settings().llm_enabled


def llm_kwargs() -> dict[str, Any]:
    """Arguments for `litellm.(a)completion` (see `.env.example`: LLM_MODEL, LLM_API_KEY, LLM_API_BASE)."""
    s = get_settings()
    kwargs: dict[str, Any] = {"model": s.llm_model}
    if s.llm_api_key:
        kwargs["api_key"] = s.llm_api_key
    if s.llm_api_base:
        kwargs["api_base"] = s.llm_api_base
    return kwargs
