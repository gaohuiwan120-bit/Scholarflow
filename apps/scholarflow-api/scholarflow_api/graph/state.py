"""LangGraph shared state for ScholarFlow research orchestration."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


WorkflowMode = Literal[
    "paper_research",
    "repository_analysis",
    "experiment_design",
    "research_orchestration",
]


class SubtaskRecord(TypedDict, total=False):
    subtask_id: str
    role: str
    status: str  # queued|running|succeeded|failed|skipped
    depends_on: list[str]
    started_at: float | None
    ended_at: float | None
    duration_ms: int | None
    error: str | None
    summary: str | None
    data_source: str | None  # fixture|live_mcp|none


class ResearchState(TypedDict, total=False):
    """Shared graph state.

    ``subtasks`` uses operator.add so parallel paper/repo nodes can each append
    their own record without clobbering the sibling update.
    """

    task_id: str
    question: str
    workflow_mode: WorkflowMode
    data_mode: str  # fixture | live
    allow_fixture_fallback: bool
    force_fail_review: bool
    force_fail_paper: bool
    simulate_work_seconds: float
    artifacts_dir: str
    persist_artifacts: bool

    research_plan: dict[str, Any]
    papers: list[dict[str, Any]]
    repositories: list[dict[str, Any]]
    experiment: dict[str, Any]
    reviews: list[dict[str, Any]]
    artifact_contents: dict[str, str]
    artifact_summary: dict[str, Any]
    artifact_manifest: dict[str, Any]

    subtasks: Annotated[list[SubtaskRecord], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
    mcp_calls: Annotated[list[dict[str, Any]], operator.add]
    degradation_events: Annotated[list[dict[str, Any]], operator.add]
    review_decision: str  # pass|fail|needs_supplement
    overall_status: str  # succeeded|partial_succeeded|failed
    error: str | None
    report_excerpt: str | None
    effective_data_mode: str  # fixture | live | mixed_degraded
