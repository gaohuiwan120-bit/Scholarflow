"""Live SSE streaming tests — require SCHOLARFLOW_LIVE_LLM=1."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.router import create_conversation_router
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.llm.settings import get_llm_settings, load_root_env_into_process, reset_llm_settings_cache

pytestmark = pytest.mark.live_llm


def _live_enabled() -> bool:
    return os.getenv("SCHOLARFLOW_LIVE_LLM", "").strip() in {"1", "true", "TRUE", "yes"}


def _parse_sse(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        data_lines = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


@pytest.fixture()
def live_client(tmp_path: Path):
    if not _live_enabled():
        pytest.skip("Set SCHOLARFLOW_LIVE_LLM=1")
    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    if not get_llm_settings().configured:
        pytest.skip("DEEPSEEK_API_KEY not configured")
    store = ConversationStore(root=tmp_path / "conversations")
    agent = ChatAgentRuntime(store, max_tool_iters=6)
    app = FastAPI()
    app.include_router(create_conversation_router(store, agent))
    return TestClient(app), store


def test_live_sse_token_increments(live_client) -> None:
    client, _ = live_client
    cid = client.post("/api/v1/conversations", json={"title": "live-sse"}).json()[
        "conversation"
    ]["conversation_id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/turns/stream",
        json={
            "content": "Reply with exactly the three words: ONE TWO THREE. No tools."
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(resp.iter_text())
    events = _parse_sse(body)
    names = [e["event"] for e in events]
    assert names[0] == "turn_start"
    assert names[-1] == "done"
    tokens = [e for e in events if e["event"] == "token"]
    assert len(tokens) >= 1, "expected real token deltas from DeepSeek stream"
    joined = "".join(t["text"] for t in tokens)
    assert len(joined) >= 3
    assert events[-1]["status"] in {"completed", "max_iterations", "error"}


def test_live_sse_tool_then_tokens(live_client) -> None:
    client, _ = live_client
    cid = client.post("/api/v1/conversations", json={"title": "live-tool-sse"}).json()[
        "conversation"
    ]["conversation_id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/turns/stream",
        json={
            "content": (
                "Use search_papers to find 1 paper about BM25 retrieval. "
                "Then briefly name the title."
            )
        },
    ) as resp:
        body = "".join(resp.iter_text())
    events = _parse_sse(body)
    names = [e["event"] for e in events]
    assert "tool_start" in names
    assert "tool_end" in names
    # Final answer tokens should appear after tool_end when model continues
    tool_end_idx = max(i for i, e in enumerate(events) if e["event"] == "tool_end")
    later_tokens = [
        e for i, e in enumerate(events) if e["event"] == "token" and i > tool_end_idx
    ]
    assert later_tokens, "expected streamed tokens after tool result re-injection"
    assert names[-1] == "done"
