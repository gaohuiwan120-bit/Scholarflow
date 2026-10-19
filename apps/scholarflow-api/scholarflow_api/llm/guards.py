"""Redaction and safe error formatting — never leak API keys."""

from __future__ import annotations

import re

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{8,}"),
)


def redact_secrets(text: str) -> str:
    """Strip likely secret material from loggable / reportable strings."""
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def safe_exc_message(exc: BaseException, *, limit: int = 400) -> str:
    msg = redact_secrets(f"{type(exc).__name__}: {exc}")
    if len(msg) > limit:
        return msg[: limit - 3] + "..."
    return msg
