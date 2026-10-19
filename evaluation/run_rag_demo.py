#!/usr/bin/env python3
"""Interview demo: ScholarFlow hybrid RAG (real fastembed embeddings).

  cd backend
  uv run python ../evaluation/run_rag_demo.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "backend" / "packages" / "harness"
sys.path.insert(0, str(HARNESS))

# Prefer real fastembed when installed; do NOT force lite
if "SCHOLAR_RAG_BACKEND" not in os.environ:
    try:
        import fastembed  # noqa: F401

        os.environ["SCHOLAR_RAG_BACKEND"] = "fastembed"
    except Exception:
        os.environ["SCHOLAR_RAG_BACKEND"] = "lite"

from scholarflow.scholar.rag import RagConfig, index_artifacts_dir, rag_answer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="ScholarFlow RAG demo")
    parser.add_argument(
        "--artifacts",
        default=str(ROOT / "docs" / "scholar-flow" / "samples" / "rag-test-001"),
    )
    parser.add_argument(
        "--question",
        default="Blended RAG hybrid dense sparse vs Naive RAG",
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    cfg = RagConfig.from_env()
    print("=== ScholarFlow RAG Config ===")
    print(
        json.dumps(
            {
                "backend": cfg.backend,
                "embed_model": cfg.embed_model,
                "rerank_model": cfg.rerank_model,
                "embed_dim": cfg.embed_dim,
                "persist_dir": str(cfg.persist_dir),
                "fusion": "RRF",
                "sparse": "BM25+jieba",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if cfg.backend == "lite":
        print(
            "\n[WARN] Running lite hashing backend. Install deps for real embeddings:\n"
            "  uv pip install fastembed chromadb rank-bm25 jieba\n"
        )

    print("\n=== Indexing artifacts ===")
    # Fresh index for clean demo
    import shutil

    if cfg.persist_dir.exists():
        shutil.rmtree(cfg.persist_dir, ignore_errors=True)
    info = index_artifacts_dir(args.artifacts, config=cfg, task_id="rag-test-001")
    print(json.dumps(info, ensure_ascii=False, indent=2))

    print("\n=== RAG Answer ===")
    result = rag_answer(args.question, config=cfg, top_k=args.top_k, verified_only=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Hard checks for interview confidence
    assert info.get("upserted", 0) >= 3, "index failed"
    assert result.get("evidence"), "no evidence returned"
    assert result.get("need_mcp_fallback") is False, "unexpected fallback"
    print("\n=== DEMO OK ===")


if __name__ == "__main__":
    main()
