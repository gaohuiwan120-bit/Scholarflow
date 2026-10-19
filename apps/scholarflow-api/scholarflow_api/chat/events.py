"""SSE event schemas and formatting (Phase 8.3)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from scholarflow_api.llm.guards import redact_secrets
from scholarflow_api.models import utc_now

SseEventType = Literal[
    "turn_start",
    "token",
    "tool_start",
    "tool_end",
    "workflow_progress",
    "error",
    "done",
]

TurnFinalStatus = Literal[
    "completed",
    "max_iterations",
    "error",
    "cancelled",
    "timeout",
]


class SseEventBase(BaseModel):
    event: SseEventType
    turn_id: str
    conversation_id: str
    ts: datetime = Field(default_factory=utc_now)


class TurnStartEvent(SseEventBase):
    event: Literal["turn_start"] = "turn_start"
    user_message_id: str
    model: str | None = None


class TokenEvent(SseEventBase):
    event: Literal["token"] = "token"
    text: str
    iteration: int = 1


class ToolStartEvent(SseEventBase):
    event: Literal["tool_start"] = "tool_start"
    tool_name: str
    tool_call_id: str
    arguments_summary: dict[str, Any] = Field(default_factory=dict)


class ToolEndEvent(SseEventBase):
    event: Literal["tool_end"] = "tool_end"
    tool_name: str
    tool_call_id: str
    status: Literal["succeeded", "failed"]
    duration_ms: int | None = None
    result_summary: str | None = None
    error: str | None = None


class WorkflowProgressEvent(SseEventBase):
    event: Literal["workflow_progress"] = "workflow_progress"
    message: str
    task_id: str | None = None
    overall_status: str | None = None
    # No fabricated percent fields


class ErrorEvent(SseEventBase):
    event: Literal["error"] = "error"
    message: str
    stage: str | None = None


class DoneEvent(SseEventBase):
    event: Literal["done"] = "done"
    status: TurnFinalStatus
    assistant_message_id: str | None = None
    related_task_id: str | None = None
    iterations: int = 0
    latency_ms: float | None = None
    error: str | None = None


def summarize_args(args: dict[str, Any], *, limit: int = 200) -> dict[str, Any]:
    """Redact and truncate tool args for safe SSE emission."""
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        key = str(k).lower()
        if any(s in key for s in ("key", "token", "secret", "password", "auth")):
            out[k] = "[REDACTED]"
            continue
        if isinstance(v, str):
            s = redact_secrets(v)
            out[k] = s if len(s) <= limit else s[: limit - 3] + "..."
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
        else:
            s = redact_secrets(json.dumps(v, ensure_ascii=False, default=str))
            out[k] = s if len(s) <= limit else s[: limit - 3] + "..."
    return out


def format_sse(event: SseEventBase) -> str:
    """Encode one SSE message: event + data JSON lines."""
    payload = event.model_dump(mode="json")
    # Belt-and-suspenders redaction on serialized form
    data = redact_secrets(json.dumps(payload, ensure_ascii=False, default=str))
    return f"event: {event.event}\ndata: {data}\n\n"
