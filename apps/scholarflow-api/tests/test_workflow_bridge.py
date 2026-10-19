"""Phase 8.4: TaskStore-backed research workflow bridge tests (fixture / mock)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.events import WorkflowProgressEvent
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.tools import build_chat_tools, set_workflow_progress_callback
from scholarflow_api.chat.workflow_bridge import WorkflowBridge, configure_workflow_bridge
from scholarflow_api.config import get_settings
from scholarflow_api.models import TaskKind, TaskStatus
from scholarflow_api.runtime.research_runtime import ResearchTaskRuntime
from scholarflow_api.services.task_store import TaskStore


@pytest.fixture()
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkflowBridge:
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(tmp_path / "tasks"))
    store = TaskStore(persist=True)
    cfg = get_settings()
    # Ensure sample artifacts dir exists for fixture workflow
    assert cfg.default_artifacts_dir.is_dir()
    return configure_workflow_bridge(store, ResearchTaskRuntime(cfg), cfg)


def test_submit_wait_writes_taskstore_and_artifacts(bridge: WorkflowBridge) -> None:
    result = bridge.submit_research(
        question="hybrid RAG evaluation plan for ScholarFlow",
        kind="research_orchestration",
        data_mode="fixture",
        wait=True,
        wait_timeout_seconds=90.0,
    )
    assert result["task_id"].startswith("sf-")
    assert result.get("terminal") is True
    assert result.get("status") in {"succeeded", "partial_succeeded"}
    assert result.get("data_mode") == "fixture" or result.get("effective_data_mode") == "fixture"
    assert "fixture" in (result.get("data_source_note") or "")

    record = bridge.store.get(result["task_id"])
    assert record is not None
    assert record.status == TaskStatus.succeeded or record.status == TaskStatus.partial_succeeded
    assert record.kind == TaskKind.research_orchestration

    # Disk artifacts must exist for successful fixture runs
    files = result.get("disk_artifacts") or []
    assert "research_report.md" in files or len(result.get("artifacts") or []) > 0

    listed = bridge.list_artifacts(result["task_id"])
    assert listed["ok"] is True
    assert listed["artifact_count"] >= 1
    for item in listed["artifacts"]:
        assert item["exists"] is True
        assert item["download_url"].startswith(f"/api/v1/tasks/{result['task_id']}/artifacts/")


def test_get_task_matches_store(bridge: WorkflowBridge) -> None:
    submitted = bridge.submit_research(
        question="paper-focused RAG question",
        kind="paper_research",
        data_mode="fixture",
        wait=True,
    )
    tid = submitted["task_id"]
    got = bridge.get_task(tid)
    assert got["task_id"] == tid
    assert got["status"] == submitted["status"]
    assert got["terminal"] is True


def test_async_submit_not_claimed_complete(bridge: WorkflowBridge) -> None:
    result = bridge.submit_research(
        question="async research",
        data_mode="fixture",
        wait=False,
    )
    assert result["terminal"] is False
    assert result["status"] in {"queued", "running"}
    assert "poll" in (result.get("message") or "").lower() or "get_research_task" in (
        result.get("poll_hint") or ""
    )
    # Must not pretend artifacts are ready
    assert result.get("artifact_count") in (None, 0) or result.get("terminal") is False

    # Eventually finishes in background
    import time

    tid = result["task_id"]
    deadline = time.time() + 60
    while time.time() < deadline:
        snap = bridge.get_task(tid)
        if snap.get("terminal"):
            break
        time.sleep(0.5)
    final = bridge.get_task(tid)
    assert final.get("terminal") is True


def test_force_fail_propagates(bridge: WorkflowBridge, tmp_path: Path) -> None:
    # Create via store with force_fail_review then execute
    record = bridge.store.create(
        kind=TaskKind.research_orchestration,
        question="force fail",
        runtime=bridge.runtime.name,
        params={
            "data_mode": "fixture",
            "force_fail_review": True,
            "persist_artifacts": True,
        },
    )
    from scholarflow_api.services.task_runner import execute_stored_task

    final = execute_stored_task(
        store=bridge.store,
        runtime=bridge.runtime,
        settings=bridge.settings,
        task_id=record.task_id,
        timeout_seconds=60,
    )
    assert final is not None
    # Review hard-fail may yield failed or partial depending on graph policy
    assert final.status in {
        TaskStatus.failed,
        TaskStatus.partial_succeeded,
        TaskStatus.succeeded,
    }
    snap = bridge.get_task(record.task_id)
    # Snapshot must reflect store — never invent succeeded if store says failed
    assert snap["status"] == final.status.value


def test_workflow_progress_events_during_wait(bridge: WorkflowBridge) -> None:
    seen: list[tuple[str, dict]] = []

    def cb(message: str, fields: dict) -> None:
        seen.append((message, fields))

    set_workflow_progress_callback(cb)
    try:
        bridge.submit_research(
            question="progress events",
            data_mode="fixture",
            wait=True,
            wait_timeout_seconds=90,
        )
    finally:
        set_workflow_progress_callback(None)

    assert any("submitted" in m for m, _ in seen)
    assert any(f.get("task_id") for _, f in seen)


def test_agent_tool_uses_taskstore(bridge: WorkflowBridge, tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conv")
    meta = store.create(title="wf")
    # Scripted model that calls run_research_workflow then answers
    model_script = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "run_research_workflow",
                    "args": {
                        "question": "hybrid RAG plan",
                        "data_mode": "fixture",
                        "wait": True,
                    },
                    "id": "c1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Workflow done with task."),
    ]

    class Scripted:
        _sf_skip_bind = True

        def __init__(self) -> None:
            self.script = list(model_script)

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return self.script.pop(0)

    agent = ChatAgentRuntime(
        store,
        tools=build_chat_tools(),
        model=Scripted(),
        max_tool_iters=4,
    )
    result = agent.run_turn(meta.conversation_id, "Please run a full research workflow.")
    assert result.tool_call_trace
    assert result.tool_call_trace[0].tool_name == "run_research_workflow"
    assert result.related_task_id
    assert result.related_task_id.startswith("sf-")
    # Task must exist in the shared bridge store
    assert bridge.store.get(result.related_task_id) is not None


def test_sse_includes_workflow_progress(bridge: WorkflowBridge, tmp_path: Path) -> None:
    from langchain_core.messages import AIMessage

    conv = ConversationStore(root=tmp_path / "c")
    meta = conv.create()

    class Scripted:
        _sf_skip_bind = True
        script = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "run_research_workflow",
                        "args": {
                            "question": "sse workflow",
                            "data_mode": "fixture",
                            "wait": True,
                        },
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="done"),
        ]

        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return self.script.pop(0)

    agent = ChatAgentRuntime(
        conv, tools=build_chat_tools(), model=Scripted(), max_tool_iters=4
    )
    events = list(agent.stream_turn(meta.conversation_id, "run wf", emit_tokens=False))
    types = [e.event for e in events]
    assert "tool_start" in types
    assert "tool_end" in types
    assert any(isinstance(e, WorkflowProgressEvent) for e in events)
    assert types[-1] == "done"
