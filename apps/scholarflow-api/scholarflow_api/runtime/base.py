"""Runtime interface for Phase 1 RAG and Phase 2 LangGraph orchestrator."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from pydantic import BaseModel, Field

from scholarflow_api.models import (
    ArtifactRef,
    RagResultPayload,
    ResearchWorkflowPayload,
    TaskKind,
)


ProgressCallback = Callable[[str], None]


class RuntimeRequest(BaseModel):
    """Normalized input passed to any TaskRuntime implementation."""

    task_id: str
    kind: TaskKind
    question: str
    top_k: int = 5
    ensure_index: bool = True
    force_reindex: bool = False
    verified_only: bool = False
    artifacts_dir: str | None = None
    # Phase-2 research options
    data_mode: str = "fixture"  # fixture | live
    allow_fixture_fallback: bool = False
    force_fail_review: bool = False
    force_fail_paper: bool = False
    simulate_work_seconds: float = 0.0
    persist_artifacts: bool = True
    # Phase 4
    enable_mcp_fallback: bool = False
    rerank_model: str | None = None


class RuntimeResult(BaseModel):
    """Normalized output — both RAG and research runtimes return this shape."""

    payload: RagResultPayload | None = None
    research: ResearchWorkflowPayload | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    index_info: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    overall_status: str = "succeeded"


class TaskRuntime(ABC):
    """Pluggable execution backend."""

    name: str

    @abstractmethod
    def run(
        self,
        request: RuntimeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RuntimeResult:
        raise NotImplementedError
