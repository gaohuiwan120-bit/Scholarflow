#!/usr/bin/env python3
"""Run ScholarFlow offline evaluation on fixture artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

from scholarflow.scholar.artifacts import build_task_artifacts
from scholarflow.scholar.models import ExperimentPlan, PaperEvidence, RepositoryEvidence, ResearchPlan, ReviewFinding
from scholarflow.scholar.validation import validate_json_artifact

from evaluation.metrics import (
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


def _fixture_artifacts(task_id: str) -> dict[str, str]:
    plan = ResearchPlan(
        task_id=task_id,
        title=f"Evaluation task {task_id}",
        objective="Offline evaluation fixture",
        research_questions=["What works?"],
    )
    papers = [
        PaperEvidence(
            evidence_id="p1",
            title="Fixture Paper",
            source_url="https://arxiv.org/abs/0000.00001",
            key_findings=["Fixture finding"],
        )
    ]
    repos = [
        RepositoryEvidence(
            evidence_id="r1",
            repository="org/fixture",
            source_url="https://github.com/org/fixture",
        )
    ]
    experiment = ExperimentPlan(objective="Validate fixture pipeline", hypotheses=["H1"])
    reviews = [
        ReviewFinding(
            claim="Fixture claim",
            status="supported",
            reason="Matches fixture paper",
            recommended_action="none",
        )
    ]
    return build_task_artifacts(plan, papers, repos, experiment, reviews)


def main() -> None:
    parser = argparse.ArgumentParser(description="ScholarFlow offline evaluation")
    parser.add_argument("--tasks", default=str(Path(__file__).parent / "tasks.json"))
    args = parser.parse_args()

    tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))["tasks"]
    results = []
    for task in tasks:
        artifacts = _fixture_artifacts(task["id"])
        metrics = [
            artifact_completeness(artifacts),
            report_structure(artifacts["research_report.md"]),
            evidence_coverage(1, 1),
            matrix_row_consistency(artifacts),
            source_traceability(artifacts),
            review_coverage(artifacts),
            experiment_plan_presence(artifacts),
            json_parseability(artifacts),
            csv_parseability(artifacts),
            markdown_nonempty(artifacts),
        ]
        valid = 0
        json_files = {
            "research_plan.json": json.loads(artifacts["research_plan.json"]),
            "paper_evidence.json": json.loads(artifacts["paper_evidence.json"]),
            "repository_evidence.json": json.loads(artifacts["repository_evidence.json"]),
            "evidence_review.json": json.loads(artifacts["evidence_review.json"]),
            "sources.json": json.loads(artifacts["sources.json"]),
        }
        for name, payload in json_files.items():
            try:
                validate_json_artifact(name, payload)
                valid += 1
            except Exception:
                pass
        metrics.append(schema_validity(valid, len(json_files)))
        score = aggregate_score(metrics)
        results.append({"task_id": task["id"], "score": score, "metrics": [m.__dict__ for m in metrics]})

    summary = {"task_count": len(results), "average_score": aggregate_score([]) if not results else sum(r["score"] for r in results) / len(results), "results": results}
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
