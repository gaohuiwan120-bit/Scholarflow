"""Hybrid retrieval: dense (bge) + BM25 + RRF + hybrid-score or Cross-Encoder rerank."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from scholarflow.scholar.rag.config import RagConfig
from scholarflow.scholar.rag.store import embed_texts, load_corpus, load_vectors, rerank


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


class _BM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_tokens = corpus_tokens
        self.doc_len = [len(doc) for doc in corpus_tokens]
        self.avgdl = sum(self.doc_len) / max(len(corpus_tokens), 1)
        df: dict[str, int] = {}
        for doc in corpus_tokens:
            for t in set(doc):
                df[t] = df.get(t, 0) + 1
        n = max(len(corpus_tokens), 1)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        scores = [0.0] * len(self.corpus_tokens)
        for i, doc in enumerate(self.corpus_tokens):
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            dl = self.doc_len[i] or 1
            for t in query_tokens:
                if t not in tf:
                    continue
                idf = self.idf.get(t, 0.0)
                freq = tf[t]
                score += idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                )
            scores[i] = score
        return scores


@lru_cache(maxsize=4)
def _bm25_bundle(persist_dir: str):
    import json
    from pathlib import Path

    path = Path(persist_dir) / "bm25_corpus.json"
    rows: list[dict[str, Any]] = []
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        cpath = Path(persist_dir) / "corpus.json"
        if cpath.exists():
            rows = json.loads(cpath.read_text(encoding="utf-8"))
    corpus_tokens = [_tokenize(r.get("text", "")) for r in rows]
    bm25 = _BM25(corpus_tokens) if rows else None
    return rows, bm25


def _rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, doc_id in enumerate(ranks):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + i + 1)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class RetrievedEvidence:
    chunk_id: str
    evidence_id: str
    kind: str
    title: str
    text: str
    source_url: str
    verification_status: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "title": self.title,
            "text": self.text,
            "source_url": self.source_url,
            "verification_status": self.verification_status,
            "score": self.score,
        }


@dataclass
class RetrievalResult:
    hits: list[RetrievedEvidence]
    diagnostics: dict[str, Any]


def hybrid_retrieve(
    query: str,
    config: RagConfig,
    *,
    top_k: int | None = None,
    verified_only: bool = False,
    return_diagnostics: bool = False,
) -> list[RetrievedEvidence] | RetrievalResult:
    top_k = top_k or config.rerank_top_k
    t0 = time.perf_counter()
    rows = load_corpus(config)
    vectors = load_vectors(config)
    if not rows:
        rows, _ = _bm25_bundle(str(config.persist_dir))
    if not rows:
        empty_diag = {
            "dense_candidates": 0,
            "sparse_candidates": 0,
            "rrf_candidates": 0,
            "rerank_candidates": 0,
            "timings_ms": {},
            "rerank_backend": None,
        }
        return RetrievalResult([], empty_diag) if return_diagnostics else []

    t_dense0 = time.perf_counter()
    q_emb = embed_texts([query], config)[0]
    dense_scored = []
    for row in rows:
        emb = vectors.get(row["chunk_id"])
        if not emb:
            continue
        dense_scored.append((_cosine(q_emb, emb), row["chunk_id"]))
    dense_scored.sort(reverse=True)
    dense_ids = [cid for _, cid in dense_scored[: config.recall_dense]]
    dense_score_map = {cid: s for s, cid in dense_scored}
    t_dense = (time.perf_counter() - t_dense0) * 1000

    t_sparse0 = time.perf_counter()
    _, bm25 = _bm25_bundle(str(config.persist_dir))
    sparse_ids: list[str] = []
    if bm25 is not None:
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
            : config.recall_sparse
        ]
        sparse_ids = [rows[i]["chunk_id"] for i in ranked if i < len(rows)]
    t_sparse = (time.perf_counter() - t_sparse0) * 1000

    t_rrf0 = time.perf_counter()
    fused_ids = _rrf_fuse([dense_ids, sparse_ids], k=config.rrf_k)
    t_rrf = (time.perf_counter() - t_rrf0) * 1000

    by_id = {r["chunk_id"]: r for r in rows}
    candidates = []
    for cid in fused_ids:
        row = by_id.get(cid)
        if not row:
            continue
        if verified_only and row.get("verification_status") not in {
            "verified",
            "partially_verified",
        }:
            continue
        candidates.append(row)
    if not candidates:
        candidates = [by_id[cid] for cid in fused_ids if cid in by_id][: config.recall_dense]
    if not candidates:
        empty = RetrievalResult([], {"dense_candidates": len(dense_ids), "sparse_candidates": len(sparse_ids)})
        return empty if return_diagnostics else []

    dense_for_cand = [dense_score_map.get(c["chunk_id"], 0.0) for c in candidates]
    if dense_for_cand:
        lo, hi = min(dense_for_cand), max(dense_for_cand)
        if hi > lo:
            dense_for_cand = [(x - lo) / (hi - lo) for x in dense_for_cand]

    t_rr0 = time.perf_counter()
    scores, rerank_meta = rerank(
        query,
        [c.get("text", "") for c in candidates],
        config,
        dense_scores=dense_for_cand,
    )
    t_rerank = (time.perf_counter() - t_rr0) * 1000

    adjusted = []
    for c, s in zip(candidates, scores):
        bonus = 0.0
        # Light structural priors (applied after CE/hybrid scores; documented)
        if c.get("kind") in {"paper", "repository"}:
            bonus += 0.02
        if c.get("source_url"):
            bonus += 0.01
        adjusted.append((c, float(s) + bonus))
    ordered = sorted(adjusted, key=lambda x: x[1], reverse=True)[:top_k]
    hits = [
        RetrievedEvidence(
            chunk_id=c["chunk_id"],
            evidence_id=c["evidence_id"],
            kind=c.get("kind", "unknown"),
            title=c.get("title") or "",
            text=c.get("text") or "",
            source_url=c.get("source_url") or "",
            verification_status=c.get("verification_status") or "unverified",
            score=float(s),
        )
        for c, s in ordered
    ]
    diagnostics = {
        "dense_candidates": len(dense_ids),
        "sparse_candidates": len(sparse_ids),
        "rrf_candidates": len(fused_ids),
        "rerank_candidates": len(candidates),
        "returned": len(hits),
        "timings_ms": {
            "dense": round(t_dense, 2),
            "sparse": round(t_sparse, 2),
            "rrf": round(t_rrf, 2),
            "rerank": round(t_rerank, 2),
            "total": round((time.perf_counter() - t0) * 1000, 2),
        },
        **rerank_meta,
    }
    if return_diagnostics:
        return RetrievalResult(hits=hits, diagnostics=diagnostics)
    return hits


_STOP = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "is",
    "are",
    "be",
    "as",
    "by",
    "from",
    "at",
    "this",
    "that",
    "it",
    "code",
    "data",
    "model",
    "models",
    "system",
    "systems",
    # Question / discourse words that inflate false topical overlap
    "what",
    "which",
    "when",
    "where",
    "who",
    "whom",
    "whose",
    "why",
    "how",
    "does",
    "did",
    "have",
    "has",
    "been",
    "will",
    "would",
    "could",
    "should",
    "can",
    "our",
    "your",
    "their",
    "according",
    "provide",
    "quote",
    "cite",
    "using",
    "used",
    "into",
    "about",
    # Corpus-meta tokens common in ScholarFlow sample artifacts
    "artifacts",
    "artifact",
    "evidence",
    "source",
    "sources",
    "report",
    "research",
    "paper",
    "papers",
}


def _content_tokens(text: str) -> set[str]:
    return {t for t in _tokenize(text) if len(t) >= 4 and t not in _STOP}


def _query_overlap(query: str, text: str) -> tuple[float, int]:
    q = _content_tokens(query)
    t = _content_tokens(text)
    if not q:
        return 0.0, 0
    inter = q & t
    return len(inter) / max(len(q), 1), len(inter)


def evidence_is_sufficient(
    hits: list[RetrievedEvidence],
    config: RagConfig,
    *,
    query: str | None = None,
) -> tuple[bool, str]:
    if len(hits) < config.min_evidence:
        return False, f"hit_count={len(hits)} < min_evidence={config.min_evidence}"
    if not any((h.source_url or "").strip() for h in hits):
        return False, "no_source_url_in_hits"
    # Topical support: require meaningful content-token overlap (not stopwords)
    if query:
        scored = [
            _query_overlap(query, f"{h.title} {h.text}") for h in hits[:5]
        ]
        best_ratio, best_n = max(scored, key=lambda x: (x[1], x[0]), default=(0.0, 0))
        # Require ≥3 shared content tokens OR (≥2 and ratio≥0.25) to reduce
        # false-sufficient answers on out-of-scope refuse questions.
        if best_n < 2 or (best_n < 3 and best_ratio < 0.25) or best_ratio < 0.12:
            return False, f"topical_overlap={best_ratio:.4f} shared_content_tokens={best_n}"
        # High-risk claim markers: if the question asks about awards/secrets/
        # unpublished scores/etc. and those markers are absent from evidence, refuse.
        q_l = query.casefold()
        claim_markers = (
            "award",
            "phone",
            "password",
            "api key",
            "secret",
            "unpublished",
            "gpu hour",
            "gpt-5",
            "best paper",
        )
        markers_in_q = [m for m in claim_markers if m in q_l]
        if markers_in_q:
            ev_blob = " ".join(f"{h.title} {h.text}" for h in hits[:5]).casefold()
            if not any(m in ev_blob for m in markers_in_q):
                return False, f"claim_markers_missing={markers_in_q}"
    top = hits[0].score if hits else 0.0
    backend = (config.rerank_model or "").lower()
    if "cross-encoder" in backend or backend.startswith("ce:") or "minilm" in backend:
        return True, "ok"
    if "stub" in backend:
        return True, "ok"
    if top < config.min_top_score:
        return False, f"top_score={top:.4f} < min_top_score={config.min_top_score}"
    return True, "ok"
