"""Pydantic schemas for conversations and messages (Phase 8.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from scholarflow_api.models import utc_now

MessageRole = Literal["user", "assistant", "system", "tool"]


class ToolCallTraceItem(BaseModel):
    """Reserved for Phase 8.2+ — do not fabricate in 8.1."""

    tool_name: str
    tool_call_id: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result_summary: str | None = None


class EvidenceRef(BaseModel):
    """Lightweight evidence pointer reserved for chat answers."""

    evidence_id: str | None = None
    source_url: str | None = None
    title: str | None = None
    kind: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    kind_hint: str | None = None
    relevance_score: float | None = None


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreateRequest(BaseModel):
    """Persist-only message append for Phase 8.1 (no LLM / SSE)."""

    role: MessageRole
    content: str = Field(..., min_length=1, max_length=100_000)
    related_task_id: str | None = Field(default=None, max_length=64)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    tool_call_trace: list[ToolCallTraceItem] = Field(
        default_factory=list,
        description="Optional; leave empty unless a real tool call occurred",
    )

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("content must not be empty")
        return text


class ChatMessage(BaseModel):
    message_id: str
    conversation_id: str
    role: MessageRole
    content: str
    created_at: datetime
    tool_call_trace: list[ToolCallTraceItem] = Field(default_factory=list)
    related_task_id: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class ConversationMeta(BaseModel):
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationDetail(ConversationMeta):
    """Same as meta for 8.1; kept distinct for future expansion."""


class ConversationListResponse(BaseModel):
    conversations: list[ConversationMeta]
    total: int


class MessageListResponse(BaseModel):
    conversation_id: str
    messages: list[ChatMessage]
    total: int


class ConversationTasksResponse(BaseModel):
    conversation_id: str
    related_task_ids: list[str]


class ConversationCreateResponse(BaseModel):
    conversation: ConversationMeta
    message: str = "Conversation created"


class AgentTurnRequest(BaseModel):
    """Phase 8.2: run one agent turn (LLM + optional tools). No SSE yet."""

    content: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("content must not be empty")
        return text


class AgentTurnResponse(BaseModel):
    conversation_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage | None = None
    tool_call_trace: list[ToolCallTraceItem] = Field(default_factory=list)
    related_task_id: str | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    status: Literal[
        "completed", "max_iterations", "error", "cancelled", "timeout"
    ] = "completed"
    error: str | None = None
    model: str | None = None
    iterations: int = 0
    latency_ms: float | None = None
    turn_id: str | None = None


class TurnCancelResponse(BaseModel):
    turn_id: str
    cancelled: bool
    message: str


def new_conversation_title(title: str | None) -> str:
    if title and title.strip():
        return title.strip()[:200]
    return f"Conversation {utc_now().strftime('%Y-%m-%d %H:%M UTC')}"
