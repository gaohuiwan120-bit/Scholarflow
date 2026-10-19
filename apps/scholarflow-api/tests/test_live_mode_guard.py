"""Ensure live mode never silently succeeds via fixture without explicit degrade."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.workflow import run_research_workflow
from scholarflow_api.mcp.client import ScholarMcpError

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"


@pytest.fixture()
def tasks_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tasks"
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(root))
    return root


def test_live_mcp_failure_without_fallback_is_failed(tasks_tmpdir: Path) -> None:
    def _boom(*_a: Any, **_k: Any) -> tuple[list, list]:
        raise ScholarMcpError("simulated network failure")

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_boom):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("simulated github failure"),
        ):
            final = run_research_workflow(
                task_id="sf-live-fail-1",
                question="Blended RAG hybrid dense sparse vs Naive RAG",
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert "live MCP failed" in (paper.get("error") or "")
    # Must not look like fixture success
    assert paper.get("data_source") == "live_mcp"
    assert not final.get("papers")


def test_live_explicit_degrade_marks_partial(tasks_tmpdir: Path) -> None:
    def _boom(*_a: Any, **_k: Any) -> tuple[list, list]:
        raise ScholarMcpError("simulated network failure")

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_boom):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("simulated github failure"),
        ):
            final = run_research_workflow(
                task_id="sf-live-deg-1",
                question="Blended RAG hybrid dense sparse vs Naive RAG",
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=True,
                persist_artifacts=True,
            )
    assert final["overall_status"] == "partial_succeeded"
    assert final.get("effective_data_mode") == "mixed_degraded"
    assert final.get("degradation_events")
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "succeeded"
    assert paper.get("data_source") == "fixture_degraded_from_live"
    assert final.get("papers")


def test_live_offtopic_fixture_fallback_rejected(tasks_tmpdir: Path) -> None:
    """Compressed-sensing query must not accept RAG/langchain fixture as success."""

    def _boom(*_a: Any, **_k: Any) -> tuple[list, list]:
        raise ScholarMcpError("simulated network failure")

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_boom):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("simulated github failure"),
        ):
            final = run_research_workflow(
                task_id="sf-live-cs-reject",
                question="基于深度学习的图像压缩感知重建",
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=True,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert "off-topic" in (paper.get("error") or "").lower() or "rejected" in (
        paper.get("error") or ""
    ).lower()
    assert not final.get("papers")


def test_fixture_experiment_uses_upstream_ids(tasks_tmpdir: Path) -> None:
    final = run_research_workflow(
        task_id="sf-up-1",
        question="Blended RAG upstream check",
        workflow_mode="research_orchestration",
        artifacts_dir=str(ARTIFACTS),
        data_mode="fixture",
        persist_artifacts=False,
    )
    exp = final.get("experiment") or {}
    assert exp.get("upstream_paper_ids")
    assert exp.get("upstream_repo_ids")
    assert all(exp["upstream_paper_ids"])
