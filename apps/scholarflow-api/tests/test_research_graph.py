"""Phase-2 LangGraph workflow tests (deterministic fixture mode)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.workflow import build_research_graph, run_research_workflow

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"


@pytest.fixture(scope="module")
def artifacts_dir() -> str:
    assert ARTIFACTS.is_dir()
    return str(ARTIFACTS)


def test_graph_compiles() -> None:
    g = build_research_graph()
    assert g is not None


def test_orchestration_produces_nine_artifacts(artifacts_dir: str) -> None:
    final = run_research_workflow(
        task_id="t-orch-1",
        question="Blended RAG hybrid dense sparse vs Naive RAG",
        workflow_mode="research_orchestration",
        artifacts_dir=artifacts_dir,
        data_mode="fixture",
        simulate_work_seconds=0.0,
        persist_artifacts=False,
    )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    summary = final.get("artifact_summary") or {}
    assert summary.get("artifact_count") == 9
    assert not summary.get("missing")
    assert final.get("papers")
    assert final.get("repositories")
    assert final.get("experiment")
    roles = {s["role"] for s in final.get("subtasks") or []}
    assert "paper_research" in roles
    assert "repository_analysis" in roles
    assert "experiment_design" in roles
    assert "review" in roles
    assert "assemble" in roles


def test_paper_and_repo_parallel_overlap(artifacts_dir: str) -> None:
    """Prove paper/repo wall-clock intervals overlap under simulated work."""
    final = run_research_workflow(
        task_id="t-par-1",
        question="RAG survey",
        workflow_mode="research_orchestration",
        artifacts_dir=artifacts_dir,
        data_mode="fixture",
        simulate_work_seconds=0.45,
        persist_artifacts=False,
    )
    subs = {s["role"]: s for s in final.get("subtasks") or []}
    paper = subs["paper_research"]
    repo = subs["repository_analysis"]
    assert paper["started_at"] is not None and paper["ended_at"] is not None
    assert repo["started_at"] is not None and repo["ended_at"] is not None
    # Intervals [ps, pe] and [rs, re] overlap iff ps < re and rs < pe
    assert paper["started_at"] < repo["ended_at"]
    assert repo["started_at"] < paper["ended_at"]
    # Also check event stream
    kinds = [e.get("kind") for e in final.get("events") or []]
    assert "paper_started" in kinds and "repo_started" in kinds


def test_experiment_consumes_upstream(artifacts_dir: str) -> None:
    final = run_research_workflow(
        task_id="t-exp-1",
        question="RAG experiment design",
        workflow_mode="experiment_design",
        artifacts_dir=artifacts_dir,
        data_mode="fixture",
        persist_artifacts=False,
    )
    exp = final.get("experiment") or {}
    assert exp.get("upstream_paper_ids")
    assert exp.get("upstream_repo_ids")
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}


def test_review_fail_marks_failed(artifacts_dir: str) -> None:
    final = run_research_workflow(
        task_id="t-fail-1",
        question="force fail review",
        workflow_mode="research_orchestration",
        artifacts_dir=artifacts_dir,
        data_mode="fixture",
        force_fail_review=True,
        persist_artifacts=False,
    )
    assert final["review_decision"] == "fail"
    assert final["overall_status"] == "failed"
    assemble = next(s for s in final["subtasks"] if s["role"] == "assemble")
    assert assemble["status"] == "skipped"


def test_paper_failure_not_success(artifacts_dir: str) -> None:
    final = run_research_workflow(
        task_id="t-fail-paper",
        question="force fail paper",
        workflow_mode="research_orchestration",
        artifacts_dir=artifacts_dir,
        data_mode="fixture",
        force_fail_paper=True,
        persist_artifacts=False,
    )
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert final["overall_status"] == "failed"


def test_single_stream_workflows(artifacts_dir: str) -> None:
    paper = run_research_workflow(
        task_id="t-paper",
        question="papers only",
        workflow_mode="paper_research",
        artifacts_dir=artifacts_dir,
        persist_artifacts=False,
    )
    assert paper.get("papers")
    repo = run_research_workflow(
        task_id="t-repo",
        question="repos only",
        workflow_mode="repository_analysis",
        artifacts_dir=artifacts_dir,
        persist_artifacts=False,
    )
    assert repo.get("repositories")
