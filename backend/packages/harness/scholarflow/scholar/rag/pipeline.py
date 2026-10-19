"""End-to-end ScholarFlow RAG pipeline (index + retrieve + citation + optional MCP)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from scholarflow.scholar.rag.chunking import load_chunks_from_artifacts_dir
from scholarflow.scholar.rag.citation import assemble_cited_answer
from scholarflow.scholar.rag.config import RagConfig
from scholarflow.scholar.rag.fallback import retrieve_with_mcp_fallback
from scholarflow.scholar.rag.store import upsert_chunks

McpCaller = Callable[[str, dict[str, Any]], Any]


def index_artifacts_dir(
    artifacts_dir: str | Path, *, config: RagConfig | None = None, task_id: str | None = None
) -> dict[str, Any]:
    cfg = config or RagConfig.from_env()
    chunks = load_chunks_from_artifacts_dir(Path(artifacts_dir), task_id=task_id)
    result = upsert_chunks(chunks, cfg)
    result.update(
        {
            "artifacts_dir": str(artifacts_dir),
            "embed_model": cfg.embed_model,
            "rerank_model": cfg.rerank_model,
            "embed_dim": cfg.embed_dim,
            "backend": cfg.backend,
        }
    )
    return result


def rag_answer(
    question: str,
    *,
    config: RagConfig | None = None,
    top_k: int = 5,
    verified_only: bool = True,
    min_score: float = 0.0,
    enable_mcp_fallback: bool = False,
    mcp_caller: McpCaller | None = None,
    data_mode: str = "fixture",
    task_id: str = "rag-session",
) -> dict[str, Any]:
    """Retrieve-then-answer with mandatory evidence citations (no LLM required).

    Answers only when retrieval evidence is *sufficient* for the question.
    Insufficient hits trigger an explicit refuse (``need_mcp_fallback=True``),
    instead of assembling weakly related bullets. Pass
    ``enable_mcp_fallback=True`` with a live ``mcp_caller`` and
    ``data_mode=\"live\"`` to attempt MCP supplement before refusing.
    """
    cfg = config or RagConfig.from_env()
    pack = retrieve_with_mcp_fallback(
        question,
        cfg,
        top_k=top_k,
        verified_only=verified_only,
        mcp_caller=mcp_caller,
        enable_mcp_fallback=enable_mcp_fallback,
        data_mode=data_mode,
        task_id=task_id,
    )
    hits = pack["hits"]
    if min_score > 0:
        filtered = [h for h in hits if h.score >= min_score]
        if filtered:
            hits = filtered

    retrieval_meta = {
        "backend": cfg.backend,
        "embed_model": cfg.embed_model,
        "rerank_model": cfg.rerank_model,
        "embed_dim": cfg.embed_dim,
        "hit_count": len(hits),
        "vector_store": "chromadb+json",
        "sparse": "bm25+jieba",
        "fusion": "RRF",
        "diagnostics": pack.get("diagnostics") or {},
        "rerank_backend": (pack.get("diagnostics") or {}).get("rerank_backend"),
        "mcp_rounds": pack.get("mcp_rounds") or [],
        "data_mode": pack.get("data_mode"),
        "indexed_extra": pack.get("indexed_extra"),
        "sufficient": pack.get("sufficient"),
        "insufficiency_reason": pack.get("insufficiency_reason"),
        "max_rounds_reached": pack.get("max_rounds_reached"),
        "fallback_blocked": pack.get("fallback_blocked"),
    }

    # Answer only when evidence is sufficient for the question. Weak/topically
    # unrelated hits must NOT be assembled into grounded-looking bullets (refuse).
    # MCP loop (when enabled) may supplement first; still refuse if still insufficient.
    can_answer = bool(hits) and bool(pack.get("sufficient"))
    if not can_answer:
        # Pass empty hits so assemble_cited_answer emits an explicit refuse text.
        built = assemble_cited_answer(question, [], retrieval_meta=retrieval_meta)
        reason = pack.get("insufficiency_reason")
        if reason:
            built["answer"] = (built.get("answer") or "") + f"\n\n（不足原因：{reason}）"
        if pack.get("max_rounds_reached"):
            built["answer"] = (
                (built.get("answer") or "")
                + "\n\n已达最大 MCP 补检次数仍证据不足，明确拒答扩展结论。"
            )
        built["confidence"] = "low"
        built["need_mcp_fallback"] = True
        built["mcp_rounds"] = pack.get("mcp_rounds") or []
        return built

    built = assemble_cited_answer(question, hits, retrieval_meta=retrieval_meta)
    built["need_mcp_fallback"] = False
    built["mcp_rounds"] = pack.get("mcp_rounds") or []
    return built
