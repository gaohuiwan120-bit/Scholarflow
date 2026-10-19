"""Chat agent tools — thin wrappers over existing RAG / MCP / research workflow.

No API keys are returned to the model. Business logic is not reimplemented.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Callable, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator

from scholarflow_api.llm.guards import redact_secrets, safe_exc_message

logger = logging.getLogger("scholarflow_api.chat.tools")

# Optional progress sink for Phase 8.3 SSE (set by ChatAgentRuntime during a turn).
WorkflowProgressFn = Callable[[str, dict[str, Any]], None]
_workflow_progress_cb: ContextVar[WorkflowProgressFn | None] = ContextVar(
    "sf_workflow_progress_cb", default=None
)


def set_workflow_progress_callback(cb: WorkflowProgressFn | None):
    return _workflow_progress_cb.set(cb)


def reset_workflow_progress_callback(token) -> None:
    _workflow_progress_cb.reset(token)


def _emit_workflow_progress(message: str, **fields: Any) -> None:
    cb = _workflow_progress_cb.get()
    if cb is not None:
        try:
            cb(message, fields)
        except Exception as exc:  # noqa: BLE001
            logger.debug("workflow progress callback failed: %s", exc)

WorkflowKind = Literal[
    "research_orchestration",
    "paper_research",
    "repository_analysis",
    "experiment_design",
]


def _truncate(obj: Any, *, limit: int = 6000) -> str:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    text = redact_secrets(text)
    if len(text) > limit:
        return text[: limit - 20] + "\n...[truncated]"
    return text


class ScholarRagQueryArgs(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000, description="Research question to answer from indexed ScholarFlow artifacts")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of evidence chunks to retrieve")

    @field_validator("question")
    @classmethod
    def _strip_q(cls, v: str) -> str:
        t = v.strip()
        if len(t) < 2:
            raise ValueError("question too short")
        return t


class SearchPapersArgs(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description=(
            "arXiv search query in English when possible. For a broad topic "
            "(e.g. compressed sensing), prefer a clear topic phrase such as "
            "'compressed sensing' or 'compressed sensing survey' — do NOT "
            "default to a user's personal specialty (e.g. single-pixel imaging) "
            "unless the user explicitly asked for that sub-area. "
            "For a focused follow-up, include the specialty terms the user named."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def _strip_q(cls, v: str) -> str:
        t = v.strip()
        if len(t) < 2:
            raise ValueError("query too short")
        return t


class RunResearchWorkflowArgs(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000, description="Full research question for the ScholarFlow LangGraph workflow")
    kind: WorkflowKind = Field(
        default="research_orchestration",
        description="Workflow mode: research_orchestration | paper_research | repository_analysis | experiment_design",
    )
    data_mode: Literal["fixture", "live"] = Field(
        default="fixture",
        description="Use fixture for fast local runs; live calls MCP (slower). Always report this mode honestly.",
    )
    wait: bool = Field(
        default=True,
        description="If true, wait up to wait_timeout_seconds for completion; if false, return task_id immediately and poll later",
    )
    wait_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=300.0,
        description="Max seconds to wait when wait=true (does not claim success if still running)",
    )

    @field_validator("question")
    @classmethod
    def _strip_q(cls, v: str) -> str:
        t = v.strip()
        if len(t) < 2:
            raise ValueError("question too short")
        return t


class GetResearchTaskArgs(BaseModel):
    task_id: str = Field(..., min_length=4, max_length=64, description="ScholarFlow task_id (sf-...)")

    @field_validator("task_id")
    @classmethod
    def _strip_id(cls, v: str) -> str:
        return v.strip()


class ListResearchArtifactsArgs(BaseModel):
    task_id: str = Field(..., min_length=4, max_length=64)

    @field_validator("task_id")
    @classmethod
    def _strip_id(cls, v: str) -> str:
        return v.strip()


def _run_scholar_rag_query(question: str, top_k: int = 5) -> str:
    from scholarflow_api.config import ensure_harness_on_path, get_settings

    ensure_harness_on_path()
    from scholarflow.scholar.rag import RagConfig, rag_answer

    settings = get_settings()
    cfg = RagConfig.from_env()
    t0 = time.perf_counter()
    try:
        result = rag_answer(question, config=cfg, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "ok": False,
            "tool": "scholar_rag_query",
            "error": safe_exc_message(exc),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
        }
        return _truncate(payload)

    evidence = result.get("evidence") or result.get("citations") or []
    slim_ev = []
    for e in evidence[: top_k]:
        if not isinstance(e, dict):
            continue
        slim_ev.append(
            {
                "evidence_id": e.get("evidence_id") or e.get("chunk_id"),
                "title": e.get("title"),
                "source_url": e.get("source_url"),
                "score": e.get("score"),
            }
        )
    payload = {
        "ok": True,
        "tool": "scholar_rag_query",
        "answer": (result.get("answer") or "")[:2000],
        "refused": bool(result.get("refused") or result.get("insufficient_evidence")),
        "evidence": slim_ev,
        "artifacts_dir": str(settings.default_artifacts_dir),
        "duration_ms": int((time.perf_counter() - t0) * 1000),
    }
    return _truncate(payload)


def _run_search_papers(query: str, max_results: int = 5) -> str:
    from scholarflow_api.chat.paper_rank import rerank_papers, slim_paper_for_tool
    from scholarflow_api.graph.adapters import fetch_papers_via_mcp
    from scholarflow_api.mcp.client import ScholarMcpError

    t0 = time.perf_counter()
    # Over-fetch from arXiv, then re-rank locally on real title/abstract fields.
    fetch_n = min(40, max(max_results * 4, 12))
    try:
        papers, calls = fetch_papers_via_mcp(query, max_results=fetch_n)
    except ScholarMcpError as exc:
        return _truncate(
            {
                "ok": False,
                "tool": "search_papers",
                "error": safe_exc_message(exc),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _truncate(
            {
                "ok": False,
                "tool": "search_papers",
                "error": safe_exc_message(exc),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }
        )

    ranked = rerank_papers(query, papers, top_k=max_results)
    slim = [slim_paper_for_tool(p) for p in ranked]
    return _truncate(
        {
            "ok": True,
            "tool": "search_papers",
            "query": query,
            "papers": slim,
            "count": len(slim),
            "candidates_fetched": len(papers),
            "reranked": True,
            "mcp_calls": len(calls),
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "note": (
                "Papers are real arXiv MCP results, re-ranked by title/abstract "
                "overlap with the query. relevance_score is heuristic only — "
                "not a peer-review rating. kind_hint=survey_or_review only when "
                "those words appear in the title. Do not invent missing authors "
                "or call a paper 'classic' without real evidence."
            ),
        },
        limit=9000,
    )


def _run_research_workflow(
    question: str,
    kind: WorkflowKind = "research_orchestration",
    data_mode: Literal["fixture", "live"] = "fixture",
    wait: bool = True,
    wait_timeout_seconds: float = 120.0,
) -> str:
    from scholarflow_api.chat.workflow_bridge import get_workflow_bridge

    bridge = get_workflow_bridge()
    try:
        result = bridge.submit_research(
            question=question,
            kind=kind,
            data_mode=data_mode,
            wait=wait,
            wait_timeout_seconds=wait_timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        return _truncate(
            {
                "ok": False,
                "tool": "run_research_workflow",
                "error": safe_exc_message(exc),
            }
        )
    return _truncate(result)


def _get_research_task(task_id: str) -> str:
    from scholarflow_api.chat.workflow_bridge import get_workflow_bridge

    return _truncate(get_workflow_bridge().get_task(task_id))


def _list_research_artifacts(task_id: str) -> str:
    from scholarflow_api.chat.workflow_bridge import get_workflow_bridge

    return _truncate(get_workflow_bridge().list_artifacts(task_id))


def build_chat_tools() -> list[StructuredTool]:
    """Register chat tools (Phase 8.2 + 8.4 workflow bridge)."""
    return [
        StructuredTool.from_function(
            func=_run_scholar_rag_query,
            name="scholar_rag_query",
            description=(
                "Query the ScholarFlow hybrid RAG index over existing research artifacts. "
                "Use when the user asks about previously indexed research evidence, "
                "citations, or local corpus knowledge. Do not use for brand-new arXiv search."
            ),
            args_schema=ScholarRagQueryArgs,
        ),
        StructuredTool.from_function(
            func=_run_search_papers,
            name="search_papers",
            description=(
                "Search academic papers via ScholarFlow MCP (arXiv), then re-rank "
                "candidates by title/abstract relevance to the query. "
                "Use when the user needs external papers. "
                "Pass a focused English query; for broad topics prefer the topic name "
                "(optionally with 'survey'); only add specialty terms the user stated."
            ),
            args_schema=SearchPapersArgs,
        ),
        StructuredTool.from_function(
            func=_run_research_workflow,
            name="run_research_workflow",
            description=(
                "Submit a full ScholarFlow LangGraph research workflow via TaskStore "
                "(paper/repo/experiment/review + 9 artifacts). Returns real task_id and status. "
                "Prefer data_mode=fixture for local demos; use live only when external MCP is needed. "
                "Set wait=false for long jobs and then call get_research_task. "
                "Never invent artifacts or claim success if status is not terminal."
            ),
            args_schema=RunResearchWorkflowArgs,
        ),
        StructuredTool.from_function(
            func=_get_research_task,
            name="get_research_task",
            description=(
                "Fetch actual TaskStore status/result for a research task_id. "
                "Use after run_research_workflow or when the user asks about a prior task. "
                "If terminal=false, say the task is still running."
            ),
            args_schema=GetResearchTaskArgs,
        ),
        StructuredTool.from_function(
            func=_list_research_artifacts,
            name="list_research_artifacts",
            description=(
                "List real on-disk / manifest artifacts for a task_id with download URLs "
                "under /api/v1/tasks/{id}/artifacts/{filename}. Only list files that exist."
            ),
            args_schema=ListResearchArtifactsArgs,
        ),
    ]


SYSTEM_PROMPT = """You are ScholarFlow, a research assistant.

