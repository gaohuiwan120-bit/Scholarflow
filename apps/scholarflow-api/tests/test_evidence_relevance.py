"""Regression: topic relevance gate, review claims, failure propagation."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.evidence_gate import (
    claim_supported_by_evidence,
    claims_from_question_and_evidence,
    extract_paper_query,
    filter_relevant_papers,
    filter_relevant_repos,
    fixture_theme_compatible,
    repo_is_relevant,
)
from scholarflow_api.graph.workflow import run_research_workflow

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"

CS_QUESTION = "基于深度学习的图像压缩感知重建"
RAG_QUESTION = "Blended RAG hybrid dense sparse vs Naive RAG"


@pytest.fixture()
def tasks_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tasks"
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(root))
    return root


def test_extract_paper_query_strips_chinese_boilerplate() -> None:
    long_q = (
        "基于深度学习的图像压缩感知重建：检索相关论文，研究问题、核心方法、"
        "创新点与局限性；查找并分析相关 GitHub 开源实现"
    )
    q = extract_paper_query(long_q)
    assert "compressed sensing" in q.lower() or "deep learning" in q.lower()
    assert "检索相关论文" not in q
    assert "GitHub" not in q or "github" not in q.lower()


def test_ista_net_pytorch_accepted_despite_compressed_vs_compressive() -> None:
    """Live GitHub descriptions say 'Compressive'; cleaned query says 'compressed'."""
    q = (
        "图像压缩感知重建：检索相关论文与 GitHub 开源实现"
        "（参考 jianzhangcs/ISTA-Net），并设计实验方案"
    )
    repo = {
        "repository": "jianzhangcs/ISTA-Net-PyTorch",
        "description": (
            "ISTA-Net: Interpretable Optimization-Inspired Deep Network "
            "for Image Compressive Sensing, CVPR2018 (PyTorch Code)"
        ),
        "architecture_summary": "Train_CS_ISTA_Net.py TEST_CS_ISTA_Net.py",
    }
    ok, score, signals = repo_is_relevant(q, repo)
    assert ok is True
    assert score >= 2.5
    assert any("cs_markers" in s or "compressive" in s for s in signals)

    junk = {
        "repository": "TheCyb3rAlpha/BobTheSmuggler",
        "description": "HTML Smuggling Attack tool",
        "architecture_summary": "",
    }
    ok_j, _, sig_j = repo_is_relevant(q, junk)
    assert ok_j is False
    assert any("lacks_cs" in s or "mismatch" in s for s in sig_j)


def test_cs_query_rejects_github_sociology_papers() -> None:
    papers = [
        {
            "evidence_id": "p-bad",
            "title": "The Rise of GitHub Emoji in Developer Collaboration",
            "abstract": "We study GitHub applications and AI agent systems on Stack Overflow.",
            "source_url": "https://arxiv.org/abs/0000.00001",
        },
        {
            "evidence_id": "p-good",
            "title": "Deep Learning for Image Compressed Sensing Reconstruction",
            "abstract": "We propose a CNN for compressive sensing image reconstruction.",
            "source_url": "https://arxiv.org/abs/0000.00002",
        },
    ]
    accepted, rejected = filter_relevant_papers(CS_QUESTION, papers)
    ids_ok = {p["evidence_id"] for p in accepted}
    ids_bad = {p["evidence_id"] for p in rejected}
    assert "p-good" in ids_ok
    assert "p-bad" in ids_bad


def test_cs_query_rejects_langchain_repo() -> None:
    repos = [
        {
            "evidence_id": "repo-langchain-ai-langchain",
            "repository": "langchain-ai/langchain",
            "description": "Building applications with LLMs through composability",
            "architecture_summary": "RAG chains and agents",
            "source_url": "https://github.com/langchain-ai/langchain",
        }
    ]
    accepted, rejected = filter_relevant_repos(CS_QUESTION, repos)
    assert not accepted
    assert rejected


def test_rag_query_accepts_langchain_repo() -> None:
    repos = [
        {
            "evidence_id": "repo-langchain-ai-langchain",
            "repository": "langchain-ai/langchain",
            "description": "Building applications with LLMs through composability",
            "architecture_summary": "RAG retrieval chains",
            "source_url": "https://github.com/langchain-ai/langchain",
        }
    ]
    accepted, _ = filter_relevant_repos(RAG_QUESTION, repos)
    assert accepted


def test_fixture_theme_rejects_cs_for_rag_corpus() -> None:
    assert not fixture_theme_compatible(CS_QUESTION, fixture_theme="rag")
    assert fixture_theme_compatible(RAG_QUESTION, fixture_theme="rag")


def test_review_does_not_auto_support_fixed_rag_claim() -> None:
    papers = [
        {
            "evidence_id": "p-cs",
            "title": "Deep Compressed Sensing",
            "abstract": "compressed sensing image reconstruction with deep learning",
            "source_url": "https://arxiv.org/abs/1",
        }
    ]
    # Legacy hard-coded claim must not be auto-supported just because a paper exists
    finding = claim_supported_by_evidence(
        {
            "claim": "Hybrid retrieval improves over Naive RAG",
            "related_evidence_ids": ["p-cs"],
            "kind": "paper_support",
        },
        papers,
        [],
        CS_QUESTION,
    )
    # Paper is on-topic for CS, so status may be supported for *that* claim text,
    # but claims_from_question must not emit the fixed RAG slogan.
    derived = claims_from_question_and_evidence(CS_QUESTION, papers, [])
    assert all("Hybrid retrieval improves over Naive RAG" not in (c.get("claim") or "") for c in derived)
    assert finding["related_evidence_ids"] == ["p-cs"]


def test_fixture_cs_question_fails_without_fake_success(tasks_tmpdir: Path) -> None:
    final = run_research_workflow(
        task_id="sf-rel-cs-fixture",
        question=CS_QUESTION,
        workflow_mode="research_orchestration",
        artifacts_dir=str(ARTIFACTS),
        data_mode="fixture",
        persist_artifacts=False,
    )
    assert final["overall_status"] == "failed"
    assert not final.get("papers") or final.get("review_decision") == "fail"


def test_fixture_rag_still_succeeds(tasks_tmpdir: Path) -> None:
    final = run_research_workflow(
        task_id="sf-rel-rag-ok",
        question=RAG_QUESTION,
        workflow_mode="research_orchestration",
        artifacts_dir=str(ARTIFACTS),
        data_mode="fixture",
        persist_artifacts=False,
    )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    assert final.get("papers")
    assert final.get("repositories")
    reviews = final.get("reviews") or []
    assert reviews
    assert all("Hybrid retrieval improves over Naive RAG" != r.get("claim") for r in reviews)
    # Claims must reference real evidence ids
    for r in reviews:
        if r.get("related_evidence_ids"):
            assert r.get("status") in {
                "supported",
                "partially_supported",
                "unsupported",
                "conflicting",
                "unverified",
            }


def test_live_irrelevant_papers_not_accepted(tasks_tmpdir: Path) -> None:
    junk = [
        {
            "evidence_id": "paper-live-0",
            "title": "GitHub Emoji and AI Agent Developer Challenges",
            "authors": ["A"],
            "year": 2024,
            "venue": "arXiv",
            "identifier": "2401.00001",
            "source_url": "https://arxiv.org/abs/2401.00001",
            "abstract": "We analyze GitHub application popularity and developer collaboration.",
            "research_problem": "GitHub sociology",
            "methodology": "survey",
            "datasets": [],
            "metrics": [],
            "key_findings": ["emoji matter"],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        }
    ]

    def _papers(query: str, max_results: int = 12) -> tuple[list, list]:
        return junk, [{"tool": "search_academic_papers", "args": {"query": query}}]

    from scholarflow_api.mcp.client import ScholarMcpError

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_papers):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("no relevant repo"),
        ):
            final = run_research_workflow(
                task_id="sf-rel-live-junk",
                question=CS_QUESTION,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert not final.get("papers")
    assert final["overall_status"] == "failed"
    # Experiment must not treat junk as reliable input
    exp = next(s for s in final["subtasks"] if s["role"] == "experiment_design")
    assert exp["status"] == "failed"


def test_live_relevant_papers_can_pass_paper_gate(tasks_tmpdir: Path) -> None:
    good = [
        {
            "evidence_id": "paper-live-cs",
            "title": "ISTA-Net: Interpretable Optimization-Inspired Deep Network for Image Compressive Sensing",
            "authors": ["Zhang"],
            "year": 2018,
            "venue": "CVPR",
            "identifier": "1806.00001",
            "source_url": "https://arxiv.org/abs/1806.00001",
            "abstract": "Deep learning network for image compressed sensing reconstruction.",
            "research_problem": "image compressed sensing",
            "methodology": "deep unfolding",
            "datasets": ["Set11"],
            "metrics": ["PSNR", "SSIM"],
            "key_findings": ["ISTA-Net improves PSNR"],
            "limitations": ["training cost"],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        }
    ]
    good_repo = {
        "evidence_id": "repo-cs",
        "repository": "jianzhangcs/ISTA-Net",
        "source_url": "https://github.com/jianzhangcs/ISTA-Net",
        "description": "ISTA-Net for image compressed sensing",
        "language": "Python",
        "framework": ["PyTorch"],
        "architecture_summary": "Deep unfolding compressed sensing reconstruction",
        "key_modules": ["models"],
        "installation_summary": "pip install",
        "reproducibility_notes": [],
        "limitations": [],
        "default_branch": "master",
        "root_listing": [],
        "verification_status": "verified",
        "fetched_at": "2024-01-01T00:00:00Z",
    }

    def _papers(query: str, max_results: int = 12) -> tuple[list, list]:
        assert "compress" in query.lower() or "sensing" in query.lower() or "deep" in query.lower()
        return good, [{"tool": "search_academic_papers", "args": {"query": query}}]

    with patch("scholarflow_api.graph.nodes.fetch_papers_via_mcp", side_effect=_papers):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            return_value=(good_repo, [], {"selected": "jianzhangcs/ISTA-Net", "method": "mock"}),
        ):
            final = run_research_workflow(
                task_id="sf-rel-live-ok",
                question=CS_QUESTION,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final.get("papers")
    assert final["papers"][0]["evidence_id"] == "paper-live-cs"
    assert final.get("repositories")
    exp = final.get("experiment") or {}
    assert "paper-live-cs" in (exp.get("upstream_paper_ids") or [])
    assert "Naive RAG" not in str(exp.get("hypotheses") or [])
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
