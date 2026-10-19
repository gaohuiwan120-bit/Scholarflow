"""Shared research/RAG task execution against TaskStore (Phase 8.4).

Used by the HTTP task API and by the chat agent workflow bridge so task_id,
status, and artifacts always come from the same TaskStore records.
"""

from __future__ import annotations

import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Callable

from scholarflow_api.config import Settings
from scholarflow_api.models import TaskKind, TaskStatus
from scholarflow_api.runtime.base import RuntimeRequest, TaskRuntime
from scholarflow_api.services.task_store import TaskRecord, TaskStore

logger = logging.getLogger("scholarflow_api.task_runner")

ProgressFn = Callable[[str], None]


def map_overall_to_task_status(overall: str) -> TaskStatus:
    if overall == "partial_succeeded":
        return TaskStatus.partial_succeeded
    if overall == "failed":
        return TaskStatus.failed
    if overall == "timed_out":
        return TaskStatus.timed_out
    return TaskStatus.succeeded


def build_runtime_request(record: TaskRecord) -> RuntimeRequest:
    params = record.params or {}
    return RuntimeRequest(
        task_id=record.task_id,
        kind=record.kind,
        question=record.question,
        top_k=int(params.get("top_k", 5)),
        ensure_index=bool(params.get("ensure_index", True)),
        force_reindex=bool(params.get("force_reindex", False)),
        verified_only=bool(params.get("verified_only", False)),
        data_mode=str(params.get("data_mode") or "fixture"),
        allow_fixture_fallback=bool(params.get("allow_fixture_fallback", False)),
        force_fail_review=bool(params.get("force_fail_review", False)),
        force_fail_paper=bool(params.get("force_fail_paper", False)),
        simulate_work_seconds=float(params.get("simulate_work_seconds") or 0.0),
        persist_artifacts=bool(params.get("persist_artifacts", True)),
        enable_mcp_fallback=bool(params.get("enable_mcp_fallback", False)),
        rerank_model=params.get("rerank_model"),
    )


def execute_stored_task(
    *,
    store: TaskStore,
    runtime: TaskRuntime,
    settings: Settings,
    task_id: str,
    on_progress: ProgressFn | None = None,
    timeout_seconds: float | None = None,
    executor: ThreadPoolExecutor | None = None,
) -> TaskRecord | None:
    """Run a queued task, update TaskStore, return final record."""
    record = store.get(task_id)
    if record is None:
        return None

    store.update(
        task_id,
        status=TaskStatus.running,
        progress="starting",
        runtime=runtime.name,
    )
    started = time.perf_counter()
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(settings.task_timeout_seconds)
    )

    def _progress(msg: str) -> None:
        store.update(task_id, progress=msg)
        if on_progress:
            on_progress(msg)

    req = build_runtime_request(record)

    owns_executor = executor is None
    pool = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="sf-run")
    future = pool.submit(runtime.run, req, on_progress=_progress)
    try:
        result = future.result(timeout=timeout)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        final_status = map_overall_to_task_status(result.overall_status)
        subtasks = []
        if result.research is not None:
            subtasks = list(result.research.subtasks)
        err = None
        if final_status == TaskStatus.failed:
            err = (result.raw or {}).get("error") or "Research workflow failed"
        store.update(
            task_id,
            status=final_status,
            result=result.payload,
            research=result.research,
            subtasks=subtasks,
            artifacts=result.artifacts,
            index_info=result.index_info,
            progress="done",
            error=err,
            duration_ms=elapsed_ms,
        )
        logger.info("task %s finished status=%s in %sms", task_id, final_status, elapsed_ms)
    except FuturesTimeout:
        future.cancel()
        store.update(
            task_id,
            status=TaskStatus.timed_out,
            error=f"Task exceeded {timeout}s timeout",
            progress="timed_out",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        logger.error("task %s timed out", task_id)
    except Exception as exc:  # noqa: BLE001
        store.update(
            task_id,
            status=TaskStatus.failed,
            error=f"{type(exc).__name__}: {exc}",
            progress="failed",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        logger.error("task %s failed: %s\n%s", task_id, exc, traceback.format_exc())
    finally:
        if owns_executor:
            pool.shutdown(wait=False, cancel_futures=False)

    return store.get(task_id)


def research_kind_from_str(kind: str) -> TaskKind:
    try:
        return TaskKind(kind)
    except ValueError:
        return TaskKind.research_orchestration


def summarize_task_for_agent(record: TaskRecord) -> dict[str, Any]:
    """Safe, truncated snapshot for LLM tool results."""
    research = record.research
    papers = []
    repos = []
    review = None
    experiment_objective = None
    data_mode = None
    effective_data_mode = None
    if research is not None:
        data_mode = research.data_mode
        effective_data_mode = research.effective_data_mode
        for p in (research.papers or [])[:5]:
            if isinstance(p, dict):
                papers.append(
                    {
                        "evidence_id": p.get("evidence_id"),
                        "title": p.get("title"),
                        "source_url": p.get("source_url"),
                        "year": p.get("year"),
                    }
                )
        for r in (research.repositories or [])[:3]:
            if isinstance(r, dict):
                repos.append(
                    {
                        "evidence_id": r.get("evidence_id"),
                        "repository": r.get("repository"),
                        "source_url": r.get("source_url"),
                    }
                )
        reviews = research.reviews or []
        if reviews:
            review = reviews[0] if isinstance(reviews[0], dict) else {"raw": str(reviews[0])[:300]}
        if isinstance(research.experiment, dict):
            experiment_objective = research.experiment.get("objective")

    artifacts = []
    for a in record.artifacts or []:
        artifacts.append(
            {
                "label": a.label,
                "path": a.path,
                "kind": a.kind,
                "download_url": a.path
                if str(a.path).startswith("/api/")
                else f"/api/v1/tasks/{record.task_id}/artifacts/{a.label}",
            }
        )

    answer_preview = None
    if record.result is not None:
        answer_preview = (record.result.answer or "")[:800]

    terminal = record.status in {
        TaskStatus.succeeded,
        TaskStatus.partial_succeeded,
        TaskStatus.failed,
        TaskStatus.timed_out,
    }
    return {
        "ok": record.status != TaskStatus.failed and record.status != TaskStatus.timed_out,
        "task_id": record.task_id,
        "status": record.status.value
        if hasattr(record.status, "value")
        else str(record.status),
        "kind": record.kind.value if hasattr(record.kind, "value") else str(record.kind),
        "question": record.question,
        "progress": record.progress,
        "error": record.error,
        "data_mode": data_mode or (record.params or {}).get("data_mode"),
        "effective_data_mode": effective_data_mode,
        "terminal": terminal,
        "duration_ms": record.duration_ms,
        "papers": papers,
        "repositories": repos,
        "review": review,
        "experiment_objective": experiment_objective,
        "answer_preview": answer_preview,
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "subtask_count": len(record.subtasks or []),
    }
