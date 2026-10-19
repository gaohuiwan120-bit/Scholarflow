"""core / supporting / irrelevant grading + downstream constraints."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scholarflow_api.config import repo_root
from scholarflow_api.graph.evidence_gate import (
    classify_paper_relevance,
    filter_relevant_papers,
    papers_by_tier,
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


def _paper(eid: str, title: str, abstract: str, **extra: Any) -> dict[str, Any]:
    return {
        "evidence_id": eid,
        "title": title,
        "authors": ["A"],
        "year": 2020,
        "venue": "arXiv",
        "identifier": eid.replace("paper-", ""),
        "source_url": f"https://arxiv.org/abs/{eid.replace('paper-', '')}",
        "abstract": abstract,
        "research_problem": abstract,
        "methodology": extra.get("methodology", ""),
        "datasets": [],
        "metrics": [],
        "key_findings": [],
        "limitations": [],
        "evidence_level": "abstract_only",
        "verification_status": "verified",
        "fetched_at": "2024-01-01T00:00:00Z",
    }


SAMPLES = {
    "core_cs": _paper(
        "paper-core-cs",
        "Deep Learning for Image Compressed Sensing Reconstruction",
        "We propose a CNN for compressive sensing image reconstruction on Set11.",
        methodology="deep unfolding",
    ),
    "core_mri_cs": _paper(
        "paper-core-mri",
        "Compressed Sensing: From Research to Clinical Practice with Data-Driven Learning",
        "Compressed sensing in MRI with deep learning reconstruction.",
    ),
    "supporting_sparse": _paper(
        "paper-supp-sparse",
        "A Survey of Sparse Recovery Algorithms",
        "We review sparse recovery and measurement matrix design for underdetermined systems.",
    ),
    "irrel_remote": _paper(
        "paper-irrel-remote",
        "Oriented object detection in optical remote sensing images using deep learning: a survey",
        "Oriented object detection is a fundamental task in remote sensing (RS).",
    ),
    "irrel_thrombus": _paper(
        "paper-irrel-thrombus",
        "Predicting Thrombectomy Recanalization from CT Imaging Using Deep Learning Models",
        "We predict thrombectomy recanalization for ischemic stroke using CT imaging.",
    ),
    "irrel_lecture": _paper(
        "paper-irrel-lecture",
        "Deep Learning and Computational Physics (Lecture Notes)",
        "These lecture notes introduce deep learning for engineering graduate students.",
    ),
}


def test_core_cs_paper_graded_core() -> None:
    tier, _, reasons = classify_paper_relevance(CS_Q, SAMPLES["core_cs"])
    assert tier == "core"
    assert any("core" in r for r in reasons)


def test_mri_cs_is_supporting_not_core() -> None:
    """MRI / clinical CS is boundary supporting for natural-image CS goals."""
    tier, _, reasons = classify_paper_relevance(CS_Q, SAMPLES["core_mri_cs"])
    assert tier == "supporting"
    assert any("supporting" in r for r in reasons)


def test_supporting_sparse_recovery_not_core() -> None:
    tier, _, _ = classify_paper_relevance(CS_Q, SAMPLES["supporting_sparse"])
    assert tier == "supporting"


def test_weak_papers_are_irrelevant() -> None:
    for key in ("irrel_remote", "irrel_thrombus", "irrel_lecture"):
        tier, _, _ = classify_paper_relevance(CS_Q, SAMPLES[key])
        assert tier == "irrelevant", key


def test_filter_keeps_core_and_supporting_only() -> None:
    accepted, rejected = filter_relevant_papers(CS_Q, list(SAMPLES.values()))
    tiers = {p["evidence_id"]: p["relevance_tier"] for p in accepted}
    assert tiers["paper-core-cs"] == "core"
    assert tiers["paper-core-mri"] == "supporting"
    assert tiers["paper-supp-sparse"] == "supporting"
    rej_ids = {p["evidence_id"] for p in rejected}
    assert "paper-irrel-remote" in rej_ids
    assert "paper-irrel-thrombus" in rej_ids
    assert "paper-irrel-lecture" in rej_ids
    # Core sorts before supporting
    assert accepted[0]["relevance_tier"] == "core"


def test_experiment_driven_by_core_not_weak(tasks_tmpdir: Path) -> None:
    good_repo = {
        "evidence_id": "repo-cs",
        "repository": "jianzhangcs/ISTA-Net",
        "source_url": "https://github.com/jianzhangcs/ISTA-Net",
        "description": "ISTA-Net for image compressed sensing",
        "language": "Python",
        "framework": ["PyTorch"],
        "architecture_summary": "deep unfolding compressed sensing reconstruction",
        "key_modules": ["models"],
        "installation_summary": "pip",
        "reproducibility_notes": [],
        "limitations": [],
        "default_branch": "master",
        "root_listing": [],
        "verification_status": "verified",
        "fetched_at": "2024-01-01T00:00:00Z",
    }
    mixed = [
        SAMPLES["irrel_remote"],
        SAMPLES["irrel_thrombus"],
        SAMPLES["irrel_lecture"],
        SAMPLES["supporting_sparse"],
        SAMPLES["core_cs"],
    ]

    with patch(
        "scholarflow_api.graph.nodes.fetch_papers_via_mcp",
        return_value=(mixed, [{"tool": "search_academic_papers"}]),
    ):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            return_value=(good_repo, [], {"selected": "jianzhangcs/ISTA-Net"}),
        ):
            final = run_research_workflow(
                task_id="sf-tier-core-drive",
                question=CS_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    papers = final.get("papers") or []
    ids = {p["evidence_id"] for p in papers}
    assert "paper-core-cs" in ids
    assert "paper-irrel-remote" not in ids
    assert "paper-irrel-thrombus" not in ids
    assert "paper-irrel-lecture" not in ids
    exp = final.get("experiment") or {}
    assert exp.get("upstream_paper_ids") == ["paper-core-cs"] or "paper-core-cs" in (
        exp.get("upstream_paper_ids") or []
    )
    assert "paper-irrel-remote" not in (exp.get("upstream_paper_ids") or [])
    # Supporting may be listed separately, never as core upstream
    if "paper-supp-sparse" in ids:
        assert "paper-supp-sparse" not in (exp.get("upstream_paper_ids") or [])
        assert "paper-supp-sparse" in (exp.get("upstream_supporting_paper_ids") or [])
    reviews = final.get("reviews") or []
    assert all("Hybrid retrieval improves over Naive RAG" != r.get("claim") for r in reviews)


def test_only_irrelevant_papers_fail_workflow(tasks_tmpdir: Path) -> None:
    junk = [
        SAMPLES["irrel_remote"],
        SAMPLES["irrel_thrombus"],
        SAMPLES["irrel_lecture"],
    ]
    with patch(
        "scholarflow_api.graph.nodes.fetch_papers_via_mcp",
        return_value=(junk, [{"tool": "search_academic_papers"}]),
    ):
        with patch(
            "scholarflow_api.graph.nodes.resolve_live_repository",
            side_effect=ScholarMcpError("no repo"),
        ):
            final = run_research_workflow(
                task_id="sf-tier-no-core",
                question=CS_Q,
                workflow_mode="research_orchestration",
                artifacts_dir=str(ARTIFACTS),
                data_mode="live",
                allow_fixture_fallback=False,
                persist_artifacts=False,
            )
    assert final["overall_status"] == "failed"
    assert not final.get("papers")
    paper = next(s for s in final["subtasks"] if s["role"] == "paper_research")
    assert paper["status"] == "failed"
    assert "core" in (paper.get("error") or "").lower() or "relevance" in (
        paper.get("error") or ""
    ).lower() or "none passed" in (paper.get("error") or "").lower()


def test_sf12_snapshot_titles_would_not_enter_core() -> None:
    """Replay titles from sf-12fa1e2791cb without overwriting that task."""
    historical_weak = [
        SAMPLES["irrel_remote"],
        SAMPLES["irrel_thrombus"],
        SAMPLES["irrel_lecture"],
    ]
    historical = [
        SAMPLES["core_cs"],
        _paper(
            "paper-2410.18954v2",
            "Learning Structured Compressed Sensing with Automatic Resource Allocation",
            "Structured compressed sensing with ultrasound localization resource allocation.",
        ),
    ]
    accepted, rejected = filter_relevant_papers(CS_Q, historical_weak + historical)
    core, supporting = papers_by_tier(accepted)
    core_ids = {p["evidence_id"] for p in core}
    supporting_ids = {p["evidence_id"] for p in supporting}
    assert "paper-core-cs" in core_ids
    # Structured/ultrasound CS is supporting for natural-image CS goals (not core).
    assert "paper-2410.18954v2" in supporting_ids or "paper-2410.18954v2" in core_ids
    assert "paper-2410.18954v2" not in {p["evidence_id"] for p in rejected}
    assert not any(p["evidence_id"].startswith("paper-irrel") for p in core)
    assert {p["evidence_id"] for p in rejected} >= {
        "paper-irrel-remote",
        "paper-irrel-thrombus",
        "paper-irrel-lecture",
    }


def test_rag_fixture_workflow_still_ok(tasks_tmpdir: Path) -> None:
    final = run_research_workflow(
        task_id="sf-tier-rag-fixture",
        question="Blended RAG hybrid dense sparse vs Naive RAG",
        workflow_mode="research_orchestration",
        artifacts_dir=str(ARTIFACTS),
        data_mode="fixture",
        persist_artifacts=False,
    )
    assert final["overall_status"] in {"succeeded", "partial_succeeded"}
    assert final.get("papers")
