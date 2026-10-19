"""Vector + sparse corpus persistence (fastembed + JSON, optional Chroma)."""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from scholarflow.scholar.rag.chunking import EvidenceChunk
from scholarflow.scholar.rag.config import RagConfig, _detect_backend


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+(?:[./-][a-z0-9]+)*", text)
    try:
        import jieba

        tokens.extend(t.strip() for t in jieba.cut(text) if t.strip() and not t.isspace())
    except Exception:
        hans = re.findall(r"[\u4e00-\u9fff]+", text)
        for span in hans:
            tokens.extend(list(span))
            tokens.extend(span[i : i + 2] for i in range(len(span) - 1))
    return tokens


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@lru_cache(maxsize=2)
def _load_embedder(model_name: str, backend: str):
    if backend == "fastembed":
        from fastembed import TextEmbedding

        return ("fastembed", TextEmbedding(model_name=model_name))
    if backend == "st":
        from sentence_transformers import SentenceTransformer

        return ("st", SentenceTransformer(model_name))
    return ("lite", None)


def embed_texts(texts: list[str], config: RagConfig) -> list[list[float]]:
    backend = config.backend or _detect_backend()
    kind, model = _load_embedder(config.embed_model, backend)
    if kind == "lite" or model is None:
        return [_hash_embed(t, config.embed_dim if config.embed_dim > 0 else 384) for t in texts]
    if kind == "fastembed":
        return [list(map(float, v)) for v in model.embed(texts)]
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def hybrid_score_rerank(query: str, passages: list[str], dense_scores: list[float] | None = None) -> list[float]:
    """Stage-2 rerank without CrossEncoder: lexical overlap (+ optional dense)."""
    q = set(_tokenize(query))
    scores = []
    for i, p in enumerate(passages):
        toks = set(_tokenize(p))
        overlap = len(q & toks) / max(len(q), 1)
        dense = dense_scores[i] if dense_scores and i < len(dense_scores) else 0.0
        scores.append(0.55 * overlap + 0.45 * max(dense, 0.0))
    return scores


def rerank(
    query: str,
    passages: list[str],
    config: RagConfig,
    *,
    dense_scores: list[float] | None = None,
) -> tuple[list[float], dict[str, Any]]:
    """Return (scores, meta). meta.rerank_backend is hybrid-score | cross-encoder | stub-cross-encoder.

    Real Cross-Encoder is never silently replaced by hybrid-score when CE was requested.
    """
    if not passages:
        return [], {"rerank_backend": "none", "is_stub": False, "candidate_count": 0}

    from scholarflow.scholar.rag.cross_encoder import (
        CrossEncoderUnavailable,
        get_cross_encoder,
        resolve_rerank_mode,
    )

    mode = resolve_rerank_mode(config.rerank_model)
    if mode in {"hybrid-score", "lexical-overlap", "none"}:
        scores = (
            [0.0] * len(passages)
            if mode == "none"
            else hybrid_score_rerank(query, passages, dense_scores=dense_scores)
        )
        return scores, {
            "rerank_backend": "hybrid-score" if mode != "none" else "none",
            "is_stub": False,
            "candidate_count": len(passages),
            "requested_model": config.rerank_model,
        }

    try:
        ce = get_cross_encoder(config.rerank_model)
    except CrossEncoderUnavailable:
        raise
    if ce is None:
        scores = hybrid_score_rerank(query, passages, dense_scores=dense_scores)
        return scores, {
            "rerank_backend": "hybrid-score",
            "is_stub": False,
            "candidate_count": len(passages),
            "requested_model": config.rerank_model,
        }
    scores = ce.score_pairs(query, passages)
    return scores, {
        "rerank_backend": "stub-cross-encoder" if ce.is_stub else "cross-encoder",
        "is_stub": ce.is_stub,
        "ce_name": ce.name,
        "candidate_count": len(passages),
        "requested_model": config.rerank_model,
    }


def _corpus_path(config: RagConfig) -> Path:
    return config.persist_dir / "corpus.json"


def _vectors_path(config: RagConfig) -> Path:
    return config.persist_dir / "vectors.json"


def load_corpus(config: RagConfig) -> list[dict[str, Any]]:
    path = _corpus_path(config)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_vectors(config: RagConfig) -> dict[str, list[float]]:
    path = _vectors_path(config)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_chunks(chunks: list[EvidenceChunk], config: RagConfig) -> dict[str, Any]:
    if not chunks:
        return {"upserted": 0}

    try:
        from scholarflow.scholar.rag import retrieve as retrieve_mod

        retrieve_mod._bm25_bundle.cache_clear()
    except Exception:
        pass

    config.persist_dir.mkdir(parents=True, exist_ok=True)
    existing = {row["chunk_id"]: row for row in load_corpus(config)}
    vectors = load_vectors(config)
    docs = [c.text for c in chunks]
    embeds = embed_texts(docs, config)
    actual_dim = len(embeds[0]) if embeds else config.embed_dim

    for c, emb in zip(chunks, embeds):
        existing[c.chunk_id] = {
            "chunk_id": c.chunk_id,
            "evidence_id": c.evidence_id,
            "kind": c.kind,
            "title": c.title,
            "text": c.text,
            "source_url": c.source_url,
            "verification_status": c.verification_status,
            "task_id": c.task_id,
            "metadata": c.metadata,
        }
        vectors[c.chunk_id] = emb

    rows = list(existing.values())
    _corpus_path(config).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _vectors_path(config).write_text(json.dumps(vectors), encoding="utf-8")

    chroma_ok = False
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(config.persist_dir / "chroma"),
            settings=Settings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=config.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            embeddings=embeds,
            metadatas=[
                {
                    "evidence_id": c.evidence_id,
                    "kind": c.kind,
                    "title": c.title[:200],
                    "source_url": c.source_url,
                    "verification_status": c.verification_status,
                    "task_id": c.task_id,
                }
                for c in chunks
            ],
        )
        chroma_ok = True
    except Exception:
        chroma_ok = False

    meta = {
        "backend": config.backend,
        "embed_model": config.embed_model,
        "embed_model_runtime": config.embed_model if config.backend != "lite" else "hashing-bow",
        "rerank_model": config.rerank_model,
        "embed_dim": actual_dim,
        "chunk_count": len(rows),
        "vector_store": "chromadb+json" if chroma_ok else "json-local",
        "sparse": "bm25+jieba",
        "fusion": "RRF",
    }
    (config.persist_dir / "index_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (config.persist_dir / "bm25_corpus.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"upserted": len(chunks), "total": len(rows), "persist_dir": str(config.persist_dir), **meta}
