from __future__ import annotations

import os
import re


def allow_llm() -> bool:
    return os.environ.get("ALLOW_LLM", "").lower() in ("1", "true", "yes")


def redact_secrets(text: str) -> tuple[str, int]:
    patterns = [
        (r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]+['\"]", "[REDACTED_SECRET]"),
        (r"AKIA[0-9A-Z]{16}", "[REDACTED_AWS_KEY]"),
        (r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----", "[REDACTED_KEY]"),
    ]
    redactions = 0
    out = text
    for pattern, repl in patterns:
        new_out, count = re.subn(pattern, repl, out)
        if count:
            redactions += count
            out = new_out
    return out, redactions


def sanitize_for_llm(text: str) -> tuple[str, int]:
    redacted, count = redact_secrets(text)
    return redacted, count
