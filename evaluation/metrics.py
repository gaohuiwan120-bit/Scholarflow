"""ScholarFlow evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


@dataclass
class MetricResult:
    name: str
    score: float
    details: dict[str, Any]


def artifact_completeness(artifacts: dict[str, str]) -> MetricResult:
    present = [name for name in REQUIRED_ARTIFACTS if name in artifacts and artifacts[name].strip()]
    score = len(present) / len(REQUIRED_ARTIFACTS)
    return MetricResult(
        name="artifact_completeness",
        score=score,
        details={"present": present, "missing": [a for a in REQUIRED_ARTIFACTS if a not in present]},
    )


def schema_validity(valid_count: int, total: int) -> MetricResult:
    score = valid_count / total if total else 0.0
    return MetricResult(name="schema_validity", score=score, details={"valid": valid_count, "total": total})


def evidence_coverage(paper_count: int, repo_count: int, min_papers: int = 3, min_repos: int = 1) -> MetricResult:
    paper_score = min(1.0, paper_count / min_papers) if min_papers else 1.0
    repo_score = min(1.0, repo_count / min_repos) if min_repos else 1.0
    score = (paper_score + repo_score) / 2
    return MetricResult(
        name="evidence_coverage",
        score=score,
        details={"paper_count": paper_count, "repo_count": repo_count},
    )


def report_structure(report_md: str) -> MetricResult:
    required_sections = ["## Objective", "## Key Paper Findings", "## Experiment Plan Summary"]
    hits = sum(1 for section in required_sections if section in report_md)
    score = hits / len(required_sections)
    return MetricResult(name="report_structure", score=score, details={"sections_found": hits})


def matrix_row_consistency(artifacts: dict[str, str]) -> MetricResult:
    import csv
    import io
    import json

    papers = json.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])
    paper_rows = list(csv.DictReader(io.StringIO(artifacts.get("paper_matrix.csv", ""))))
    repo_rows = list(csv.DictReader(io.StringIO(artifacts.get("repository_matrix.csv", ""))))
    paper_ok = len(paper_rows) == len(papers)
    repo_ok = len(repo_rows) == len(repos)
    score = (int(paper_ok) + int(repo_ok)) / 2
    return MetricResult(
        name="matrix_row_consistency",
        score=score,
        details={"paper_rows": len(paper_rows), "paper_items": len(papers), "repo_rows": len(repo_rows), "repo_items": len(repos)},
    )


def source_traceability(artifacts: dict[str, str]) -> MetricResult:
    import json

    sources = json.loads(artifacts.get("sources.json", '{"items": []}')).get("items", [])
    papers = json.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])
    expected = len(papers) + len(repos)
    score = min(1.0, len(sources) / expected) if expected else 1.0
    return MetricResult(name="source_traceability", score=score, details={"sources": len(sources), "expected": expected})


def review_coverage(artifacts: dict[str, str]) -> MetricResult:
    import json

    reviews = json.loads(artifacts.get("evidence_review.json", '{"items": []}')).get("items", [])
    score = 1.0 if reviews else 0.5
    return MetricResult(name="review_coverage", score=score, details={"review_count": len(reviews)})


def experiment_plan_presence(artifacts: dict[str, str]) -> MetricResult:
    text = artifacts.get("experiment_plan.md", "")
    sections = ["## Hypotheses", "## Proposed Pipeline", "## Risks"]
    hits = sum(1 for s in sections if s in text)
    return MetricResult(name="experiment_plan_presence", score=hits / len(sections), details={"sections_found": hits})


def json_parseability(artifacts: dict[str, str]) -> MetricResult:
    import json

    json_names = [n for n in REQUIRED_ARTIFACTS if n.endswith(".json")]
    ok = 0
    for name in json_names:
        try:
            json.loads(artifacts[name])
            ok += 1
        except Exception:
            pass
    return MetricResult(name="json_parseability", score=ok / len(json_names), details={"parsed": ok, "total": len(json_names)})


def csv_parseability(artifacts: dict[str, str]) -> MetricResult:
    import csv
    import io

    csv_names = [n for n in REQUIRED_ARTIFACTS if n.endswith(".csv")]
    ok = 0
    for name in csv_names:
        try:
            rows = list(csv.DictReader(io.StringIO(artifacts[name])))
            if rows or artifacts[name].strip():
                ok += 1
        except Exception:
            pass
    return MetricResult(name="csv_parseability", score=ok / len(csv_names), details={"parsed": ok, "total": len(csv_names)})


def markdown_nonempty(artifacts: dict[str, str]) -> MetricResult:
    md_names = [n for n in REQUIRED_ARTIFACTS if n.endswith(".md")]
    ok = sum(1 for n in md_names if len(artifacts.get(n, "").strip()) > 50)
    return MetricResult(name="markdown_nonempty", score=ok / len(md_names), details={"nonempty": ok, "total": len(md_names)})


def aggregate_score(metrics: list[MetricResult]) -> float:
    if not metrics:
        return 0.0
    return sum(m.score for m in metrics) / len(metrics)
