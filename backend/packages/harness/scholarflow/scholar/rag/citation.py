"""Source-constrained answer assembly and citation verification."""

from __future__ import annotations

import re
from typing import Any

from scholarflow.scholar.rag.retrieve import RetrievedEvidence

_CITE_RE = re.compile(
    r"〔\s*(?P<eid>[^（(〕]+?)(?:\s*[\(（]\s*(?P<url>https?://[^\)）]+)\s*[\)）])?\s*〕"
)


def assemble_cited_answer(
    question: str,
    hits: list[RetrievedEvidence],
    *,
    retrieval_meta: dict[str, Any],
    allow_ungrounded: bool = False,
) -> dict[str, Any]:
    """Build an answer whose every factual bullet cites only provided evidence."""
    if not hits:
        return {
            "question": question,
            "confidence": "low",
            "answer": (
                "证据库未检索到足够支撑该问题的已验证证据。"
                "已标记 need_mcp_fallback；若补检仍不足将明确拒答。"
            ),
            "evidence": [],
            "need_mcp_fallback": True,
            "citation_report": {
                "cited_ids": [],
                "allowed_ids": [],
                "invalid_citations": [],
                "ungrounded_claims": 0,
                "citation_accuracy": None,
            },
            "retrieval": retrieval_meta,
        }

    bullets: list[str] = []
    citations: list[dict[str, Any]] = []
    for h in hits:
        snippet = h.text[:280].replace("\n", " ")
        cite = h.evidence_id
        if h.source_url:
            cite = f"{h.evidence_id} ({h.source_url})"
        bullets.append(f"- [{h.kind}] {snippet} 〔{cite}〕")
        row = h.to_dict()
        row["source_type"] = h.kind
        citations.append(row)

    backend = retrieval_meta.get("rerank_backend") or retrieval_meta.get("rerank_model")
    answer = (
        f"基于 ScholarFlow 科研证据库检索（backend={retrieval_meta.get('backend')}, "
        f"embed={retrieval_meta.get('embed_model')}, sparse=BM25, fusion=RRF, "
        f"rerank={backend}）：\n\n"
        + "\n".join(bullets)
        + "\n\n以上结论均绑定 evidence_id/source_url；证据不支持的主张不予扩展编造。"
    )
    report = verify_citations(answer, hits, allow_ungrounded=allow_ungrounded)
    return {
        "question": question,
        "confidence": "high" if len(hits) >= 2 else "medium",
        "answer": answer,
        "evidence": citations,
        "need_mcp_fallback": False,
        "citation_report": report,
        "retrieval": retrieval_meta,
    }


def verify_citations(
    answer: str,
    allowed: list[RetrievedEvidence] | list[dict[str, Any]],
    *,
    allow_ungrounded: bool = False,
) -> dict[str, Any]:
    """Check that 〔evidence_id (url)〕 markers refer to the allowed evidence set.

    URL format validity alone is insufficient — URL must match the evidence record.
    """
    allowed_map: dict[str, dict[str, Any]] = {}
    for item in allowed:
        if isinstance(item, RetrievedEvidence):
            allowed_map[item.evidence_id] = item.to_dict()
        else:
            eid = str(item.get("evidence_id") or "")
            if eid:
                allowed_map[eid] = dict(item)

    cited_ids: list[str] = []
    invalid: list[dict[str, Any]] = []
    for m in _CITE_RE.finditer(answer or ""):
        eid = (m.group("eid") or "").strip()
        url = (m.group("url") or "").strip()
        cited_ids.append(eid)
        rec = allowed_map.get(eid)
        if rec is None:
            invalid.append({"evidence_id": eid, "reason": "not_in_allowed_set", "url": url})
            continue
        expected = (rec.get("source_url") or "").strip()
        if url and expected and url.rstrip("/") != expected.rstrip("/"):
            invalid.append(
                {
                    "evidence_id": eid,
                    "reason": "url_mismatch",
                    "cited_url": url,
                    "expected_url": expected,
                }
            )
        # Content support: citation marker's preceding bullet should share tokens with evidence
        start = max(0, m.start() - 320)
        window = answer[start : m.start()].lower()
        text = (rec.get("text") or rec.get("title") or "").lower()
        overlap = _token_overlap(window, text)
        if overlap < 0.08:
            invalid.append(
                {
                    "evidence_id": eid,
                    "reason": "content_not_supported",
                    "overlap": round(overlap, 4),
                }
            )

    # Heuristic: sentences that look factual but have no citation nearby
    ungrounded = 0
    if not allow_ungrounded:
        for line in (answer or "").splitlines():
            s = line.strip()
            if not s.startswith("-"):
                continue
            if "〔" not in s and len(s) > 40:
                ungrounded += 1

    total = len(cited_ids)
    accuracy = None if total == 0 else max(0.0, (total - len(invalid)) / total)
    return {
        "cited_ids": cited_ids,
        "allowed_ids": sorted(allowed_map.keys()),
        "invalid_citations": invalid,
        "ungrounded_claims": ungrounded,
        "citation_accuracy": accuracy,
    }


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), 1)
