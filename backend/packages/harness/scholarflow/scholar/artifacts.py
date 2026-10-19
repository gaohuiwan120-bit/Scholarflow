"""Assemble ScholarFlow task artifacts from structured inputs."""

from __future__ import annotations

import json
from typing import Any

from scholarflow.scholar.aggregation import dedupe_papers, dedupe_repositories, merge_sources
from scholarflow.scholar.experiment_plan import render_experiment_plan_md
from scholarflow.scholar.matrix import generate_paper_matrix, generate_repository_matrix
from scholarflow.scholar.models import (
    ExperimentPlan,
    PaperEvidence,
    RepositoryEvidence,
    ResearchPlan,
    ReviewFinding,
)
from scholarflow.scholar.paths import REQUIRED_ARTIFACTS, artifact_path
from scholarflow.scholar.report import build_research_report


def build_task_artifacts(
    plan: ResearchPlan,
    papers: list[PaperEvidence],
    repositories: list[RepositoryEvidence],
    experiment: ExperimentPlan,
    reviews: list[ReviewFinding],
) -> dict[str, str]:
    """Return filename -> content for all nine ScholarFlow artifacts."""
    papers = dedupe_papers(papers)
    repositories = dedupe_repositories(repositories)
    sources = merge_sources(papers, repositories)
    return {
        "research_report.md": build_research_report(plan, papers, repositories, experiment, reviews),
        "research_plan.json": json.dumps(plan.model_dump(), indent=2, ensure_ascii=False),
        "paper_evidence.json": json.dumps({"items": [p.model_dump() for p in papers]}, indent=2, ensure_ascii=False),
        "paper_matrix.csv": generate_paper_matrix(papers),
        "repository_evidence.json": json.dumps(
            {"items": [r.model_dump() for r in repositories]}, indent=2, ensure_ascii=False
        ),
        "repository_matrix.csv": generate_repository_matrix(repositories),
        "experiment_plan.md": render_experiment_plan_md(experiment),
        "evidence_review.json": json.dumps({"items": [r.model_dump() for r in reviews]}, indent=2, ensure_ascii=False),
        "sources.json": json.dumps({"items": [s.model_dump() for s in sources]}, indent=2, ensure_ascii=False),
    }


def list_task_artifact_paths(task_id: str) -> dict[str, str]:
    return {name: str(artifact_path(task_id, name)) for name in REQUIRED_ARTIFACTS}


def summarize_artifacts(artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "artifact_count": len(artifacts),
        "artifacts": sorted(artifacts.keys()),
        "missing": [name for name in REQUIRED_ARTIFACTS if name not in artifacts],
    }
