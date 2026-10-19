"""Frozen outcome enums and résumé-metric formulas (Phase 6).

Do NOT change these definitions after a scored run to make résumé targets look better.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable


class Outcome(str, Enum):
    """Mutually exclusive per-task outcomes."""

    succeeded = "succeeded"
    partial_succeeded = "partial_succeeded"
    correct_refuse = "correct_refuse"
    failed = "failed"
    infra_error = "infra_error"


# Résumé targets (aspirational — report measured values; never rewrite criteria).
RESUME_E2E_COMPLETION_TARGET = 0.90
RESUME_SCHEMA_PASS_TARGET = 0.97

# JSON artifact files counted in schema_pass_rate denominator when expected.
SCHEMA_JSON_FILES = (
    "research_plan.json",
    "paper_evidence.json",
    "repository_evidence.json",
    "evidence_review.json",
    "sources.json",
)

REQUIRED_NINE = (
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


def e2e_completion_rate(outcomes: Iterable[str | Outcome], *, expected_total: int = 10) -> float:
    """(# e2e outcomes == succeeded) / expected_total.

    Denominator is fixed to the suite size (default 10). Missing/infra still count
    in the denominator. partial_succeeded and correct_refuse do NOT count as success.

    This is the résumé「端到端完成率」. It is NOT the same as result correctness
    (outcome matches expect_outcome), which may be 100% when a task correctly refuses.
    """
    if expected_total <= 0:
        return 0.0
    ok = sum(1 for o in outcomes if Outcome(o) == Outcome.succeeded)
    return ok / float(expected_total)


def result_correctness_rate(
    results: Iterable[dict],
    *,
    expected_total: int | None = None,
) -> float:
    """(# tasks where outcome == expect_outcome) / N.

    Pre-defined success standard for「结果正确率」: matching the task's declared
    expect_outcome (including correct_refuse / verified failure paths).
    """
    rows = list(results)
    n = expected_total if expected_total is not None else len(rows)
    if n <= 0:
        return 0.0
    matched = sum(1 for r in rows if r.get("outcome") == r.get("expect_outcome"))
    return matched / float(n)


def offline_pass_rate(outcomes: Iterable[str | Outcome], *, expected_total: int = 20) -> float:
    """Offline pass = succeeded OR correct_refuse (when that was the expected path).

    For reporting simplicity, callers should pass only tasks whose expect_outcome
    matched. This helper counts succeeded+correct_refuse over expected_total.
    """
    if expected_total <= 0:
        return 0.0
    ok = sum(
        1
        for o in outcomes
        if Outcome(o) in {Outcome.succeeded, Outcome.correct_refuse, Outcome.partial_succeeded}
    )
    return ok / float(expected_total)


def schema_pass_rate(*, passed: int, total: int) -> float:
    """passed / total schema validation events (Pydantic validate_json_artifact)."""
    if total <= 0:
        return 0.0
    return passed / float(total)


def bucket_counts(outcomes: Iterable[str | Outcome]) -> dict[str, int]:
    counts = {o.value: 0 for o in Outcome}
    for raw in outcomes:
        counts[Outcome(raw).value] += 1
    return counts


def summarize_rates(
    *,
    e2e_outcomes: list[str],
    offline_outcomes: list[str],
    schema_passed: int,
    schema_total: int,
    e2e_expected: int = 10,
    offline_expected: int = 20,
) -> dict[str, Any]:
    return {
        "e2e_completion_rate": e2e_completion_rate(e2e_outcomes, expected_total=e2e_expected),
        "e2e_completion_target": RESUME_E2E_COMPLETION_TARGET,
        "e2e_meets_resume_target": e2e_completion_rate(e2e_outcomes, expected_total=e2e_expected)
        >= RESUME_E2E_COMPLETION_TARGET,
        "offline_pass_rate": offline_pass_rate(offline_outcomes, expected_total=offline_expected),
        "schema_pass_rate": schema_pass_rate(passed=schema_passed, total=schema_total),
        "schema_pass_target": RESUME_SCHEMA_PASS_TARGET,
        "schema_meets_resume_target": schema_pass_rate(passed=schema_passed, total=schema_total)
        >= RESUME_SCHEMA_PASS_TARGET,
        "e2e_buckets": bucket_counts(e2e_outcomes),
        "offline_buckets": bucket_counts(offline_outcomes),
        "schema_passed": schema_passed,
        "schema_total": schema_total,
        "note": (
            "Résumé 90%/97% are targets, not guaranteed results. "
            "Do not change success criteria after the run."
        ),
    }
