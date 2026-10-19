"""Light disk persistence for task status across store instances."""

from __future__ import annotations

from scholarflow_api.models import TaskKind, TaskStatus
from scholarflow_api.services.task_store import TaskStore


def test_task_state_survives_new_store_instance(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(tmp_path / "tasks"))
    store_a = TaskStore(persist=True)
    rec = store_a.create(
        kind=TaskKind.rag_query,
        question="persist me",
        runtime="rag_v1",
        params={"data_mode": "fixture"},
    )
    store_a.update(rec.task_id, status=TaskStatus.succeeded, progress="done")

    store_b = TaskStore(persist=True)
    loaded = store_b.get(rec.task_id)
    assert loaded is not None
    assert loaded.status == TaskStatus.succeeded
    assert loaded.question == "persist me"
    assert loaded.runtime == "rag_v1"