You have tools. Use them only when they materially help answer the user:
- scholar_rag_query: local indexed research corpus / citations
- search_papers: find papers via arXiv MCP (re-ranked); returns real titles/urls/abstracts
- run_research_workflow: submit the full multi-step research pipeline (returns real task_id in TaskStore)
- get_research_task: poll TaskStore for status/summary/evidence
- list_research_artifacts: list real downloadable artifact files for a task_id

Rules:
1. Ordinary chit-chat or simple questions: answer directly without tools.
2. When you use a tool, base your final answer on the actual tool result (including errors).
3. Never invent tool results, papers, authors, years, abstracts, task success, or artifact files. Never request or expose API keys. If a field is missing, say unknown / omit it.
4. Always report data_mode / effective_data_mode honestly (fixture ≠ live external retrieval).
5. If terminal=false or status is queued/running, do not claim the research is finished.
6. Prefer concise, evidence-aware answers with source_url / evidence_id / task_id when available.
7. Paper search presentation: for each paper from search_papers, write a short bullet or numbered item with **title**, year (if present), authors (only if returned), 1–2 sentence abstract/problem summary from the tool fields, bare source_url on its own, and evidence_id. Do not dump a second duplicate list. Do not label a paper as classic/foundational unless the tool kind_hint or title clearly supports it (e.g. survey/review in title). Prefer representative theory/survey/method papers for broad queries.
8. Do not assume the user's personal research niche. Only narrow to image reconstruction / single-pixel imaging / deep learning when the user asks.
9. Follow-ups: keep using tools when the user asks to dig into a paper, compare methods, or search a sub-area — decide with tool-calling, not fixed keyword routing.
"""
