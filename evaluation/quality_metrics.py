"""Quality-layer metrics for E2E ScholarFlow benchmark scoring."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from evaluation.metrics import MetricResult

_PLACEHOLDER_PATTERNS = (
    "example.com",
    "0000.00001",
    "org/fixture",
    "your-",
    "placeholder",
    "lorem ipsum",
)

_VALID_PAPER_HOSTS = ("arxiv.org", "doi.org", "openreview.net", "aclanthology.org")
_VALID_REPO_HOSTS = ("github.com", "gitlab.com", "huggingface.co")


def _combined_text(artifacts: dict[str, str]) -> str:
    parts = [
        artifacts.get("research_report.md", ""),
        artifacts.get("experiment_plan.md", ""),
        artifacts.get("paper_evidence.json", ""),
        artifacts.get("repository_evidence.json", ""),
    ]
    return "\n".join(parts).lower()


def topic_relevance(artifacts: dict[str, str], keywords: list[str]) -> MetricResult:
    if not keywords:
        return MetricResult(name="topic_relevance", score=1.0, details={"keywords": [], "hits": 0})
    text = _combined_text(artifacts)
    hits = sum(1 for kw in keywords if kw.lower() in text)
    score = hits / len(keywords)
    return MetricResult(
        name="topic_relevance",
        score=score,
        details={"keywords": keywords, "hits": hits, "total_keywords": len(keywords)},
    )


def url_validity(artifacts: dict[str, str]) -> MetricResult:
    papers = json.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])
    valid = 0
    total = 0
    invalid: list[str] = []
    for paper in papers:
        total += 1
        url = paper.get("source_url", "")
        host = urlparse(url).netloc.lower()
        if any(h in host for h in _VALID_PAPER_HOSTS):
            valid += 1
        else:
            invalid.append(url)
    for repo in repos:
        total += 1
        url = repo.get("source_url", "")
        host = urlparse(url).netloc.lower()
        if any(h in host for h in _VALID_REPO_HOSTS):
            valid += 1
        else:
            invalid.append(url)
    score = valid / total if total else 0.0
    return MetricResult(
        name="url_validity",
        score=score,
        details={"valid": valid, "total": total, "invalid_samples": invalid[:5]},
    )


def anti_fabrication_heuristic(artifacts: dict[str, str]) -> MetricResult:
    blob = _combined_text(artifacts)
    hits = [p for p in _PLACEHOLDER_PATTERNS if p in blob]
    score = 1.0 if not hits else max(0.0, 1.0 - len(hits) * 0.25)
    return MetricResult(name="anti_fabrication_heuristic", score=score, details={"placeholder_hits": hits})


def verification_rate(artifacts: dict[str, str]) -> MetricResult:
    papers = json.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])
    items = papers + repos
    if not items:
        return MetricResult(name="verification_rate", score=0.0, details={"verified": 0, "total": 0})
    verified_status = {"verified", "partially_verified"}
    verified = sum(1 for item in items if item.get("verification_status") in verified_status)
    return MetricResult(
        name="verification_rate",
        score=verified / len(items),
        details={"verified": verified, "total": len(items)},
    )


def review_substantive(artifacts: dict[str, str]) -> MetricResult:
    reviews = json.loads(artifacts.get("evidence_review.json", '{"items": []}')).get("items", [])
    if not reviews:
        return MetricResult(name="review_substantive", score=0.0, details={"substantive": 0, "total": 0})
    substantive = sum(
        1
        for r in reviews
        if len(r.get("claim", "").strip()) > 10 and len(r.get("reason", "").strip()) > 10
    )
    return MetricResult(
        name="review_substantive",
        score=substantive / len(reviews),
        details={"substantive": substantive, "total": len(reviews)},
    )


def evidence_richness(artifacts: dict[str, str]) -> MetricResult:
    papers = json.loads(artifacts.get("paper_evidence.json", '{"items": []}')).get("items", [])
    repos = json.loads(artifacts.get("repository_evidence.json", '{"items": []}')).get("items", [])
    paper_rich = sum(
        1
        for p in papers
        if p.get("key_findings") or p.get("methodology") or p.get("research_problem")
    )
    repo_rich = sum(1 for r in repos if r.get("architecture_summary") or r.get("description"))
    total = len(papers) + len(repos)
    rich = paper_rich + repo_rich
    return MetricResult(
        name="evidence_richness",
        score=rich / total if total else 0.0,
        details={"rich_items": rich, "total_items": total},
    )


def keyword_in_plan(artifacts: dict[str, str], keywords: list[str]) -> MetricResult:
    plan = json.loads(artifacts.get("research_plan.json", "{}"))
    plan_text = json.dumps(plan, ensure_ascii=False).lower()
    hits = sum(1 for kw in keywords if kw.lower() in plan_text)
    score = hits / len(keywords) if keywords else 1.0
    return MetricResult(
        name="keyword_in_plan",
        score=score,
        details={"hits": hits, "keywords": keywords},
    )


def e2e_pass_gate(metrics: list[MetricResult], thresholds: dict[str, float] | None = None) -> MetricResult:
    """Hard gate for resume-grade E2E success."""
    thresholds = thresholds or {
        "artifact_completeness": 1.0,
        "schema_validity": 1.0,
        "url_validity": 0.8,
        "topic_relevance": 0.5,
    }
    by_name = {m.name: m.score for m in metrics}
    failed = [name for name, min_score in thresholds.items() if by_name.get(name, 0.0) < min_score]
    passed = not failed
    return MetricResult(
        name="e2e_pass_gate",
        score=1.0 if passed else 0.0,
        details={"passed": passed, "failed_gates": failed, "thresholds": thresholds},
    )
