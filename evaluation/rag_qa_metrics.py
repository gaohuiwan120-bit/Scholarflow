"""Compute RAG QA metrics from raw per-question results (no hardcoded targets)."""

from __future__ import annotations

import re
from typing import Any


def top5_hit(gold_ids: list[str], retrieved_ids: list[str]) -> bool:
    if not gold_ids:
        return False
    top = set(retrieved_ids[:5])
    return any(g in top for g in gold_ids)


def faithfulness(reference_points: list[str], answer: str, evidence_texts: list[str]) -> float:
    """Fraction of reference points supported by answer∪evidence (substring, casefold).

    Protocol: automatic lexical support; no LLM judge. Documented for calibration.
    """
    if not reference_points:
        return 1.0 if not answer else 1.0
    blob = (" ".join([answer or ""] + evidence_texts)).casefold()
    hits = 0
    for pt in reference_points:
        if (pt or "").casefold() in blob:
            hits += 1
    return hits / len(reference_points)


def citation_accuracy_from_report(report: dict[str, Any] | None) -> float | None:
    if not report:
        return None
    acc = report.get("citation_accuracy")
    if acc is None:
        return None
    return float(acc)


def mcp_calls_in_result(result: dict[str, Any]) -> int:
    rounds = result.get("mcp_rounds") or (result.get("retrieval") or {}).get("mcp_rounds") or []
    total = 0
    for r in rounds:
        tools = r.get("tools") or []
        total += len(tools) if tools else (1 if r.get("ok") is not None else 0)
    return total


def refuse_ok(should_refuse: bool, result: dict[str, Any]) -> bool:
    if not should_refuse:
        return True
    ans = (result.get("answer") or "").lower()
    flags = (
        result.get("need_mcp_fallback") is True
        or "证据不足" in (result.get("answer") or "")
        or "拒答" in (result.get("answer") or "")
        or "insufficient" in ans
        or result.get("confidence") == "low"
    )
    # Must not invent award/phone/key style content
    bad = any(x in ans for x in ("api key", "phone", "best paper award", "gpu hours: "))
    return bool(flags) and not bad


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}

    def avg(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    faith = [r["faithfulness"] for r in rows if r.get("faithfulness") is not None]
    hits = [1.0 if r.get("top5_hit") else 0.0 for r in rows if r.get("gold_evidence_ids")]
    cites = [r["citation_accuracy"] for r in rows if r.get("citation_accuracy") is not None]
    mcp_total = sum(int(r.get("mcp_calls") or 0) for r in rows)
    mcp_topic = [
        int(r.get("mcp_calls") or 0)
        for r in rows
        if r.get("needs_mcp") or r.get("eval_type") == "needs_mcp"
    ]
    refuse = [1.0 if r.get("refuse_ok") else 0.0 for r in rows if r.get("should_refuse")]

    return {
        "n": n,
        "faithfulness_mean": round(avg(faith), 4),
        "top5_hit_rate": round(avg(hits), 4) if hits else None,
        "top5_hit_denominator": len(hits),
        "citation_accuracy_mean": round(avg(cites), 4) if cites else None,
        "citation_denominator": len(cites),
        "mcp_calls_total": mcp_total,
        "mcp_calls_on_needs_mcp_total": sum(mcp_topic),
        "mcp_calls_on_needs_mcp_avg": round(avg([float(x) for x in mcp_topic]), 4) if mcp_topic else 0.0,
        "needs_mcp_question_count": len(mcp_topic),
        "refuse_accuracy": round(avg(refuse), 4) if refuse else None,
        # Explicitly NOT resume targets — computed only
        "note": "Metrics computed from raw rows; resume targets are goals not injected values.",
    }


_CITE_EID = re.compile(r"〔\s*([^（(〕]+)")


def extract_cited_ids(answer: str) -> list[str]:
    return [m.group(1).strip() for m in _CITE_EID.finditer(answer or "")]
