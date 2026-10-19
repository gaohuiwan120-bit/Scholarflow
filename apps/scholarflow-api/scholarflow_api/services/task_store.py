"""Task store with optional JSON persistence (Phase-1 memory + light disk restore).

In-memory remains the primary index for the running process. On update, state is
mirrored under SCHOLARFLOW_TASKS_DIR/<task_id>/task_state.json so API restarts can
reload status/result without Redis. Artifacts stay in the existing artifact_store.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from scholarflow_api.models import (
    ArtifactRef,
    RagResultPayload,
    ResearchWorkflowPayload,
    SubtaskStatusItem,
    TaskKind,
    TaskStatus,
    utc_now,
)

logger = logging.getLogger("scholarflow_api.task_store")


def _tasks_root() -> Path:
    import os

    from scholarflow_api.config import repo_root

    env = os.getenv("SCHOLARFLOW_TASKS_DIR")
    if env:
        return Path(env)
    return repo_root() / "apps" / "scholarflow-api" / "data" / "tasks"


@dataclass
class TaskRecord:
    task_id: str
    kind: TaskKind
    question: str
    status: TaskStatus
    runtime: str
    created_at: datetime
    updated_at: datetime
    progress: str | None = None
    error: str | None = None
    result: RagResultPayload | None = None
    research: ResearchWorkflowPayload | None = None
    subtasks: list[SubtaskStatusItem] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    index_info: dict[str, Any] | None = None
    duration_ms: int | None = None
    params: dict[str, Any] = field(default_factory=dict)


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return utc_now()


def _serialize(record: TaskRecord) -> dict[str, Any]:
    def enc(obj: Any) -> Any:
        if obj is None:
            return None
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if isinstance(obj, list):
            return [enc(x) for x in obj]
        if isinstance(obj, (TaskStatus, TaskKind)):
            return obj.value
        return obj

    return {
        "task_id": record.task_id,
        "kind": enc(record.kind),
        "question": record.question,
        "status": enc(record.status),
        "runtime": record.runtime,
        "created_at": enc(record.created_at),
        "updated_at": enc(record.updated_at),
        "progress": record.progress,
        "error": record.error,
        "result": enc(record.result),
        "research": enc(record.research),
        "subtasks": enc(record.subtasks),
        "artifacts": enc(record.artifacts),
        "index_info": record.index_info,
        "duration_ms": record.duration_ms,
        "params": record.params,
    }


def _deserialize(data: dict[str, Any]) -> TaskRecord:
    kind = data.get("kind") or "rag_query"
    status = data.get("status") or "queued"
    result = data.get("result")
    research = data.get("research")
    subtasks_raw = data.get("subtasks") or []
    artifacts_raw = data.get("artifacts") or []
    return TaskRecord(
        task_id=str(data["task_id"]),
        kind=TaskKind(kind) if not isinstance(kind, TaskKind) else kind,
        question=str(data.get("question") or ""),
        status=TaskStatus(status) if not isinstance(status, TaskStatus) else status,
        runtime=str(data.get("runtime") or ""),
        created_at=_dt(data.get("created_at")),
        updated_at=_dt(data.get("updated_at")),
        progress=data.get("progress"),
        error=data.get("error"),
        result=RagResultPayload.model_validate(result) if result else None,
        research=ResearchWorkflowPayload.model_validate(research) if research else None,
        subtasks=[SubtaskStatusItem.model_validate(s) for s in subtasks_raw],
        artifacts=[ArtifactRef.model_validate(a) for a in artifacts_raw],
        index_info=data.get("index_info"),
        duration_ms=data.get("duration_ms"),
        params=dict(data.get("params") or {}),
    )


class TaskStore:
    def __init__(self, *, persist: bool = True) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskRecord] = {}
        self._persist = persist

    def _state_path(self, task_id: str) -> Path:
        return _tasks_root() / task_id / "task_state.json"

    def _write_disk(self, record: TaskRecord) -> None:
        if not self._persist:
            return
        try:
            path = self._state_path(record.task_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(_serialize(record), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("task state persist failed task=%s: %s", record.task_id, exc)

    def _load_disk(self, task_id: str) -> TaskRecord | None:
        if not self._persist:
            return None
        path = self._state_path(task_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _deserialize(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("task state load failed task=%s: %s", task_id, exc)
            return None

    def create(
        self,
        *,
        kind: TaskKind,
        question: str,
        runtime: str,
        params: dict[str, Any],
    ) -> TaskRecord:
        now = utc_now()
        record = TaskRecord(
            task_id=f"sf-{uuid.uuid4().hex[:12]}",
            kind=kind,
            question=question,
            status=TaskStatus.queued,
            runtime=runtime,
            created_at=now,
            updated_at=now,
            params=params,
        )
        with self._lock:
            self._tasks[record.task_id] = record
            self._write_disk(record)
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is not None:
                return record
            loaded = self._load_disk(task_id)
            if loaded is not None:
                self._tasks[task_id] = loaded
            return loaded

    def update(self, task_id: str, **kwargs: Any) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                record = self._load_disk(task_id)
                if record is None:
                    return None
                self._tasks[task_id] = record
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            record.updated_at = utc_now()
            self._write_disk(record)
            return record
