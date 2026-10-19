"""Regression against failure signature of sf-fcb37987da7b (do not overwrite that task)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.evidence_gate import (
    classify_paper_relevance,
    extract_paper_query,
    extract_repo_search_query,
    extract_short_topic_title,
    filter_relevant_papers,
)
from scholarflow_api.graph.nodes import experiment_design_node, orchestrator_node
from scholarflow_api.graph.workflow import run_research_workflow
from scholarflow_api.mcp.client import ScholarMcpError

ARTIFACTS = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"

# Exact-style brief from the failed live task (preserved historically as sf-fcb37987da7b).
FCB_Q = (
    "基于深度学习的图像压缩感知重建（Deep Learning for Image Compressed Sensing Reconstruction）："
    "分析研究问题、核心方法与创新点、局限性；检索真正实现图像压缩感知重建的 GitHub 仓库并分析技术框架、"
    "关键模块与复现条件；基于实际检索到的论文与仓库证据设计实验（Baseline、对照实验、消融实验、评价指标）；"
    "审查证据相关性（核心/辅助/不相关）；生成科研报告与全部产物。"
)


@pytest.fixture()
def tasks_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "tasks"
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(root))
    return root


def test_long_zh_instruction_becomes_concrete_paper_query() -> None:
    q = extract_paper_query(FCB_Q)
    assert "分析研究问题" not in q
    assert "评价指标" not in q
    assert len(q) < 160
    assert "compressed sensing" in q.lower() or "compressive sensing" in q.lower()
    # Must not be the full brief or a verbatim long English title alone
    assert q != FCB_Q
    assert "langchain" not in q.lower()
    assert q.lower().startswith("image") or "image" in q.lower()


def test_repo_query_not_langchain_rag() -> None:
    rq = extract_repo_search_query(FCB_Q)
    assert "langchain" not in rq.lower()
    assert "retrieval augmented" not in rq.lower()
    assert "ista-net" in rq.lower() or "compressive sensing" in rq.lower()
    assert "(" not in rq  # GitHub-friendly


def test_short_title_not_full_brief() -> None:
    title = extract_short_topic_title(FCB_Q)
    assert len(title) <= 80
    assert "分析研究问题" not in title
    assert "Compressed Sensing" in title or "compressed sensing" in title.lower()


def test_orchestrator_plan_uses_cleaned_queries() -> None:
    out = orchestrator_node(
        {
            "task_id": "t-fcb-orch",
            "question": FCB_Q,
            "workflow_mode": "research_orchestration",
            "artifacts_dir": str(ARTIFACTS),
        }
    )
    plan = out["research_plan"]
    assert plan["title"] != FCB_Q
    assert "分析研究问题" not in plan["title"]
    assert all(q != FCB_Q for q in plan["search_queries"])
    assert all("langchain" not in q.lower() for q in plan["code_search_queries"])
    assert plan["objective"] == FCB_Q  # full brief retained


def test_mri_and_remote_sensing_classification() -> None:
    mri = {
        "title": "Compressed Sensing: From Research to Clinical Practice with Data-Driven Learning",
        "abstract": "Compressed sensing in MRI enables high subsampling factors.",
        "research_problem": "MRI compressed sensing clinical practice",
        "methodology": "",
    }
    remote = {
        "title": "A Progressive Image Restoration Network for High-order Degradation Imaging in Remote Sensing",
        "abstract": "deep learning image restoration for remote sensing (RS).",
        "research_problem": "remote sensing restoration",
        "methodology": "",
    }
    image_cs = {
        "title": "ISTA-Net: Interpretable Optimization-Inspired Deep Network for Image Compressive Sensing",
        "abstract": "deep network for image compressed sensing reconstruction",
        "research_problem": "image compressive sensing",
        "methodology": "deep unfolding",
    }
    assert classify_paper_relevance(FCB_Q, mri)[0] == "supporting"
    assert classify_paper_relevance(FCB_Q, remote)[0] == "irrelevant"
    assert classify_paper_relevance(FCB_Q, image_cs)[0] == "core"


def test_experiment_has_no_rag_template_for_cs() -> None:
    core = {
        "evidence_id": "paper-cs",
        "title": "Deep Learning for Image Compressed Sensing Reconstruction",
        "relevance_tier": "core",
        "datasets": ["Set11"],
        "metrics": ["PSNR", "SSIM"],
    }
    repo = {
        "evidence_id": "repo-cs",
        "repository": "jianzhangcs/ISTA-Net",
        "relevance_tier": "core",
    }
    out = experiment_design_node(
        {
            "task_id": "t-fcb-exp",
            "question": FCB_Q,
            "workflow_mode": "research_orchestration",
            "papers": [core],
            "repositories": [repo],
            "subtasks": [
                {"role": "paper_research", "status": "succeeded"},
                {"role": "repository_analysis", "status": "succeeded"},
            ],
        }
    )
    exp = out["experiment"]
    blob = str(exp).lower()
    assert "naive rag" not in blob
    assert "natural questions" not in blob
    assert "squad" not in blob
    assert "bm25" not in blob
    assert "rrf" not in blob
    assert "psnr" in blob
    assert "ssim" in blob
    assert exp["upstream_paper_ids"] == ["paper-cs"]


def test_live_mock_rejects_langchain_and_rag_review(tasks_tmpdir: Path) -> None:
    papers = [
        {
            "evidence_id": "paper-ista",
            "title": "ISTA-Net for Image Compressive Sensing",
            "authors": ["Z"],
            "year": 2018,
            "venue": "CVPR",
            "identifier": "1806.00001",
            "source_url": "https://arxiv.org/abs/1806.00001",
            "abstract": "deep network for image compressed sensing reconstruction",
            "research_problem": "image compressive sensing",
            "methodology": "ISTA-Net",
            "datasets": ["Set11"],
            "metrics": ["PSNR", "SSIM"],
            "key_findings": [],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        },
        {
            "evidence_id": "paper-mri",
            "title": "Compressed Sensing: From Research to Clinical Practice with Data-Driven Learning",
            "authors": ["C"],
            "year": 2019,
            "venue": "arXiv",
            "identifier": "1903.07824",
            "source_url": "https://arxiv.org/abs/1903.07824",
            "abstract": "Compressed sensing in MRI with deep learning",
            "research_problem": "MRI compressed sensing",
            "methodology": "",
            "datasets": [],
            "metrics": [],
            "key_findings": [],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        },
        {
            "evidence_id": "paper-rs",
            "title": "Progressive Image Restoration for Remote Sensing",
            "authors": ["R"],
            "year": 2024,
            "venue": "arXiv",
            "identifier": "2412.07195",
            "source_url": "https://arxiv.org/abs/2412.07195",
            "abstract": "image restoration network for remote sensing high-order degradation",
            "research_problem": "remote sensing restoration",
            "methodology": "",
            "datasets": [],
            "metrics": [],
            "key_findings": [],
            "limitations": [],
            "evidence_level": "abstract_only",
            "verification_status": "verified",
            "fetched_at": "2024-01-01T00:00:00Z",
        },
    ]
    good_repo = {
        "evidence_id": "repo-ista",
        "repository": "jianzhangcs/ISTA-Net",
        "source_url": "https://github.com/jianzhangcs/ISTA-Net",
        "description": "ISTA-Net image compressed sensing",
        "language": "Python",
        "framework": ["PyTorch"],
        "architecture_summary": "deep unfolding for image compressive sensing reconstruction",
        "key_modules": ["models"],
        "installation_summary": "pip",
        "reproducibility_notes": [],
        "limitations": [],
        "default_branch": "master",
        "root_listing": [],
        "verification_status": "verified",
        "fetched_at": "2024-01-01T00:00:00Z",
    }

    with patch(
        "scholarflow_api.graph.nodes.fetch_papers_via_mcp",
        return_value=(papers, [{"tool": "search_academic_papers", "args": {"query": "x"}}]),
    ):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            return_value=(good_repo, [], {"selected": "jianzhangcs/ISTA-Net"}),
        ):
            final = run_research_workflow(
                task_id="sf-fcb-reg-ok",
                question=FCB_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    plan = final.get("research_plan") or {}
    assert all("langchain" not in q.lower() for q in (plan.get("code_search_queries") or []))
    ids = {p["evidence_id"] for p in (final.get("papers") or [])}
    assert "paper-ista" in ids
    assert "paper-rs" not in ids
    tiers = {p["evidence_id"]: p.get("relevance_tier") for p in (final.get("papers") or [])}
    assert tiers.get("paper-ista") == "core"
    if "paper-mri" in tiers:
        assert tiers["paper-mri"] == "supporting"
    exp = final.get("experiment") or {}
    assert "paper-ista" in (exp.get("upstream_paper_ids") or [])
    assert "paper-mri" not in (exp.get("upstream_paper_ids") or [])
    blob = str(exp).lower()
    assert "naive rag" not in blob and "bm25" not in blob
    reviews = final.get("reviews") or []
    assert all("Hybrid retrieval improves over Naive RAG" != r.get("claim") for r in reviews)
    repos = final.get("repositories") or []
    assert repos and "langchain" not in (repos[0].get("repository") or "").lower()


def test_no_core_cannot_full_succeed(tasks_tmpdir: Path) -> None:
    only_mri = [
        {
            "evidence_id": "paper-mri-only",
            "title": "Compressed Sensing: From Research to Clinical Practice with Data-Driven Learning",
            "authors": ["C"],
            "year": 2019,
            "venue": "arXiv",
            "identifier": "1903.07824",
            "source_url": "https://arxiv.org/abs/1903.07824",
            "abstract": "Compressed sensing in MRI",
            "research_problem": "MRI compressed sensing clinical",
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
    with patch(
        "scholarflow_api.graph.nodes.fetch_papers_via_mcp",
        return_value=(only_mri, []),
    ):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("no cs repo"),
        ):
            final = run_research_workflow(
                task_id="sf-fcb-no-core",
                question=FCB_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    assert final.get("overall_status") != "succeeded"


def test_historical_fcb379_not_overwritten() -> None:
    p = Path("data/tasks/sf-fcb37987da7b/task_state.json")
    if not p.is_file():
        pytest.skip("historical task not present in this checkout")
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["task_id"] == "sf-fcb37987da7b"
    assert data["status"] == "partial_succeeded"
