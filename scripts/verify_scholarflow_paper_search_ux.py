#!/usr/bin/env python3
"""Live check: paper search re-rank + URL consistency (Phase paper UX polish).

Compares arXiv candidate order vs local re-rank for two queries.
Does not invent papers. Writes docs/scholarflow-paper-search-ux.md evidence JSON.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "scholarflow-api"))
sys.path.insert(0, str(ROOT / "backend" / "packages" / "harness"))

from scholarflow_api.chat.paper_rank import rerank_papers, sanitize_source_url, slim_paper_for_tool
from scholarflow_api.chat.tools import _run_search_papers
from scholarflow_api.graph.adapters import fetch_papers_via_mcp

BASE = "http://127.0.0.1:8100"


def _api_health() -> dict:
    with urllib.request.urlopen(BASE + "/health", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _titles(papers: list[dict], n: int = 5) -> list[str]:
    return [str(p.get("title") or "")[:90] for p in papers[:n]]


def compare_query(query: str, max_results: int = 5) -> dict:
    raw, _calls = fetch_papers_via_mcp(query, max_results=max(12, max_results * 4))
    ranked = rerank_papers(query, raw, top_k=max_results)
    slim = [slim_paper_for_tool(p) for p in ranked]
    url_ok = all(
        (p.get("source_url") or "").startswith("https://arxiv.org/abs/")
        and "[" not in (p.get("source_url") or "")
        for p in slim
    )
    ids_ok = all(bool(p.get("evidence_id")) and bool(p.get("title")) for p in slim)
    # Tool path (same as agent)
    tool_json = json.loads(_run_search_papers(query, max_results=max_results))
    return {
        "query": query,
        "candidates_fetched": len(raw),
        "raw_top_titles": _titles(raw, max_results),
        "reranked_top_titles": _titles(ranked, max_results),
        "order_changed": _titles(raw, max_results) != _titles(ranked, max_results),
        "url_ok": url_ok,
        "ids_ok": ids_ok,
        "tool_ok": bool(tool_json.get("ok")),
        "tool_count": tool_json.get("count"),
        "sample": slim[:3],
    }


def main() -> int:
    tested_at = datetime.now(timezone.utc).isoformat()
    print("=== ScholarFlow paper search UX verify ===")
    health = _api_health()
    print("health llm_configured=", health.get("llm_configured"))

    broad = compare_query("compressed sensing", 5)
    focused = compare_query("deep learning compressed sensing image reconstruction", 5)
    print("broad order_changed=", broad["order_changed"], "url_ok=", broad["url_ok"])
    print("  raw:", broad["raw_top_titles"])
    print("  new:", broad["reranked_top_titles"])
    print("focused order_changed=", focused["order_changed"], "url_ok=", focused["url_ok"])
    print("  new:", focused["reranked_top_titles"])

    # Live agent turn via HTTP SSE (real tool call + reinjection)
    body = json.dumps({"title": "paper-ux-live"}).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/v1/conversations",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        cid = json.loads(resp.read().decode())["conversation"]["conversation_id"]

    turn_body = json.dumps(
        {
            "content": (
                "能不能帮我找一找关于压缩感知的论文？请使用 search_papers，"
                "返回若干篇并给出标题与原文链接。"
            )
        }
    ).encode("utf-8")
    treq = urllib.request.Request(
        f"{BASE}/api/v1/conversations/{cid}/turns/stream",
        data=turn_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    events: list[dict] = []
    with urllib.request.urlopen(treq, timeout=180) as resp:
        buf = ""
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                data_lines = [
                    ln[5:].strip() for ln in block.splitlines() if ln.startswith("data:")
                ]
                if data_lines:
                    events.append(json.loads("\n".join(data_lines)))

    names = [e.get("event") for e in events]
    done = next(e for e in events if e.get("event") == "done")
    with urllib.request.urlopen(
        f"{BASE}/api/v1/conversations/{cid}/messages", timeout=30
    ) as resp:
        hist = json.loads(resp.read().decode())
    asst = next(m for m in reversed(hist["messages"]) if m["role"] == "assistant")
    refs = asst.get("evidence_refs") or []
    ref_urls = [sanitize_source_url(r.get("source_url")) for r in refs]
    live = {
        "conversation_id": cid,
        "sse_events_head": names[:8],
        "tool_start_present": "tool_start" in names,
        "done_status": done.get("status"),
        "evidence_count": len(refs),
        "evidence_ids": [r.get("evidence_id") for r in refs],
        "evidence_urls": ref_urls,
        "urls_are_bare_https": all(
            u.startswith("https://") and "[" not in u for u in ref_urls if u
        ),
        "answer_excerpt": (asst.get("content") or "")[:400],
    }
    print("live tool_start=", live["tool_start_present"], "refs=", live["evidence_count"])

    evidence = {
        "tested_at": tested_at,
        "broad": broad,
        "focused": focused,
        "live_agent": live,
        "claims": {
            "relevance_improved_vs_raw_arxiv_order": broad["order_changed"]
            or focused["order_changed"],
            "note": (
                "order_changed only means re-rank altered top-N vs arXiv order; "
                "it is NOT a human relevance gold-label claim."
            ),
        },
    }
    out = ROOT / "docs" / "scholarflow-paper-search-ux-evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)

    assert broad["url_ok"] and broad["ids_ok"] and broad["tool_ok"]
    assert focused["url_ok"] and focused["tool_ok"]
    assert live["tool_start_present"] and live["done_status"] == "completed"
    assert live["evidence_count"] >= 1 and live["urls_are_bare_https"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
