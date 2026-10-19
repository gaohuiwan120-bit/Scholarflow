"""API request/response models and task state (Phase 1 + Phase 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial_succeeded = "partial_succeeded"
    failed = "failed"
    timed_out = "timed_out"


class TaskKind(str, Enum):
    rag_query = "rag_query"
    research_orchestration = "research_orchestration"
    paper_research = "paper_research"
    repository_analysis = "repository_analysis"
    experiment_design = "experiment_design"


class TaskCreateRequest(BaseModel):
    kind: TaskKind = TaskKind.rag_query
    question: str = Field(..., min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    ensure_index: bool = True
    force_reindex: bool = False
    verified_only: bool = False
    # Phase 2
    data_mode: Literal["fixture", "live"] = "fixture"
    allow_fixture_fallback: bool = Field(
        default=False,
        description="If live MCP fails, optionally degrade to fixture (marks partial_succeeded)",
    )
    force_fail_review: bool = False
    force_fail_paper: bool = False
    simulate_work_seconds: float = Field(default=0.0, ge=0.0, le=30.0)
    persist_artifacts: bool = True
    # Phase 4
    enable_mcp_fallback: bool = Field(
        default=False,
        description="When true with data_mode=live, RAG auto-calls MCP if evidence insufficient",
    )
    rerank_model: str | None = Field(
        default=None,
        description="Optional override: hybrid-score | cross-encoder | stub-cross-encoder",
    )


class EvidenceItem(BaseModel):
    evidence_id: str | None = None
    chunk_id: str | None = None
    kind: str | None = None
    title: str | None = None
    text: str | None = None
    source_url: str | None = None
    verification_status: str | None = None
    score: float | None = None


class ArtifactRef(BaseModel):
    label: str
    path: str
    kind: Literal["artifacts_dir", "rag_index", "file"] = "artifacts_dir"


class RagResultPayload(BaseModel):
    question: str
    answer: str
    confidence: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    need_mcp_fallback: bool = False
    retrieval: dict[str, Any] = Field(default_factory=dict)


class SubtaskStatusItem(BaseModel):
    subtask_id: str
    role: str
    status: str
    depends_on: list[str] = Field(default_factory=list)
    started_at: float | None = None
    ended_at: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    summary: str | None = None
    data_source: str | None = None


class ResearchWorkflowPayload(BaseModel):
    workflow_mode: str
    overall_status: str
    review_decision: str | None = None
    research_plan: dict[str, Any] | None = None
    papers: list[dict[str, Any]] = Field(default_factory=list)
    repositories: list[dict[str, Any]] = Field(default_factory=list)
    experiment: dict[str, Any] = Field(default_factory=dict)
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    subtasks: list[SubtaskStatusItem] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    mcp_calls: list[dict[str, Any]] = Field(default_factory=list)
    degradation_events: list[dict[str, Any]] = Field(default_factory=list)
    artifact_summary: dict[str, Any] | None = None
    artifact_manifest: dict[str, Any] | None = None
    report_excerpt: str | None = None
    data_mode: str = "fixture"
    effective_data_mode: str | None = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatus
    kind: TaskKind
    created_at: datetime
    message: str = "Task accepted"


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    kind: TaskKind
    question: str
    created_at: datetime
    updated_at: datetime
    runtime: str
    error: str | None = None
    progress: str | None = None
    subtasks: list[SubtaskStatusItem] = Field(default_factory=list)


class TaskResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    kind: TaskKind
    question: str
    runtime: str
    result: RagResultPayload | None = None
    research: ResearchWorkflowPayload | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    index_info: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    duration_ms: int | None = None
    subtasks: list[SubtaskStatusItem] = Field(default_factory=list)


class SandboxExecuteRequest(BaseModel):
    task_id: str = Field(..., min_length=2, max_length=80)
    code: str = Field(..., min_length=1, max_length=200_000)
    timeout_seconds: float = Field(default=8.0, ge=0.5, le=60.0)
    memory_mb: int = Field(default=256, ge=64, le=1024)
    max_output_bytes: int = Field(default=64_000, ge=1024, le=2_000_000)
    allow_network: bool = False
    prefer_docker: bool = True
    filename: str = "main.py"


class SandboxExecuteResponse(BaseModel):
    task_id: str
    status: str
    backend: str
    exit_code: int | None = None
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    error_summary: str | None = None
    work_dir: str | None = None
    limits: dict[str, Any] = Field(default_factory=dict)
    security_notes: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "scholarflow-api"
    version: str
    runtime: str
    runtimes: list[str] = Field(default_factory=list)
    harness_importable: bool
    artifacts_dir_exists: bool
    langgraph_available: bool = False
    sandbox_available: bool = False
    sandbox_docker: bool = False
    # Phase 8.0 — presence only; never expose API key material
    llm_configured: bool = False
    llm_model: str | None = None
    llm_provider: str | None = None
