"""Live DeepSeek tool-calling tests — require SCHOLARFLOW_LIVE_LLM=1.

These assert real model-returned tool_calls when applicable.
They do NOT hardcode tool routing. Skipped when key/live flag missing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.llm.settings import get_llm_settings, load_root_env_into_process, reset_llm_settings_cache

pytestmark = pytest.mark.live_llm


def _live_enabled() -> bool:
    return os.getenv("SCHOLARFLOW_LIVE_LLM", "").strip() in {"1", "true", "TRUE", "yes"}


@pytest.fixture()
def live_agent(tmp_path: Path) -> tuple[ChatAgentRuntime, ConversationStore]:
    if not _live_enabled():
        pytest.skip("Set SCHOLARFLOW_LIVE_LLM=1 for live agent tests")
    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    if not get_llm_settings().configured:
        pytest.skip("DEEPSEEK_API_KEY not configured")
    store = ConversationStore(root=tmp_path / "conversations")
    agent = ChatAgentRuntime(store, max_tool_iters=6)
    return agent, store


def test_live_direct_answer_no_forced_tool(live_agent) -> None:
    agent, store = live_agent
    meta = store.create(title="live-direct")
    result = agent.run_turn(
        meta.conversation_id,
        "Reply with exactly the word READY and nothing else. Do not use any tools.",
    )
    assert result.status in {"completed", "error", "max_iterations"}
    assert result.assistant_message is not None
    # Model may still call tools; if it obeyed, trace empty and READY present
    content = result.assistant_message.content.upper()
    if not result.tool_call_trace:
        assert "READY" in content


def test_live_search_papers_autonomous(live_agent) -> None:
    agent, store = live_agent
    meta = store.create(title="live-papers")
    result = agent.run_turn(
        meta.conversation_id,
        "Find 2 recent academic papers about retrieval-augmented generation on arXiv. "
        "You must use the search_papers tool. Then summarize titles and URLs.",
    )
    names = [t.tool_name for t in result.tool_call_trace]
    # Record-only soft assert: if model ignored tools, fail honestly
    assert "search_papers" in names, (
        f"Model did not call search_papers. traces={names} "
        f"status={result.status} answer={(result.assistant_message.content or '')[:200]}"
    )
    assert result.assistant_message is not None
    assert result.assistant_message.content.strip()


def test_live_rag_or_workflow_choice(live_agent) -> None:
    """Ask for corpus / full research — accept either RAG or workflow tool."""
    agent, store = live_agent
    meta = store.create(title="live-rag-or-wf")
    result = agent.run_turn(
        meta.conversation_id,
        "Using ScholarFlow tools, answer from the local research corpus if possible: "
        "What evidence exists about hybrid RAG and BM25? "
        "Prefer scholar_rag_query; if you need a full task pipeline use run_research_workflow "
        "with data_mode=fixture.",
    )
    names = [t.tool_name for t in result.tool_call_trace]
    assert any(n in names for n in ("scholar_rag_query", "run_research_workflow")), (
        f"Expected RAG or workflow tool. traces={names} "
        f"answer={(result.assistant_message.content or '')[:200]}"
    )


def test_live_history_isolation(live_agent) -> None:
    agent, store = live_agent
    a = store.create(title="iso-a")
    b = store.create(title="iso-b")
    agent.run_turn(a.conversation_id, "Remember the codeword ALPHA-ONLY for this chat. Reply OK.")
    agent.run_turn(b.conversation_id, "Remember the codeword BETA-ONLY for this chat. Reply OK.")
    ra = agent.run_turn(a.conversation_id, "What codeword did I ask you to remember? Answer with the codeword only.")
    rb = agent.run_turn(b.conversation_id, "What codeword did I ask you to remember? Answer with the codeword only.")
    ca = (ra.assistant_message.content or "").upper()
    cb = (rb.assistant_message.content or "").upper()
    # Soft isolation check: A's answer should not prefer BETA if ALPHA present
    assert "BETA" not in ca or "ALPHA" in ca
    assert "ALPHA" not in cb or "BETA" in cb
