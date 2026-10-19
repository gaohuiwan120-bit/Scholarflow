#!/usr/bin/env python3
"""Run fixed 50-question RAG eval for baseline vs full_rag profiles.

Profiles:
  baseline  — hybrid-score rerank, no MCP auto loop
  full_rag  — Cross-Encoder rerank + source constraints (+ optional live MCP)
  no_ce     — RRF + hybrid-score, MCP off (ablation)
  no_mcp    — Cross-Encoder on, MCP off (ablation)

Never writes resume target numbers into result files.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(ROOT))

from evaluation.rag_qa_metrics import (  # noqa: E402
    citation_accuracy_from_report,
    faithfulness,
    mcp_calls_in_result,
    refuse_ok,
    summarize,
    top5_hit,
)

SAMPLE = ROOT / "docs" / "scholar-flow" / "samples" / "rag-test-001"
QA_PATH = ROOT / "evaluation" / "rag_qa" / "v1" / "questions.json"
CE_DIR = ROOT / "evaluation" / "models" / "ce-minilm"


def _profile_env(profile: str) -> dict[str, str]:
    env: dict[str, str] = {}
    if profile == "baseline":
        env["SCHOLAR_RAG_RERANK_MODEL"] = "hybrid-score"
        env["ENABLE_MCP"] = "0"
    elif profile == "full_rag":
        env["SCHOLAR_RAG_RERANK_MODEL"] = "cross-encoder"
        env["SCHOLAR_RAG_CE_MODEL_DIR"] = str(CE_DIR)
        env["ENABLE_MCP"] = os.getenv("SCHOLARFLOW_LIVE_MCP", "0")
    elif profile == "no_ce":
        env["SCHOLAR_RAG_RERANK_MODEL"] = "hybrid-score"
        env["ENABLE_MCP"] = "0"
    elif profile == "no_mcp":
        env["SCHOLAR_RAG_RERANK_MODEL"] = "cross-encoder"
        env["SCHOLAR_RAG_CE_MODEL_DIR"] = str(CE_DIR)
        env["ENABLE_MCP"] = "0"
    elif profile == "stub_ce":
        env["SCHOLAR_RAG_RERANK_MODEL"] = "stub-cross-encoder"
        env["ENABLE_MCP"] = "0"
    elif profile == "cold_mcp":
        # No useful local corpus — forces MCP path for call-count baseline
        env["SCHOLAR_RAG_RERANK_MODEL"] = "hybrid-score"
        env["ENABLE_MCP"] = "1"
        env["COLD_INDEX"] = "1"
        env["MCP_MOCK"] = "1"
    elif profile == "full_rag_mcp_mock":
        # Indexed corpus + mock MCP (offline comparable call counts)
        env["SCHOLAR_RAG_RERANK_MODEL"] = "cross-encoder"
        env["SCHOLAR_RAG_CE_MODEL_DIR"] = str(CE_DIR)
        env["ENABLE_MCP"] = "1"
        env["MCP_MOCK"] = "1"
    else:
        raise SystemExit(f"unknown profile: {profile}")
    return env


def _make_mcp_caller():
    """Live MCP via scholarflow stdio client; or deterministic mock for offline call counts."""
    if os.environ.get("MCP_MOCK") == "1":

        def mock_caller(name: str, arguments: dict):
            q = str((arguments or {}).get("query") or "topic")
            if name == "search_academic_papers":
                return {
                    "items": [
                        {
                            "evidence_id": f"paper-mcp-mock-{abs(hash(q)) % 10000}",
                            "title": f"Mock paper about {q[:80]}",
                            "identifier": "0000.00000",
                            "source_url": "https://arxiv.org/abs/0000.00000",
                            "research_problem": q,
                            "key_findings": [q[:120]],
                            "verification_status": "verified",
                        }
                    ]
                }
            if name == "get_repository_overview":
                return {
                    "evidence_id": "repo-mcp-mock",
                    "repository": "example/mock",
                    "source_url": "https://github.com/example/mock",
                    "description": q if False else "mock repo",
                    "key_modules": ["src/"],
                    "verification_status": "verified",
                }
            raise RuntimeError(f"unexpected tool {name}")

        return mock_caller

    api = ROOT / "apps" / "scholarflow-api"
    if str(api) not in sys.path:
        sys.path.insert(0, str(api))
    from scholarflow_api.mcp.client import call_mcp_tool

    def caller(name: str, arguments: dict):
        return call_mcp_tool(name, arguments, timeout_seconds=90.0)

    return caller


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        default="baseline",
        choices=[
            "baseline",
            "full_rag",
            "no_ce",
            "no_mcp",
            "stub_ce",
            "cold_mcp",
            "full_rag_mcp_mock",
        ],
    )
    parser.add_argument("--limit", type=int, default=0, help="0 = all 50")
    parser.add_argument("--out-dir", default=str(ROOT / "evaluation" / "reports" / "rag_qa"))
    args = parser.parse_args()

    for k, v in _profile_env(args.profile).items():
        os.environ[k] = v

    # Prefer fastembed
    if "SCHOLAR_RAG_BACKEND" not in os.environ:
        try:
            import fastembed  # noqa: F401

            os.environ["SCHOLAR_RAG_BACKEND"] = "fastembed"
        except Exception:
            os.environ["SCHOLAR_RAG_BACKEND"] = "lite"

    from scholarflow.scholar.rag import RagConfig, index_artifacts_dir, rag_answer
    from scholarflow.scholar.rag.cross_encoder import CrossEncoderUnavailable, resolve_rerank_mode

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    index_dir = out_dir / f"index_{args.profile}"
    if index_dir.exists():
        shutil.rmtree(index_dir, ignore_errors=True)
    os.environ["SCHOLAR_RAG_INDEX_DIR"] = str(index_dir)

    cfg = RagConfig.from_env()
    mode = resolve_rerank_mode(cfg.rerank_model)
    ce_meta = {"requested": cfg.rerank_model, "resolved_mode": mode, "is_stub": mode == "stub-cross-encoder"}
    if mode == "cross-encoder":
        try:
            from scholarflow.scholar.rag.cross_encoder import get_cross_encoder

            ce = get_cross_encoder(cfg.rerank_model)
            ce_meta["loaded"] = ce.name if ce else None
            ce_meta["is_stub"] = bool(ce and ce.is_stub)
        except CrossEncoderUnavailable as exc:
            print(f"[ERROR] Cross-Encoder unavailable: {exc}")
            payload = {
                "profile": args.profile,
                "error": str(exc),
                "ce_meta": ce_meta,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            (out_dir / f"{args.profile}_ERROR.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raise SystemExit(2) from exc

    if os.environ.get("COLD_INDEX") == "1":
        print("=== Cold index (skip corpus) for MCP call-count baseline ===")
        info = {
            "upserted": 0,
            "backend": cfg.backend,
            "rerank_model": cfg.rerank_model,
            "embed_model": cfg.embed_model,
            "cold": True,
        }
        cfg.persist_dir.mkdir(parents=True, exist_ok=True)
        (cfg.persist_dir / "corpus.json").write_text("[]", encoding="utf-8")
        (cfg.persist_dir / "vectors.json").write_text("{}", encoding="utf-8")
        (cfg.persist_dir / "bm25_corpus.json").write_text("[]", encoding="utf-8")
    else:
        print("=== Indexing corpus ===")
        info = index_artifacts_dir(SAMPLE, config=cfg, task_id="rag-test-001")
        print(
            json.dumps(
                {k: info.get(k) for k in ("upserted", "backend", "rerank_model", "embed_model")},
                indent=2,
            )
        )

    qa = json.loads(QA_PATH.read_text(encoding="utf-8"))
    questions = qa["questions"]
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]

    enable_mcp = os.environ.get("ENABLE_MCP") == "1"
    mcp_caller = _make_mcp_caller() if enable_mcp else None
    data_mode = "live" if enable_mcp else "fixture"

    rows = []
    t_all = time.perf_counter()
    for item in questions:
        qid = item["question_id"]
        question = item["question"]
        t0 = time.perf_counter()
        try:
            result = rag_answer(
                question,
                config=cfg,
                top_k=5,
                verified_only=False,
                enable_mcp_fallback=enable_mcp,
                mcp_caller=mcp_caller,
                data_mode=data_mode,
                task_id=f"eval-{qid}",
            )
            err = None
        except Exception as exc:  # noqa: BLE001
            result = {"answer": "", "evidence": [], "need_mcp_fallback": True, "error": str(exc)}
            err = f"{type(exc).__name__}: {exc}"
        elapsed = (time.perf_counter() - t0) * 1000
        evidence = result.get("evidence") or []
        retrieved_ids = [e.get("evidence_id") for e in evidence if e.get("evidence_id")]
        gold = item.get("gold_evidence_ids") or []
        faith = faithfulness(
            item.get("reference_points") or [],
            result.get("answer") or "",
            [e.get("text") or "" for e in evidence],
        )
        cite = citation_accuracy_from_report(result.get("citation_report"))
        row = {
            "question_id": qid,
            "eval_type": item.get("eval_type"),
            "needs_mcp": bool(item.get("needs_mcp")),
            "should_refuse": bool(item.get("should_refuse")),
            "gold_evidence_ids": gold,
            "retrieved_evidence_ids": retrieved_ids,
            "top5_hit": top5_hit(gold, retrieved_ids) if gold else None,
            "faithfulness": round(faith, 4),
            "citation_accuracy": cite,
            "mcp_calls": mcp_calls_in_result(result),
            "need_mcp_fallback": result.get("need_mcp_fallback"),
            "refuse_ok": refuse_ok(bool(item.get("should_refuse")), result),
            "duration_ms": round(elapsed, 2),
            "rerank_backend": (result.get("retrieval") or {}).get("rerank_backend"),
            "error": err,
            "answer_excerpt": (result.get("answer") or "")[:400],
        }
        rows.append(row)
        print(f"{qid} faith={row['faithfulness']} hit={row['top5_hit']} mcp={row['mcp_calls']} {elapsed:.0f}ms")

    summary = summarize(rows)
    summary.update(
        {
            "profile": args.profile,
            "dataset_version": qa.get("version"),
            "ce_meta": ce_meta,
            "enable_mcp": enable_mcp,
            "data_mode": data_mode,
            "wall_ms": round((time.perf_counter() - t_all) * 1000, 2),
            "index_info": {
                "backend": info.get("backend"),
                "embed_model": info.get("embed_model"),
                "rerank_model": info.get("rerank_model"),
                "upserted": info.get("upserted"),
            },
            "resume_targets_NOT_injected": {
                "faithfulness": 0.84,
                "top5_hit_rate": 0.82,
                "citation_accuracy": 0.91,
                "mcp_reduction": 0.77,
                "note": "Targets for comparison only; results above are measured.",
            },
        }
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = out_dir / f"{args.profile}_{stamp}_raw.json"
    sum_path = out_dir / f"{args.profile}_{stamp}_summary.json"
    latest_raw = out_dir / f"{args.profile}_latest_raw.json"
    latest_sum = out_dir / f"{args.profile}_latest_summary.json"
    payload = {"summary": summary, "rows": rows}
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sum_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_raw.write_text(raw_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_sum.write_text(sum_path.read_text(encoding="utf-8"), encoding="utf-8")
    print("=== Summary ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("wrote", latest_sum)


if __name__ == "__main__":
    main()
