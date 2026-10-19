#!/usr/bin/env python3
"""Unified ScholarFlow Agent Bench entry (Phase 6).

Suites:
  offline  — 20 offline Agent tasks (FastAPI / RAG pipeline)
  e2e      — 10 E2E benchmarks (FastAPI TestClient)
  rag      — existing 50-question RAG QA eval (subprocess)
  sandbox  — process_jail (+ optional docker) verify scripts
  golden   — compare / update golden snapshot from last offline+e2e
  all      — offline + e2e + sandbox (+ rag if --with-rag)

Examples:
  python evaluation/run_agent_bench.py --suite offline
  python evaluation/run_agent_bench.py --suite e2e --data-mode fixture
  python evaluation/run_agent_bench.py --suite all --update-golden
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "scholarflow-api"))
sys.path.insert(0, str(ROOT / "backend" / "packages" / "harness"))


def _run_rag_suite() -> dict[str, Any]:
    script = ROOT / "evaluation" / "run_rag_qa_eval.py"
    if not script.is_file():
        return {"ok": False, "error": "run_rag_qa_eval.py missing"}
    out_json = ROOT / "evaluation" / "reports" / "agent-bench-rag-qa.json"
    cmd = [sys.executable, str(script), "--output-json", str(out_json)]
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "report": str(out_json) if out_json.is_file() else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _run_sandbox_suite() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, script in (
        ("process_jail", ROOT / "scripts" / "verify_scholar_sandbox.py"),
        ("docker", ROOT / "scripts" / "verify_scholar_sandbox_docker.py"),
    ):
        if not script.is_file():
            results[name] = {"ok": False, "error": "script missing"}
            continue
        try:
            proc = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=180,
            )
            results[name] = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-1500:],
                "stderr_tail": (proc.stderr or "")[-800:],
            }
        except Exception as exc:  # noqa: BLE001
            results[name] = {"ok": False, "error": str(exc)}
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="ScholarFlow Agent Bench (Phase 6)")
    parser.add_argument(
        "--suite",
        choices=["offline", "e2e", "rag", "sandbox", "golden", "all"],
        default="all",
    )
    parser.add_argument("--data-mode", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--limit", type=int, default=0, help="Limit tasks per suite (debug)")
    parser.add_argument("--with-rag", action="store_true", help="Include RAG-50 when suite=all")
    parser.add_argument("--update-golden", action="store_true")
    parser.add_argument(
        "--output-json",
        default="",
        help="Default: agent-bench-latest.json; golden suite alone -> agent-bench-golden-compare.json",
    )
    parser.add_argument(
        "--output-md",
        default="",
        help="Markdown sibling of --output-json",
    )
    args = parser.parse_args()
    if not args.output_json:
        if args.suite == "golden" and not args.update_golden:
            args.output_json = str(
                ROOT / "evaluation" / "reports" / "agent-bench-golden-compare.json"
            )
        else:
            args.output_json = str(ROOT / "evaluation" / "reports" / "agent-bench-latest.json")
    if not args.output_md:
        args.output_md = str(Path(args.output_json).with_suffix(".md"))

    from evaluation.agent_bench.api_client import get_client, git_meta, prepare_env
    from evaluation.agent_bench.golden import (
        compare_snapshots,
        extract_snapshot,
        load_snapshot,
        save_snapshot,
    )
    from evaluation.agent_bench.report import build_report, write_reports

    git = git_meta(ROOT)
    extras: dict[str, Any] = {}
    offline: list[dict[str, Any]] = []
    e2e: list[dict[str, Any]] = []
    config = {
        "data_mode": args.data_mode,
        "timeout": args.timeout,
        "limit": args.limit,
        "suite": args.suite,
        "update_golden": args.update_golden,
    }

    work = Path(tempfile.mkdtemp(prefix="sf-agent-bench-"))
    prepare_env(work)

    need_api = args.suite in {"offline", "e2e", "all", "golden"}
    client = None
    if need_api and args.suite != "golden":
        client = get_client()

    if args.suite in {"offline", "all"}:
        from evaluation.agent_bench.offline_runner import run_offline_suite

        assert client is not None
        offline = run_offline_suite(
            client, data_mode=args.data_mode, timeout=args.timeout, limit=args.limit
        )

    if args.suite in {"e2e", "all"}:
        from evaluation.agent_bench.e2e_runner import run_e2e_suite

        assert client is not None
        e2e = run_e2e_suite(
            client, data_mode=args.data_mode, timeout=args.timeout, limit=args.limit
        )

    if args.suite == "rag" or (args.suite == "all" and args.with_rag):
        extras["rag"] = _run_rag_suite()

    if args.suite in {"sandbox", "all"}:
        extras["sandbox"] = _run_sandbox_suite()

    # Golden: build from current offline+e2e; if suite=golden only, require existing results file
    if args.suite in {"golden", "all"} or args.update_golden:
        if not offline and not e2e and args.suite == "golden":
            # Re-run both for golden compare
            client = get_client()
            from evaluation.agent_bench.e2e_runner import run_e2e_suite
            from evaluation.agent_bench.offline_runner import run_offline_suite

            offline = run_offline_suite(
                client, data_mode=args.data_mode, timeout=args.timeout, limit=args.limit
            )
            e2e = run_e2e_suite(
                client, data_mode=args.data_mode, timeout=args.timeout, limit=args.limit
            )
        snap = extract_snapshot(list(offline) + list(e2e))
        baseline = load_snapshot()
        if args.update_golden or baseline is None:
            path = save_snapshot(snap)
            extras["golden"] = {
                "updated": True,
                "path": str(path),
                "pass": True,
                "diff_count": 0,
                "diffs": [],
                "note": "snapshot created/updated",
            }
        else:
            cmp = compare_snapshots(baseline, snap)
            extras["golden"] = cmp

    report = build_report(
        suite=args.suite,
        config=config,
        git=git,
        offline=offline,
        e2e=e2e,
        extras=extras,
    )
    write_reports(report, Path(args.output_json), Path(args.output_md))

    rates = report.get("rates") or {}
    print(
        json.dumps(
            {
                "output_json": args.output_json,
                "output_md": args.output_md,
                "e2e_completion_rate": rates.get("e2e_completion_rate"),
                "schema_pass_rate": rates.get("schema_pass_rate"),
                "offline_pass_rate": rates.get("offline_pass_rate"),
                "e2e_meets_resume_target": rates.get("e2e_meets_resume_target"),
                "schema_meets_resume_target": rates.get("schema_meets_resume_target"),
                "golden": (extras.get("golden") or {}).get("pass"),
                "work_root": str(work),
            },
            indent=2,
        )
    )

    # Exit non-zero if any offline/e2e mismatch (infra_error also fails CI)
    mismatches = [
        r
        for r in list(offline) + list(e2e)
        if r.get("outcome") != r.get("expect_outcome")
    ]
    golden_fail = extras.get("golden") and extras["golden"].get("pass") is False
    return 1 if mismatches or golden_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
