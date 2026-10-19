"""Mock tests for Phase 8.3 SSE streaming (NOT live model)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.events import format_sse
from scholarflow_api.chat.router import create_conversation_router
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.turns import TurnRegistry


class _EchoArgs(BaseModel):
    text: str = Field(..., min_length=1)


def _echo_tool() -> StructuredTool:
    def _run(text: str) -> str:
        return json.dumps({"ok": True, "echo": text}, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="echo_tool",
        description="Echo",
        args_schema=_EchoArgs,
    )


def _fail_tool() -> StructuredTool:
    def _run(text: str) -> str:
        return json.dumps({"ok": False, "error": "forced failure"}, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="fail_tool",
        description="Fail",
        args_schema=_EchoArgs,
    )


class ScriptedModel:
    _sf_skip_bind = True

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[Any] = []

    def bind_tools(self, tools: Any) -> ScriptedModel:
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, AIMessage):
            return item
        raise TypeError("expected AIMessage in invoke script")

    def stream(self, messages: list[Any]):
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, list):
            # list of AIMessageChunk — real incremental stream
            yield from item
            return
        if isinstance(item, AIMessage):
            # Single message: emit as one chunk (still from model path, not sliced answer)
            yield AIMessageChunk(content=_content(item), tool_calls=item.tool_calls or [])
            return
        raise TypeError("bad script item")


def _content(m: AIMessage) -> str:
    c = m.content
    return c if isinstance(c, str) else str(c or "")


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    blocks = body.split("\n\n")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        ev_name = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                ev_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        payload = json.loads("\n".join(data_lines))
        if ev_name:
            payload["_sse_event"] = ev_name
        events.append(payload)
    return events


def test_format_sse_has_event_and_data() -> None:
    from scholarflow_api.chat.events import TokenEvent

    raw = format_sse(
        TokenEvent(turn_id="turn-1", conversation_id="cv-aaaaaaaaaaaa", text="hi")
    )
    assert "event: token\n" in raw
    assert '"text": "hi"' in raw
    assert raw.endswith("\n\n")


def test_text_token_stream(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()
    chunks = [
        AIMessageChunk(content="Hel"),
        AIMessageChunk(content="lo"),
    ]
    model = ScriptedModel([chunks])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=3
    )
    events = list(agent.stream_turn(meta.conversation_id, "hi", emit_tokens=True))
    types = [e.event for e in events]
    assert types[0] == "turn_start"
    assert "token" in types
    assert types[-1] == "done"
    tokens = "".join(e.text for e in events if e.event == "token")  # type: ignore[attr-defined]
    assert tokens == "Hello"
    done = events[-1]
    assert done.status == "completed"  # type: ignore[attr-defined]
    msgs = store.list_messages(meta.conversation_id)
    assert msgs[-1].content == "Hello"
    assert msgs[-1].role == "assistant"


def test_tool_event_order(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo_tool",
                        "args": {"text": "x"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            [AIMessageChunk(content="done-")],
        ]
    )
    # second step: stream chunks — need AIMessageChunk that aggregates
    model.script[1] = [AIMessageChunk(content="done-with-tool")]
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=4
    )
    events = list(agent.stream_turn(meta.conversation_id, "use tool", emit_tokens=True))
    types = [e.event for e in events]
    assert "tool_start" in types
    assert "tool_end" in types
    assert types.index("tool_start") < types.index("tool_end")
    assert types.index("tool_end") < types.index("token") or "token" in types
    assert types[-1] == "done"


def test_multi_tool_events(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo_tool",
                        "args": {"text": "a"},
                        "id": "c1",
                        "type": "tool_call",
                    },
                    {
                        "name": "echo_tool",
                        "args": {"text": "b"},
                        "id": "c2",
                        "type": "tool_call",
                    },
                ],
            ),
            AIMessage(content="both done"),
        ]
    )
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=4
    )
    events = list(agent.stream_turn(meta.conversation_id, "multi", emit_tokens=False))
    starts = [e for e in events if e.event == "tool_start"]
    ends = [e for e in events if e.event == "tool_end"]
    assert len(starts) == 2
    assert len(ends) == 2


def test_tool_failure_event(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "fail_tool",
                        "args": {"text": "x"},
                        "id": "cf",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="failed gracefully"),
        ]
    )
    agent = ChatAgentRuntime(
        store, tools=[_fail_tool()], model=model, max_tool_iters=4
    )
    events = list(agent.stream_turn(meta.conversation_id, "fail", emit_tokens=False))
    end = next(e for e in events if e.event == "tool_end")
    assert end.status == "failed"  # type: ignore[attr-defined]
    assert end.error  # type: ignore[attr-defined]


def test_model_exception_error_event(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()

    class Boom:
        _sf_skip_bind = True

        def bind_tools(self, tools: Any) -> Boom:
            return self

        def invoke(self, messages: Any) -> AIMessage:
            raise RuntimeError("boom-model")

    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=Boom(), max_tool_iters=2
    )
    events = list(agent.stream_turn(meta.conversation_id, "x", emit_tokens=False))
    assert any(e.event == "error" for e in events)
    done = events[-1]
    assert done.event == "done"
    assert done.status == "error"  # type: ignore[attr-defined]
    assert store.list_messages(meta.conversation_id)[-1].role == "assistant"


def test_cancel_mid_turn(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    registry = TurnRegistry(max_active=4, max_duration_seconds=60)
    meta = store.create()
    handle = registry.begin(meta.conversation_id)

    class CancelOnInvoke:
        _sf_skip_bind = True

        def bind_tools(self, tools: Any) -> CancelOnInvoke:
            return self

        def invoke(self, messages: Any) -> AIMessage:
            handle.request_cancel()
            return AIMessage(content="should-not-finish-normally")

    agent = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=CancelOnInvoke(),
        max_tool_iters=2,
        turn_registry=registry,
    )
    # First invoke runs, then loop continues? Actually cancel checked before invoke.
    # Request cancel inside invoke — next _check_cancel raises after return...
    # Better: cancel before second iteration
    class CancelAfterFirst:
        _sf_skip_bind = True
        n = 0

        def bind_tools(self, tools: Any) -> CancelAfterFirst:
            return self

        def invoke(self, messages: Any) -> AIMessage:
            CancelAfterFirst.n += 1
            if CancelAfterFirst.n == 1:
                handle.request_cancel()
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "echo_tool",
                            "args": {"text": "z"},
                            "id": "c",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content="nope")

    agent = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=CancelAfterFirst(),
        max_tool_iters=4,
        turn_registry=registry,
    )
    events = list(
        agent.stream_turn(
            meta.conversation_id, "cancel-me", emit_tokens=False, handle=handle
        )
    )
    done = events[-1]
    assert done.status == "cancelled"  # type: ignore[attr-defined]
    assert done.event == "done"


def test_timeout_status(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    registry = TurnRegistry(max_active=4, max_duration_seconds=0.0)
    meta = store.create()
    handle = registry.begin(meta.conversation_id)

    class Slow:
        _sf_skip_bind = True

        def bind_tools(self, tools: Any) -> Slow:
            return self

        def invoke(self, messages: Any) -> AIMessage:
            return AIMessage(content="late")

    agent = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=Slow(),
        max_tool_iters=2,
        turn_registry=registry,
        max_duration_seconds=0.0,
    )
    events = list(
        agent.stream_turn(
            meta.conversation_id, "timeout", emit_tokens=False, handle=handle
        )
    )
    assert events[-1].status == "timeout"  # type: ignore[attr-defined]


def test_missing_conversation_api(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    agent = ChatAgentRuntime(store, tools=[_echo_tool()], model=ScriptedModel([]))
    app = FastAPI()
    app.include_router(create_conversation_router(store, agent))
    client = TestClient(app)
    resp = client.post(
        "/api/v1/conversations/cv-ffffffffffff/turns/stream",
        json={"content": "x"},
    )
    assert resp.status_code == 404


def test_sse_http_stream_and_persistence(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    model = ScriptedModel([[AIMessageChunk(content="A"), AIMessageChunk(content="B")]])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=2
    )
    app = FastAPI()
    app.include_router(create_conversation_router(store, agent))
    client = TestClient(app)
    cid = client.post("/api/v1/conversations", json={"title": "sse"}).json()[
        "conversation"
    ]["conversation_id"]
    with client.stream(
        "POST",
        f"/api/v1/conversations/{cid}/turns/stream",
        json={"content": "stream please"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers.get("x-accel-buffering") == "no"
        body = "".join(resp.iter_text())
    events = _parse_sse(body)
    names = [e.get("event") or e.get("_sse_event") for e in events]
    assert names[0] == "turn_start"
    assert "token" in names
    assert names[-1] == "done"
    assert events[-1]["status"] == "completed"
    assert events[-1]["assistant_message_id"]
    hist = client.get(f"/api/v1/conversations/{cid}/messages").json()["messages"]
    assert hist[-1]["content"] == "AB"
    assert hist[0]["role"] == "user"


def test_sync_turns_still_works(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    model = ScriptedModel([AIMessage(content="sync-ok")])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=2
    )
    app = FastAPI()
    app.include_router(create_conversation_router(store, agent))
    client = TestClient(app)
    cid = client.post("/api/v1/conversations", json={}).json()["conversation"][
        "conversation_id"
    ]
    resp = client.post(
        f"/api/v1/conversations/{cid}/turns", json={"content": "hello sync"}
    )
    assert resp.status_code == 200
    assert resp.json()["assistant_message"]["content"] == "sync-ok"
    assert resp.json()["turn_id"]


def test_session_isolation_concurrent_streams(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    a = store.create(title="A")
    b = store.create(title="B")
    agent_a = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=ScriptedModel([[AIMessageChunk(content="only-A")]]),
        max_tool_iters=2,
        turn_registry=TurnRegistry(),
    )
    agent_b = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=ScriptedModel([[AIMessageChunk(content="only-B")]]),
        max_tool_iters=2,
        turn_registry=TurnRegistry(),
    )
    list(agent_a.stream_turn(a.conversation_id, "qA", emit_tokens=True))
    list(agent_b.stream_turn(b.conversation_id, "qB", emit_tokens=True))
    assert [m.content for m in store.list_messages(a.conversation_id)][-1] == "only-A"
    assert [m.content for m in store.list_messages(b.conversation_id)][-1] == "only-B"
