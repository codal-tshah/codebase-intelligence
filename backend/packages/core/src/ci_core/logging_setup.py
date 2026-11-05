"""Logging with request/job correlation ids (plain text locally, JSON with CI_LOG_JSON=1)."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("ci_request_id", default=None)
_CONFIGURED = False


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id.get(),
        }
        for key in ("project_id", "job_id", "phase"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


class _Plain(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = request_id.get()
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        base += f" [{rid}]" if rid else ""
        return base + ("\n" + self.formatException(record.exc_info) if record.exc_info else "")


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    """Idempotent. Only touches the `ci_*` loggers' parent handler, never the root logger of the host."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Json() if as_json else _Plain())
    for name in ("ci_api", "ci_core", "ci_indexer", "ci_ai", "ci_mcp", "ci_cli"):
        log = logging.getLogger(name)
        log.setLevel(level)
        log.addHandler(handler)
        log.propagate = False
    _CONFIGURED = True
