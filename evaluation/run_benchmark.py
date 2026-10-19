#!/usr/bin/env python3
"""Run ScholarFlow benchmark in fixture, golden, or artifacts-dir mode."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

from scholarflow.scholar.artifacts import build_task_artifacts
from scholarflow.scholar.models import ExperimentPlan, PaperEvidence, RepositoryEvidence, ResearchPlan, ReviewFinding

from evaluation.report import render_markdown, resume_bullet_summary
from evaluation.scorer import TaskSpec, load_artifacts_from_dir, load_task_specs, run_benchmark


def _golden_artifacts(task: TaskSpec) -> dict[str, str]:
    """Realistic golden artifacts for resume demo scoring."""
    plan = ResearchPlan(
        task_id=f"bench-{task.id}",
        title=f"Benchmark: {task.id}",
        objective=task.prompt,
        research_questions=[f"What are key approaches in {task.id}?"],
        search_queries=task.keywords[:3],
        code_search_queries=[f"{task.keywords[0]}-implementation"],
    )
    papers = [
        PaperEvidence(
            evidence_id=f"p{i}",
            title=f"{kw.title()} for {task.id} — Study {i}",
            source_url=f"https://arxiv.org/abs/2401.0{i:04d}",
            identifier=f"2401.0{i:04d}",
            research_problem=f"Problem related to {kw}",
            methodology="Empirical evaluation on public benchmarks",
            key_findings=[f"{kw} improves baseline metrics"],
            limitations=["Limited to English corpora"],
            verification_status="verified",
        )
        for i, kw in enumerate(task.keywords[:3], start=1)
    ]
    repos = [
        RepositoryEvidence(
            evidence_id="r1",
            repository=f"example/{task.id}-repo",
            source_url=f"https://github.com/example/{task.id}-repo",
            description=f"Open-source implementation for {task.keywords[0]}",
            architecture_summary="Modular pipeline with training and evaluation scripts",
            verification_status="verified",
        )
    ]
    experiment = ExperimentPlan(
        objective=f"Validate {task.keywords[0]} approach",
        hypotheses=[f"{task.keywords[0]} improves over baseline"],
        datasets=["Public benchmark suite"],
        baselines=["Standard baseline"],
        proposed_pipeline=["Data prep", "Train", "Evaluate"],
        evaluation_metrics=["Accuracy", "F1"],
    )
    reviews = [
        ReviewFinding(
            claim=f"{task.keywords[0]} is effective",
            related_evidence_ids=["p1"],
            status="partially_supported",
            reason="Evidence from abstract-level sources only",
            recommended_action="Add full-text verification",
        )
    ]
    return build_task_artifacts(plan, papers, repos, experiment, reviews)


def _fixture_artifacts(task: TaskSpec) -> dict[str, str]:
    plan = ResearchPlan(task_id=task.id, title=task.id, objective="fixture")
    return build_task_artifacts(
        plan,
        [
            PaperEvidence(
                evidence_id="p1",
                title="Fixture",
                source_url="https://arxiv.org/abs/0000.00001",
            )
        ],
        [
            RepositoryEvidence(
                evidence_id="r1",
                repository="org/fixture",
                source_url="https://github.com/org/fixture",
            )
        ],
        ExperimentPlan(objective="fixture"),
        [],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ScholarFlow benchmark runner")
    parser.add_argument(
        "--mode",
        choices=["fixture", "golden", "artifacts"],
        default="golden",
        help="fixture=minimal; golden=realistic demo; artifacts=score output dirs",
    )
    parser.add_argument("--tasks", default=str(Path(__file__).parent / "benchmark_tasks.json"))
    parser.add_argument("--artifacts-root", default=str(Path(__file__).parent / "results"))
    parser.add_argument("--output-json", default=str(Path(__file__).parent / "reports" / "latest.json"))
    parser.add_argument("--output-md", default=str(Path(__file__).parent / "reports" / "latest.md"))
    args = parser.parse_args()

    tasks = load_task_specs(Path(args.tasks))

    if args.mode == "artifacts":

        def loader(task: TaskSpec) -> dict[str, str]:
            task_dir = Path(args.artifacts_root) / task.id
            if not task_dir.exists():
                raise FileNotFoundError(f"Missing artifacts dir: {task_dir}")
            return load_artifacts_from_dir(task_dir)

    elif args.mode == "golden":
        loader = _golden_artifacts
    else:
        loader = _fixture_artifacts

    report = run_benchmark(
        tasks,
        loader,
        mode=args.mode,
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tasks_file": args.tasks,
        },
    )

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps({"summary": resume_bullet_summary(report), "json": str(out_json), "markdown": str(out_md)}, indent=2))


if __name__ == "__main__":
    main()
