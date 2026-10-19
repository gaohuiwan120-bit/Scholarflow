"""ScholarFlow RAG configuration — defaults match runnable stack."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _detect_backend() -> str:
    forced = (os.getenv("SCHOLAR_RAG_BACKEND") or "").strip().lower()
    if forced:
        return forced
    try:
        import fastembed  # noqa: F401

        return "fastembed"
    except Exception:
        pass
    try:
        import sentence_transformers  # noqa: F401

        return "st"
    except Exception:
        return "lite"


def _default_index_dir() -> Path:
    env = os.getenv("SCHOLAR_RAG_INDEX_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "evaluation").is_dir() and (parent / "docs" / "scholar-flow").is_dir():
            return parent / "evaluation" / "rag_index"
    return Path.cwd() / "evaluation" / "rag_index"


@dataclass(frozen=True)
class RagConfig:
    """Hybrid RAG settings.

    Runnable default (fastembed installed):
      Embedding = BAAI/bge-small-en-v1.5 (384-d ONNX)
      Sparse    = BM25 (+ jieba)
      Fusion    = RRF
      Rerank    = hybrid-score by default; set SCHOLAR_RAG_RERANK_MODEL=cross-encoder
                  for ONNX MiniLM Cross-Encoder (requires local model or allow-download).

    Override with SCHOLAR_RAG_EMBED_MODEL / SCHOLAR_RAG_BACKEND / SCHOLAR_RAG_RERANK_MODEL.
    """

    embed_model: str
    rerank_model: str
    embed_dim: int
    persist_dir: Path
    backend: str
    collection_name: str = "scholarflow_evidence"
    recall_dense: int = 20
    recall_sparse: int = 20
    rerank_top_k: int = 5
    rrf_k: int = 60
    # Evidence sufficiency / MCP fallback
    min_evidence: int = 2
    min_top_score: float = 0.05
    max_mcp_rounds: int = 2

    @classmethod
    def from_env(cls, persist_dir: str | Path | None = None) -> RagConfig:
        backend = _detect_backend()
        if backend == "lite":
            embed = os.getenv("SCHOLAR_RAG_EMBED_MODEL", "hashing-bow")
            rerank = os.getenv("SCHOLAR_RAG_RERANK_MODEL", "hybrid-score")
            dim = int(os.getenv("SCHOLAR_RAG_EMBED_DIM", "384"))
        else:
            # Honest runnable default — NOT claiming bge-m3 unless user sets it
            embed = os.getenv("SCHOLAR_RAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
            rerank = os.getenv("SCHOLAR_RAG_RERANK_MODEL", "hybrid-score")
            dim = int(os.getenv("SCHOLAR_RAG_EMBED_DIM", "384"))
        return cls(
            embed_model=embed,
            rerank_model=rerank,
            embed_dim=dim,
            persist_dir=Path(persist_dir) if persist_dir else _default_index_dir(),
            backend=backend,
            min_evidence=int(os.getenv("SCHOLAR_RAG_MIN_EVIDENCE", "2")),
            min_top_score=float(os.getenv("SCHOLAR_RAG_MIN_TOP_SCORE", "0.05")),
            max_mcp_rounds=int(os.getenv("SCHOLAR_RAG_MAX_MCP_ROUNDS", "2")),
        )
