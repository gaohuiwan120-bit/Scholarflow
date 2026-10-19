#!/usr/bin/env python3
"""Compare two ScholarFlow benchmark JSON reports (before/after optimization)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare benchmark runs")
    parser.add_argument("baseline", help="Baseline report JSON path")
    parser.add_argument("candidate", help="Candidate report JSON path")
    parser.add_argument("--output", default="", help="Optional markdown output path")
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    candidate = json.loads(Path(args.candidate).read_text(encoding="utf-8"))

    b_map = {r["task_id"]: r for r in baseline["results"]}
    c_map = {r["task_id"]: r for r in candidate["results"]}

    lines = [
        "# ScholarFlow Benchmark Comparison",
        "",
        f"| Metric | Baseline | Candidate | Delta |",
        f"|--------|----------|-----------|-------|",
        f"| Average score | {baseline['average_score']:.3f} | {candidate['average_score']:.3f} | {candidate['average_score'] - baseline['average_score']:+.3f} |",
        f"| E2E pass rate | {baseline['e2e_pass_rate']:.1%} | {candidate['e2e_pass_rate']:.1%} | {(candidate['e2e_pass_rate'] - baseline['e2e_pass_rate'])*100:+.1f}pp |",
        "",
        "## Per-Task Delta",
        "",
        "| Task | Baseline | Candidate | Delta |",
        "|------|----------|-----------|-------|",
    ]

    for task_id in sorted(set(b_map) | set(c_map)):
        b_score = b_map.get(task_id, {}).get("score", 0.0)
        c_score = c_map.get(task_id, {}).get("score", 0.0)
        lines.append(f"| {task_id} | {b_score:.3f} | {c_score:.3f} | {c_score - b_score:+.3f} |")

    md = "\n".join(lines)
    print(md)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
