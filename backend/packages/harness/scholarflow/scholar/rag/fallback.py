"""MCP automatic supplement loop for ScholarFlow RAG.

The harness accepts an injectable ``mcp_caller`` so live MCP protocol wiring
stays in the API layer (or tests), while sufficiency / re-index / re-retrieve
logic lives here.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from scholarflow.scholar.rag.chunking import EvidenceChunk
from scholarflow.scholar.rag.config import RagConfig
from scholarflow.scholar.rag.retrieve import (
    RetrievedEvidence,
    evidence_is_sufficient,
    hybrid_retrieve,
)
from scholarflow.scholar.rag.store import upsert_chunks

logger = logging.getLogger("scholarflow.scholar.rag.fallback")

McpCaller = Callable[[str, dict[str, Any]], Any]


class SupplementSink(Protocol):
    def persist_supplement_dir(self, task_id: str, contents: dict[str, str]) -> Path | None: ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def papers_to_chunks(items: list[dict[str, Any]], *, task_id: str) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        eid = str(item.get("evidence_id") or f"paper-mcp-{i}")
        url = (item.get("source_url") or "").strip()
        ident = str(item.get("identifier") or "").strip()
        if not url and ident:
            url = f"https://arxiv.org/abs/{ident}"
        if not url:
            continue
        parts = [
            item.get("title") or "",
            item.get("research_problem") or item.get("abstract") or "",
            item.get("methodology") or "",
            " ".join(item.get("key_findings") or []),
        ]
        chunks.append(
            EvidenceChunk(
                chunk_id=f"{eid}::mcp",
                evidence_id=eid,
                kind="paper",
                title=str(item.get("title") or eid),
                text=" | ".join(p for p in parts if p)[:1800],
                source_url=url,
                verification_status=str(item.get("verification_status") or "verified"),
                task_id=task_id,
                metadata={
                    "fetched_at": item.get("fetched_at") or _now(),
                    "data_mode": "live_mcp",
                    "identifier": ident or None,
                },
            )
        )
    return chunks


def repo_to_chunk(item: dict[str, Any], *, task_id: str) -> EvidenceChunk | None:
    if not isinstance(item, dict) or item.get("error"):
        return None
    repo = str(item.get("repository") or "")
    url = (item.get("source_url") or "").strip() or (
        f"https://github.com/{repo}" if "/" in repo else ""
    )
    if not url:
        return None
    eid = str(item.get("evidence_id") or f"repo-{repo.replace('/', '-')}")
    parts = [
        repo,
        item.get("description") or "",
        item.get("architecture_summary") or "",
        " ".join(item.get("key_modules") or item.get("root_listing") or []),
    ]
    return EvidenceChunk(
        chunk_id=f"{eid}::mcp",
        evidence_id=eid,
        kind="repository",
        title=repo or eid,
        text=" | ".join(p for p in parts if p)[:1800],
        source_url=url,
        verification_status=str(item.get("verification_status") or "verified"),
        task_id=task_id,
        metadata={
            "fetched_at": item.get("fetched_at") or _now(),
            "data_mode": "live_mcp",
            "default_branch": item.get("default_branch"),
        },
    )


def run_mcp_supplement_round(
    question: str,
    *,
    mcp_caller: McpCaller,
    task_id: str,
    round_idx: int,
    reason: str,
) -> dict[str, Any]:
    """One MCP supplement round via real caller (protocol implemented outside)."""
    started = time.perf_counter()
    record: dict[str, Any] = {
        "round": round_idx,
        "reason": reason,
        "started_at": _now(),
        "tools": [],
        "ok": False,
        "chunks_added": 0,
        "error": None,
    }
    chunks: list[EvidenceChunk] = []
    try:
        papers_raw = mcp_caller(
            "search_academic_papers",
            {"query": question, "max_results": 3},
        )
        if isinstance(papers_raw, str):
            papers_raw = json.loads(papers_raw)
        items = papers_raw.get("items") if isinstance(papers_raw, dict) else papers_raw
        if not isinstance(items, list):
            items = []
        paper_chunks = papers_to_chunks(items, task_id=task_id)
        chunks.extend(paper_chunks)
        record["tools"].append(
            {
                "tool": "search_academic_papers",
                "ok": True,
                "returned": len(items),
                "duration_ms": int((time.perf_counter() - started) * 1000),
            }
        )

        # Optional repo pass for code-oriented questions (word-boundary aware)
        q_lower = f" {question.lower()} "
        if any(
            f" {k} " in q_lower or q_lower.strip().startswith(k)
            for k in ("github", "repo", "repository", "langchain", "implement", " codebase ")
        ) or "github.com" in question.lower():
            t1 = time.perf_counter()
            repo_raw = mcp_caller(
                "get_repository_overview",
                {"repository": "langchain-ai/langchain"},
            )
            if isinstance(repo_raw, str):
                repo_raw = json.loads(repo_raw)
            if isinstance(repo_raw, dict):
                rc = repo_to_chunk(repo_raw, task_id=task_id)
                if rc:
                    chunks.append(rc)
            record["tools"].append(
                {
                    "tool": "get_repository_overview",
                    "ok": True,
                    "returned": 1 if chunks else 0,
                    "duration_ms": int((time.perf_counter() - t1) * 1000),
                }
            )
        record["ok"] = bool(chunks)
        record["chunks_added"] = len(chunks)
    except Exception as exc:  # noqa: BLE001
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["ok"] = False
        logger.error("mcp supplement failed: %s", exc)
    record["duration_ms"] = int((time.perf_counter() - started) * 1000)
    record["chunks"] = chunks
    return record


def retrieve_with_mcp_fallback(
    question: str,
    config: RagConfig,
    *,
    top_k: int = 5,
    verified_only: bool = True,
    mcp_caller: McpCaller | None = None,
    enable_mcp_fallback: bool = True,
    data_mode: str = "fixture",
    task_id: str = "rag-session",
    max_rounds: int | None = None,
) -> dict[str, Any]:
    """Retrieve; if evidence insufficient and live MCP enabled, supplement and re-retrieve."""
    max_rounds = config.max_mcp_rounds if max_rounds is None else max_rounds
    supplement_log: list[dict[str, Any]] = []
    indexed_extra = 0

    result = hybrid_retrieve(
        question, config, top_k=top_k, verified_only=verified_only, return_diagnostics=True
    )
    assert not isinstance(result, list)
    hits = result.hits
    diagnostics = result.diagnostics
    ok, reason = evidence_is_sufficient(hits, config, query=question)

    if ok or not enable_mcp_fallback:
        return {
            "hits": hits,
            "diagnostics": diagnostics,
            "sufficient": ok,
            "insufficiency_reason": None if ok else reason,
            "mcp_rounds": supplement_log,
            "need_mcp_fallback": not ok,
            "data_mode": data_mode,
            "indexed_extra": indexed_extra,
        }

    if data_mode != "live" or mcp_caller is None:
        return {
            "hits": hits,
            "diagnostics": diagnostics,
            "sufficient": False,
            "insufficiency_reason": reason,
            "mcp_rounds": supplement_log,
            "need_mcp_fallback": True,
            "data_mode": data_mode,
            "indexed_extra": 0,
            "fallback_blocked": (
                "mcp_caller_missing" if mcp_caller is None else f"data_mode={data_mode}"
            ),
        }

    for round_idx in range(1, max_rounds + 1):
        round_rec = run_mcp_supplement_round(
            question,
            mcp_caller=mcp_caller,
            task_id=task_id,
            round_idx=round_idx,
            reason=reason,
        )
        chunks: list[EvidenceChunk] = round_rec.pop("chunks", [])
        # Persist call record without EvidenceChunk objects
        safe = {k: v for k, v in round_rec.items() if k != "chunks"}
        supplement_log.append(safe)
        if not round_rec.get("ok"):
            break
        if chunks:
            upsert_info = upsert_chunks(chunks, config)
            indexed_extra += int(upsert_info.get("upserted") or 0)
        result = hybrid_retrieve(
            question, config, top_k=top_k, verified_only=verified_only, return_diagnostics=True
        )
        assert not isinstance(result, list)
        hits = result.hits
        diagnostics = result.diagnostics
        ok, reason = evidence_is_sufficient(hits, config, query=question)
        if ok:
            break

    return {
        "hits": hits,
        "diagnostics": diagnostics,
        "sufficient": ok,
        "insufficiency_reason": None if ok else reason,
        "mcp_rounds": supplement_log,
        "need_mcp_fallback": not ok,
        "data_mode": data_mode,
        "indexed_extra": indexed_extra,
        "max_rounds_reached": (not ok) and len(supplement_log) >= max_rounds,
    }
