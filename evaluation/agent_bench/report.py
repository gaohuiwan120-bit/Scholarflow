"""JSON + Markdown report builders for Agent Bench."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.agent_bench.outcomes import (
    RESUME_E2E_COMPLETION_TARGET,
    RESUME_SCHEMA_PASS_TARGET,
    result_correctness_rate,
    summarize_rates,
)


def build_report(
    *,
    suite: str,
    config: dict[str, Any],
    git: dict[str, Any],
    offline: list[dict[str, Any]] | None = None,
    e2e: list[dict[str, Any]] | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    offline = offline or []
    e2e = e2e or []
    schema_passed = 0
    schema_total = 0
    for r in list(offline) + list(e2e):
        sc = r.get("schema_checks") or {}
        schema_passed += int(sc.get("passed") or 0)
        schema_total += int(sc.get("total") or 0)

    # Offline pass = outcome matches expect_outcome
    offline_matched = [
        r["outcome"]
        for r in offline
        if r.get("outcome") == r.get("expect_outcome")
    ]
    # For rate denominator use suite sizes
    offline_outcomes_for_rate = [
        r["outcome"] if r.get("outcome") == r.get("expect_outcome") else "failed"
        for r in offline
    ]
    # Prefer counting matches: rebuild as succeeded when matched
    offline_rate_outcomes = []
    for r in offline:
        if r.get("outcome") == r.get("expect_outcome"):
            offline_rate_outcomes.append(
                "succeeded"
                if r["outcome"] != "correct_refuse"
                else "correct_refuse"
            )
        else:
            offline_rate_outcomes.append("failed")

    rates = summarize_rates(
        e2e_outcomes=[r["outcome"] for r in e2e],
        offline_outcomes=offline_rate_outcomes,
        schema_passed=schema_passed,
        schema_total=schema_total,
        e2e_expected=10 if e2e else (0 if suite == "offline" else 10),
        offline_expected=20 if offline else (0 if suite == "e2e" else 20),
    )
    # When suite is e2e-only, don't force offline denom
    if not offline:
        rates["offline_pass_rate"] = None
        rates["offline_buckets"] = {}
    if not e2e:
        rates["e2e_completion_rate"] = None
        rates["e2e_buckets"] = {}
        rates["e2e_meets_resume_target"] = None

    # Honest offline pass rate: matched / len(offline)
    if offline:
        rates["offline_pass_rate"] = len(offline_matched) / float(len(offline))
        rates["offline_matched"] = len(offline_matched)
        rates["offline_total"] = len(offline)

    # Dual rates (frozen definitions — do not redefine after scoring):
    # - e2e_completion_rate: outcome==succeeded only (résumé 完成率)
    # - e2e_result_correctness_rate: outcome==expect_outcome (含正确拒答)
    if e2e:
        rates["e2e_result_correctness_rate"] = result_correctness_rate(e2e, expected_total=len(e2e))
    if offline:
        rates["offline_result_correctness_rate"] = result_correctness_rate(
            offline, expected_total=len(offline)
        )

    return {
        "suite": suite,
        "suite_version": "agent-bench-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git.get("git_commit"),
        "git_dirty": git.get("git_dirty"),
        "config": config,
        "rates": rates,
        "resume_targets": {
            "e2e_completion_rate": RESUME_E2E_COMPLETION_TARGET,
            "schema_pass_rate": RESUME_SCHEMA_PASS_TARGET,
            "note": "Targets only; measured rates above are authoritative.",
        },
        "offline_results": offline,
        "e2e_results": e2e,
        "extras": extras or {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    rates = report.get("rates") or {}
    lines = [
        "# ScholarFlow Agent Bench Report",
        "",
        f"- Suite: `{report.get('suite')}` / `{report.get('suite_version')}`",
        f"- Timestamp: {report.get('timestamp')}",
        f"- Git: `{report.get('git_commit')}` dirty={report.get('git_dirty')}",
        f"- Data mode: `{(report.get('config') or {}).get('data_mode')}`",
        "",
        "## Rates",
        "",
        f"| Metric | Value | Résumé target | Meets |",
        f"|--------|-------|---------------|-------|",
        f"| E2E completion | {_fmt(rates.get('e2e_completion_rate'))} | {RESUME_E2E_COMPLETION_TARGET:.0%} | {rates.get('e2e_meets_resume_target')} |",
        f"| Schema pass | {_fmt(rates.get('schema_pass_rate'))} | {RESUME_SCHEMA_PASS_TARGET:.0%} | {rates.get('schema_meets_resume_target')} |",
        f"| Offline pass | {_fmt(rates.get('offline_pass_rate'))} | (match expect) | — |",
        "",
        f"Schema events: {rates.get('schema_passed')}/{rates.get('schema_total')}",
        "",
        "## Offline tasks",
        "",
    ]
    lines.extend(_task_table(report.get("offline_results") or []))
    lines.extend(["", "## E2E tasks", ""])
    lines.extend(_task_table(report.get("e2e_results") or []))

    failed = [
        r
        for r in list(report.get("offline_results") or []) + list(report.get("e2e_results") or [])
        if r.get("outcome") != r.get("expect_outcome")
    ]
    if failed:
        lines.extend(["", "## Failures / mismatches", ""])
        for r in failed:
            bad = [a for a in (r.get("assertions") or []) if not a.get("ok")]
            lines.append(
                f"- **{r['task_id']}** expect={r.get('expect_outcome')} got={r.get('outcome')} "
                f"error={r.get('error')} bad={bad}"
            )

    extras = report.get("extras") or {}
    if extras.get("golden"):
        g = extras["golden"]
        lines.extend(
            [
                "",
                "## Golden regression",
                "",
                f"- pass={g.get('pass')} diffs={g.get('diff_count')}",
            ]
        )
        for d in (g.get("diffs") or [])[:20]:
            lines.append(f"- {d}")

    if extras.get("rag") or extras.get("sandbox"):
        lines.extend(["", "## Extras", "", f"```json\n{json.dumps({k: extras[k] for k in extras if k in ('rag', 'sandbox')}, indent=2, ensure_ascii=False)[:4000]}\n```"])

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Legacy `run_benchmark.py --mode golden` synthetic scores are **not** included in E2E completion.",
            "- Do not rewrite success criteria after the run to meet résumé targets.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.1%}"
    return str(v)


def _task_table(results: list[dict[str, Any]]) -> list[str]:
    if not results:
        return ["_(none)_", ""]
    lines = [
        "| ID | Outcome | Expect | Status | ms |",
        "|----|---------|--------|--------|----|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('task_id')} | {r.get('outcome')} | {r.get('expect_outcome')} | "
            f"{r.get('status')} | {r.get('duration_ms')} |"
        )
    return lines


def write_reports(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
