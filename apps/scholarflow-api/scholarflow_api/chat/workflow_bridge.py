"""Bridge chat tools ↔ TaskStore + ResearchTaskRuntime (Phase 8.4)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Literal

from scholarflow_api.chat.tools import _emit_workflow_progress
from scholarflow_api.config import Settings, get_settings
from scholarflow_api.llm.guards import safe_exc_message
from scholarflow_api.models import TaskKind, TaskStatus
from scholarflow_api.runtime.research_runtime import ResearchTaskRuntime
from scholarflow_api.services.artifact_store import list_artifacts, task_dir
from scholarflow_api.services.task_runner import (
    execute_stored_task,
    research_kind_from_str,
    summarize_task_for_agent,
)
from scholarflow_api.services.task_store import TaskStore

logger = logging.getLogger("scholarflow_api.chat.workflow_bridge")

WorkflowKind = Literal[
    "research_orchestration",
    "paper_research",
    "repository_analysis",
    "experiment_design",
]


@dataclass
class WorkflowBridge:
    store: TaskStore
    runtime: ResearchTaskRuntime
    settings: Settings
    _bg_lock: threading.Lock = threading.Lock()

    def submit_research(
        self,
        *,
        question: str,
        kind: WorkflowKind = "research_orchestration",
        data_mode: Literal["fixture", "live"] = "fixture",
        wait: bool = True,
        wait_timeout_seconds: float = 120.0,
        allow_fixture_fallback: bool | None = None,
    ) -> dict[str, Any]:
        task_kind = research_kind_from_str(kind)
        if task_kind == TaskKind.rag_query:
            task_kind = TaskKind.research_orchestration

        fallback = (
            allow_fixture_fallback
            if allow_fixture_fallback is not None
            else (data_mode == "live")
        )
        params = {
            "data_mode": data_mode,
            "allow_fixture_fallback": fallback,
            "persist_artifacts": True,
            "kind": task_kind.value,
        }
        record = self.store.create(
            kind=task_kind,
            question=question,
            runtime=self.runtime.name,
            params=params,
        )
        task_id = record.task_id
        _emit_workflow_progress(
            "research task submitted",
            task_id=task_id,
            overall_status="queued",
        )

        if not wait:
            thread = threading.Thread(
                target=self._run_background,
                args=(task_id,),
                name=f"sf-bg-{task_id}",
                daemon=True,
            )
            thread.start()
            _emit_workflow_progress(
                "research task running in background",
                task_id=task_id,
                overall_status="running",
            )
            return {
                "ok": True,
                "tool": "run_research_workflow",
                "task_id": task_id,
                "status": "queued",
                "terminal": False,
                "data_mode": data_mode,
                "message": (
                    "Task submitted asynchronously. Use get_research_task to poll. "
                    "Do not claim artifacts are ready until status is terminal."
                ),
                "poll_hint": f"get_research_task(task_id={task_id})",
            }

        def on_progress(msg: str) -> None:
            _emit_workflow_progress(
                msg,
                task_id=task_id,
                overall_status="running",
            )

        _emit_workflow_progress(
            "research task running",
            task_id=task_id,
            overall_status="running",
        )
        t0 = time.perf_counter()
        try:
            final = execute_stored_task(
                store=self.store,
                runtime=self.runtime,
                settings=self.settings,
                task_id=task_id,
                on_progress=on_progress,
                timeout_seconds=wait_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            _emit_workflow_progress(
                "research task failed",
                task_id=task_id,
                overall_status="failed",
            )
            return {
                "ok": False,
                "tool": "run_research_workflow",
                "task_id": task_id,
                "status": "failed",
                "terminal": True,
                "data_mode": data_mode,
                "error": safe_exc_message(exc),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

        if final is None:
            return {
                "ok": False,
                "tool": "run_research_workflow",
                "task_id": task_id,
                "error": "task disappeared from TaskStore",
                "terminal": True,
            }

        summary = summarize_task_for_agent(final)
        # Enrich with on-disk artifact listing when present
        disk = self._disk_artifacts(task_id)
        if disk:
            summary["disk_artifacts"] = disk
        summary["tool"] = "run_research_workflow"
        summary["waited"] = True
        summary["wait_timeout_seconds"] = wait_timeout_seconds
        summary["duration_ms"] = int((time.perf_counter() - t0) * 1000)

        status_val = summary.get("status")
        _emit_workflow_progress(
            f"research task {status_val}",
            task_id=task_id,
            overall_status=str(status_val),
        )

        # Honesty: fixture vs live
        summary["data_source_note"] = (
            "fixture workflow (sample artifacts / offline nodes)"
            if (summary.get("effective_data_mode") or data_mode) == "fixture"
            else "live MCP data mode (external calls may have occurred)"
        )
        if final.status in {TaskStatus.queued, TaskStatus.running}:
            # Should not happen after wait, but be honest
            summary["ok"] = True
            summary["terminal"] = False
            summary["message"] = "Task still running after wait window; poll get_research_task."
        elif final.status in {TaskStatus.failed, TaskStatus.timed_out}:
            summary["ok"] = False
        else:
            summary["ok"] = True
        return summary

    def _run_background(self, task_id: str) -> None:
        try:
            execute_stored_task(
                store=self.store,
                runtime=self.runtime,
                settings=self.settings,
                task_id=task_id,
                on_progress=lambda msg: _emit_workflow_progress(
                    msg, task_id=task_id, overall_status="running"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("background task %s failed: %s", task_id, safe_exc_message(exc))

    def get_task(self, task_id: str) -> dict[str, Any]:
        record = self.store.get(task_id)
        if record is None:
            return {
                "ok": False,
                "tool": "get_research_task",
                "task_id": task_id,
                "error": "task not found in TaskStore",
            }
        summary = summarize_task_for_agent(record)
        summary["tool"] = "get_research_task"
        disk = self._disk_artifacts(task_id)
        if disk:
            summary["disk_artifacts"] = disk
        if not summary["terminal"]:
            summary["message"] = (
                "Task is still in progress. Do not claim final artifacts yet."
            )
        return summary

    def list_artifacts(self, task_id: str) -> dict[str, Any]:
        record = self.store.get(task_id)
        if record is None:
            return {
                "ok": False,
                "tool": "list_research_artifacts",
                "task_id": task_id,
                "error": "task not found in TaskStore",
            }
        man = list_artifacts(task_id)
        files = self._disk_artifacts(task_id)
        items = []
        if man is not None:
            for a in man.artifacts:
                items.append(
                    {
                        "filename": a.filename,
                        "size_bytes": a.size_bytes,
                        "data_mode": a.data_mode,
                        "download_url": f"/api/v1/tasks/{task_id}/artifacts/{a.filename}",
                        "exists": True,
                    }
                )
        elif files:
            for name in files:
                items.append(
                    {
                        "filename": name,
                        "download_url": f"/api/v1/tasks/{task_id}/artifacts/{name}",
                        "exists": True,
                    }
                )

        terminal = record.status not in {TaskStatus.queued, TaskStatus.running}
        return {
            "ok": True,
            "tool": "list_research_artifacts",
            "task_id": task_id,
            "task_status": record.status.value
            if hasattr(record.status, "value")
            else str(record.status),
            "terminal": terminal,
            "artifacts": items,
            "artifact_count": len(items),
            "message": None
            if items
            else (
                "No artifact files on disk yet"
                if not terminal
                else "No artifacts found for completed task"
            ),
        }

    @staticmethod
    def _disk_artifacts(task_id: str) -> list[str]:
        try:
            path = task_dir(task_id)
            if path.is_dir():
                return sorted(p.name for p in path.iterdir() if p.is_file())
        except Exception:  # noqa: BLE001
            return []
        return []


_bridge: WorkflowBridge | None = None


def configure_workflow_bridge(
    store: TaskStore,
    runtime: ResearchTaskRuntime | None = None,
    settings: Settings | None = None,
) -> WorkflowBridge:
    global _bridge
    cfg = settings or get_settings()
    rt = runtime or ResearchTaskRuntime(cfg)
    _bridge = WorkflowBridge(store=store, runtime=rt, settings=cfg)
    return _bridge


def get_workflow_bridge() -> WorkflowBridge:
    global _bridge
    if _bridge is None:
        # Lazy fallback for tests — isolated store under default path
        from scholarflow_api.services.task_store import TaskStore

        cfg = get_settings()
        _bridge = WorkflowBridge(
            store=TaskStore(persist=True),
            runtime=ResearchTaskRuntime(cfg),
            settings=cfg,
        )
    return _bridge
