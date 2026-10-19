#!/usr/bin/env python3
"""Compare baseline vs full_rag (and optional ablations) from latest summary JSONs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "evaluation" / "reports" / "rag_qa"


def load_summary(profile: str) -> dict:
    path = REPORT / f"{profile}_latest_summary.json"
    if not path.is_file():
        raise SystemExit(f"missing {path}; run run_rag_qa_eval.py --profile {profile} first")
    return json.loads(path.read_text(encoding="utf-8"))


def mcp_reduction(baseline_calls: float, full_calls: float) -> float | None:
    if baseline_calls <= 0:
        return None
    return (baseline_calls - full_calls) / baseline_calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="baseline")
    parser.add_argument("--full", default="full_rag")
    args = parser.parse_args()
    base = load_summary(args.baseline)
    full = load_summary(args.full)

    # Prefer needs_mcp call totals for the "same-topic MCP reduction" story
    b_mcp = float(base.get("mcp_calls_on_needs_mcp_total") or base.get("mcp_calls_total") or 0)
    f_mcp = float(full.get("mcp_calls_on_needs_mcp_total") or full.get("mcp_calls_total") or 0)
    red = mcp_reduction(b_mcp, f_mcp)

    targets = {
        "faithfulness": 0.84,
        "top5_hit_rate": 0.82,
        "citation_accuracy": 0.91,
        "mcp_reduction": 0.77,
    }
    comparison = {
        "baseline_profile": args.baseline,
        "full_profile": args.full,
        "baseline": {
            "faithfulness_mean": base.get("faithfulness_mean"),
            "top5_hit_rate": base.get("top5_hit_rate"),
            "citation_accuracy_mean": base.get("citation_accuracy_mean"),
            "mcp_calls_on_needs_mcp_total": b_mcp,
            "ce_meta": base.get("ce_meta"),
        },
        "full": {
            "faithfulness_mean": full.get("faithfulness_mean"),
            "top5_hit_rate": full.get("top5_hit_rate"),
            "citation_accuracy_mean": full.get("citation_accuracy_mean"),
            "mcp_calls_on_needs_mcp_total": f_mcp,
            "ce_meta": full.get("ce_meta"),
        },
        "deltas": {
            "faithfulness": (full.get("faithfulness_mean") or 0) - (base.get("faithfulness_mean") or 0),
            "top5_hit_rate": (full.get("top5_hit_rate") or 0) - (base.get("top5_hit_rate") or 0),
            "citation_accuracy": (full.get("citation_accuracy_mean") or 0)
            - (base.get("citation_accuracy_mean") or 0),
            "mcp_reduction_ratio": red,
        },
        "resume_targets": targets,
        "target_met": {
            "faithfulness": (full.get("faithfulness_mean") or 0) >= targets["faithfulness"],
            "top5_hit_rate": (full.get("top5_hit_rate") or 0) >= targets["top5_hit_rate"],
            "citation_accuracy": (full.get("citation_accuracy_mean") or 0)
            >= targets["citation_accuracy"],
            "mcp_reduction": (red is not None and red >= targets["mcp_reduction"]),
        },
        "note": "All values measured from eval runs; targets are not written into raw metrics.",
    }
    out = REPORT / "comparison_latest.json"
    out.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(comparison, ensure_ascii=False, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
