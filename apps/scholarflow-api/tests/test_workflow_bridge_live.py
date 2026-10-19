"""Live DeepSeek + fixture research workflow integration (Phase 8.4).

This is REAL LLM tool-calling + fixture workflow data — not full live MCP E2E.
Requires SCHOLARFLOW_LIVE_LLM=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.workflow_bridge import configure_workflow_bridge, get_workflow_bridge
from scholarflow_api.config import get_settings
from scholarflow_api.llm.settings import get_llm_settings, load_root_env_into_process, reset_llm_settings_cache
from scholarflow_api.runtime.research_runtime import ResearchTaskRuntime
from scholarflow_api.services.task_store import TaskStore

pytestmark = pytest.mark.live_llm


def _live_enabled() -> bool:
    return os.getenv("SCHOLARFLOW_LIVE_LLM", "").strip() in {"1", "true", "TRUE", "yes"}


def test_live_agent_delegates_to_research_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not _live_enabled():
        pytest.skip("Set SCHOLARFLOW_LIVE_LLM=1")
    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    if not get_llm_settings().configured:
        pytest.skip("DEEPSEEK_API_KEY not configured")

    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(tmp_path / "tasks"))
    store = TaskStore(persist=True)
    cfg = get_settings()
    configure_workflow_bridge(store, ResearchTaskRuntime(cfg), cfg)

    conv = ConversationStore(root=tmp_path / "conversations")
    meta = conv.create(title="live-wf")
    agent = ChatAgentRuntime(conv, max_tool_iters=6)
    result = agent.run_turn(
        meta.conversation_id,
        "Please run a full ScholarFlow research workflow with data_mode=fixture "
        "on: hybrid RAG evaluation plan. Use run_research_workflow with wait=true. "
        "Then report the real task_id and status from the tool result.",
    )
    names = [t.tool_name for t in result.tool_call_trace]
    assert "run_research_workflow" in names, (
        f"Model did not call run_research_workflow; traces={names} "
        f"answer={(result.assistant_message.content or '')[:240]}"
    )
    assert result.related_task_id
    record = get_workflow_bridge().store.get(result.related_task_id)
    assert record is not None, "task_id not found in TaskStore"
    assert record.status.value in {
        "succeeded",
        "partial_succeeded",
        "failed",
        "timed_out",
    }
    # Final answer must not invent success if store failed
    answer = (result.assistant_message.content or "").lower()
    if record.status.value == "failed":
        assert "succeed" not in answer or "fail" in answer
    assert result.status in {"completed", "max_iterations", "error"}
