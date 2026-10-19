"""定向复验：成功路径(mock)与失败/429 降级路径分开报告。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.evidence_gate import (
    extract_paper_query,
    extract_repo_search_query,
    filter_relevant_papers,
)
from scholarflow_api.graph.workflow import run_research_workflow
from scholarflow_api.mcp.client import ScholarMcpError

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"
CS_Q = "基于深度学习的图像压缩感知重建"


@pytest.fixture()
def tasks_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tasks"
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(root))
    return root


def test_query_cleaning_cs_topic() -> None:
    paper_q = extract_paper_query(CS_Q)
    repo_q = extract_repo_search_query(CS_Q)
    assert "compressed sensing" in paper_q.lower() or "compressive sensing" in paper_q.lower()
    assert "检索" not in paper_q
    assert "langchain" not in repo_q.lower()
    assert "rag" not in repo_q.lower()
    assert "compressive sensing" in repo_q.lower() or "ista-net" in repo_q.lower()


def test_path_b_arxiv_429_rejects_offtopic_fixture(tasks_tmpdir: Path) -> None:
    """429 / 检索失败时不得混入 RAG fixture 伪装成功。"""

    def _boom(*_a: Any, **_k: Any) -> tuple[list, list]:
        raise ScholarMcpError(
            "search_academic_papers failed: arXiv HTTP 429 Too Many Requests "
            "(Retry-After='30') for query='deep learning image compressed sensing'"
        )

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_boom):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("No topic-matched GitHub repository"),
        ):
            final = run_research_workflow(
                task_id="sf-path-b-429",
                question=CS_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=True,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert "429" in (paper.get("error") or "") or "off-topic" in (paper.get("error") or "")
    assert not final.get("papers")
    assert (final.get("artifact_summary") or {}).get("artifact_count") in {None, 0}
    # experimental downstream must not succeed on empty evidence
    exp = next(s for s in final["subtasks"] if s["role"] == "experiment_design")
    assert exp["status"] == "failed"


def test_path_b_irrelevant_live_papers_rejected(tasks_tmpdir: Path) -> None:
    junk = [
        {
            "evidence_id": "paper-junk",
            "title": "GitHub Emoji Reactions and AI Agent Challenges",
            "authors": ["X"],
            "year": 2024,
            "venue": "arXiv",
            "identifier": "2401.99999",
            "source_url": "https://arxiv.org/abs/2401.99999",
            "abstract": "We study GitHub applications and Stack Overflow developer collaboration.",
            "research_problem": "sociology",
            "methodology": "",
            "datasets": [],
            "metrics": [],
            "key_findings": [],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        }
    ]
    accepted, rejected = filter_relevant_papers(CS_Q, junk)
    assert not accepted and rejected

    with patch(
        "scholarflow_api.graph.nodes.fetch_papers_via_mcp",
        return_value=(junk, [{"tool": "search_academic_papers", "args": {"query": "x"}}]),
    ):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("irrelevant repos only"),
        ):
            final = run_research_workflow(
                task_id="sf-path-b-irrel",
                question=CS_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    assert not final.get("papers")
    reviews = final.get("reviews") or []
    assert not any(r.get("status") == "supported" for r in reviews)


def test_path_a_mock_relevant_live_succeeds(tasks_tmpdir: Path) -> None:
    """成功路径用可控相关证据验证（≠ 真实外网成功）。"""
    good = [
        {
            "evidence_id": "paper-cs-1",
            "title": "Deep Networks for Image Compressed Sensing Reconstruction",
            "authors": ["A"],
            "year": 2020,
            "venue": "CVPR",
            "identifier": "2001.00001",
            "source_url": "https://arxiv.org/abs/2001.00001",
            "abstract": "We propose deep learning for compressive sensing image reconstruction.",
            "research_problem": "image compressed sensing",
            "methodology": "CNN",
            "datasets": ["Set11"],
            "metrics": ["PSNR"],
            "key_findings": ["improves PSNR"],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        }
    ]
    repo = {
        "evidence_id": "repo-cs-1",
        "repository": "jianzhangcs/ISTA-Net",
        "source_url": "https://github.com/jianzhangcs/ISTA-Net",
        "description": "ISTA-Net compressed sensing reconstruction",
        "language": "Python",
        "framework": ["PyTorch"],
        "architecture_summary": "deep unfolding for image compressed sensing",
        "key_modules": ["models"],
        "installation_summary": "pip",
        "reproducibility_notes": [],
        "limitations": [],
        "default_branch": "master",
        "root_listing": [],
        "verification_status": "verified",
        "fetched_at": "2024-01-01T00:00:00Z",
    }

    captured: dict[str, Any] = {}

    def _papers(query: str, max_results: int = 12) -> tuple[list, list]:
        captured["paper_query"] = query
        return good, [{"tool": "search_academic_papers", "args": {"query": query, "max_results": max_results}}]

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_papers):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            return_value=(repo, [], {"selected": "jianzhangcs/ISTA-Net", "method": "mock"}),
        ):
            final = run_research_workflow(
                task_id="sf-path-a-mock",
                question=CS_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert captured["paper_query"] == "deep learning image compressed sensing"
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    assert final.get("papers") and final["papers"][0]["evidence_id"] == "paper-cs-1"
    assert final.get("repositories")
    exp = final.get("experiment") or {}
    assert "paper-cs-1" in (exp.get("upstream_paper_ids") or [])
    assert "Naive RAG" not in str(exp.get("hypotheses"))
    reviews = final.get("reviews") or []
    assert any(r.get("status") == "supported" for r in reviews)
    assert all("Hybrid retrieval improves over Naive RAG" != r.get("claim") for r in reviews)
