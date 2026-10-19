"""Unified artifact loading and benchmark scoring."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from scholarflow.scholar.validation import validate_json_artifact

from evaluation.metrics import (
    REQUIRED_ARTIFACTS,
    MetricResult,
    aggregate_score,
    artifact_completeness,
    csv_parseability,
    evidence_coverage,
    experiment_plan_presence,
    json_parseability,
    markdown_nonempty,
    matrix_row_consistency,
    report_structure,
    review_coverage,
    schema_validity,
    source_traceability,
)
from evaluation.quality_metrics import (
    anti_fabrication_heuristic,
    e2e_pass_gate,
    evidence_richness,
    keyword_in_plan,
    review_substantive,
    topic_relevance,
    url_validity,
    verification_rate,
)


@dataclass
class TaskSpec:
    id: str
    prompt: str
    keywords: list[str] = field(default_factory=list)
    min_papers: int = 3
    min_repos: int = 1
    expected_artifacts: int = 9


@dataclass
class TaskScore:
    task_id: str
    prompt: str
    score: float
    e2e_pass: bool
    metrics: list[MetricResult]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    mode: str
    task_count: int
    average_score: float
    e2e_pass_rate: float
    results: list[TaskScore]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "task_count": self.task_count,
            "average_score": self.average_score,
            "e2e_pass_rate": self.e2e_pass_rate,
            "metadata": self.metadata,
            "results": [
                {
                    "task_id": r.task_id,
                    "prompt": r.prompt,
                    "score": r.score,
                    "e2e_pass": r.e2e_pass,
                    "metadata": r.metadata,
                    "metrics": [m.__dict__ for m in r.metrics],
                }
                for r in self.results
            ],
        }


def load_task_specs(path: Path) -> list[TaskSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks", payload if isinstance(payload, list) else [])
    specs: list[TaskSpec] = []
    for item in tasks:
        specs.append(
            TaskSpec(
                id=item["id"],
                prompt=item.get("prompt", ""),
                keywords=item.get("keywords", []),
                min_papers=item.get("min_papers", 3),
                min_repos=item.get("min_repos", 1),
                expected_artifacts=item.get("expected_artifacts", 9),
            )
        )
    return specs


def load_artifacts_from_dir(task_dir: Path) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = task_dir / name
        if path.exists():
            artifacts[name] = path.read_text(encoding="utf-8")
    return artifacts


def _schema_validity_score(artifacts: dict[str, str]) -> tuple[MetricResult, int, int]:
    json_files = {
        "research_plan.json": "research_plan.json",
        "paper_evidence.json": "paper_evidence.json",
        "repository_evidence.json": "repository_evidence.json",
        "evidence_review.json": "evidence_review.json",
        "sources.json": "sources.json",
    }
    valid = 0
    for filename, key in json_files.items():
        if key not in artifacts:
            continue
        try:
            validate_json_artifact(key, json.loads(artifacts[key]))
            valid += 1
        except Exception:
            pass
    total = len(json_files)
    return schema_validity(valid, total), valid, total


def score_artifacts(task: TaskSpec, artifacts: dict[str, str], *, metadata: dict[str, Any] | None = None) -> TaskScore:
    import json as json_mod

    papers = json_mod.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json_mod.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])

    schema_metric, _, _ = _schema_validity_score(artifacts)
    metrics = [
        artifact_completeness(artifacts),
        schema_metric,
        report_structure(artifacts.get("research_report.md", "")),
        evidence_coverage(len(papers), len(repos), task.min_papers, task.min_repos),
        matrix_row_consistency(artifacts),
        source_traceability(artifacts),
        review_coverage(artifacts),
        experiment_plan_presence(artifacts),
        json_parseability(artifacts),
        csv_parseability(artifacts),
        markdown_nonempty(artifacts),
        topic_relevance(artifacts, task.keywords),
        keyword_in_plan(artifacts, task.keywords),
        url_validity(artifacts),
        verification_rate(artifacts),
        evidence_richness(artifacts),
        review_substantive(artifacts),
        anti_fabrication_heuristic(artifacts),
    ]
    gate = e2e_pass_gate(metrics)
    metrics.append(gate)
    return TaskScore(
        task_id=task.id,
        prompt=task.prompt,
        score=aggregate_score(metrics[:-1]),  # exclude gate from average
        e2e_pass=gate.score >= 1.0,
        metrics=metrics,
        metadata=metadata or {},
    )


def run_benchmark(
    tasks: list[TaskSpec],
    artifact_loader: Callable[[TaskSpec], dict[str, str]],
    *,
    mode: str,
    metadata: dict[str, Any] | None = None,
) -> BenchmarkReport:
    results: list[TaskScore] = []
    for task in tasks:
        artifacts = artifact_loader(task)
        results.append(score_artifacts(task, artifacts, metadata={"loader": mode}))
    avg = aggregate_score([]) if not results else sum(r.score for r in results) / len(results)
    pass_rate = sum(1 for r in results if r.e2e_pass) / len(results) if results else 0.0
    return BenchmarkReport(
        mode=mode,
        task_count=len(results),
        average_score=avg,
        e2e_pass_rate=pass_rate,
        results=results,
        metadata=metadata or {},
    )
