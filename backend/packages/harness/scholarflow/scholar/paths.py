"""Sandbox output path helpers for ScholarFlow tasks."""

from __future__ import annotations

from pathlib import PurePosixPath

OUTPUTS_ROOT = PurePosixPath("/mnt/user-data/outputs")

REQUIRED_ARTIFACTS = (
    "research_report.md",
    "research_plan.json",
    "paper_evidence.json",
    "paper_matrix.csv",
    "repository_evidence.json",
    "repository_matrix.csv",
    "experiment_plan.md",
    "evidence_review.json",
    "sources.json",
)


def task_output_dir(task_id: str) -> PurePosixPath:
    """Return the virtual output directory for a research task."""
    safe_id = task_id.strip().replace("..", "").replace("/", "-")
    if not safe_id:
        raise ValueError("task_id must not be empty")
    return OUTPUTS_ROOT / safe_id


def artifact_path(task_id: str, filename: str) -> PurePosixPath:
    """Return a virtual artifact path under the task output directory."""
    if filename not in REQUIRED_ARTIFACTS:
        raise ValueError(f"unknown artifact filename: {filename}")
    return task_output_dir(task_id) / filename
