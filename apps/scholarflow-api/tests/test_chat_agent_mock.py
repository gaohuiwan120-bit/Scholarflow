"""Mock / unit tests for ChatAgentRuntime (NOT live model autonomy)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.tools import (
    SearchPapersArgs,
    ScholarRagQueryArgs,
    build_chat_tools,
)


class _EchoArgs(BaseModel):
    text: str = Field(..., min_length=1)


def _echo_tool() -> StructuredTool:
    def _run(text: str) -> str:
        return json.dumps({"ok": True, "echo": text}, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="echo_tool",
        description="Echo text for mock tests",
        args_schema=_EchoArgs,
    )


def _fail_tool() -> StructuredTool:
    def _run(text: str) -> str:
        return json.dumps({"ok": False, "error": "forced failure"}, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_run,
        name="fail_tool",
        description="Always fails",
        args_schema=_EchoArgs,
    )


class ScriptedModel:
    """Deterministic stand-in that returns scripted AIMessages (mock only)."""

    def __init__(self, script: list[AIMessage]) -> None:
        self.script = list(script)
        self.calls: list[list[Any]] = []

    def bind_tools(self, tools: Any) -> ScriptedModel:
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(messages)
        if not self.script:
            return AIMessage(content="(script exhausted)")
        return self.script.pop(0)


def test_build_chat_tools_names() -> None:
    names = {t.name for t in build_chat_tools()}
    assert names == {
        "scholar_rag_query",
        "search_papers",
        "run_research_workflow",
        "get_research_task",
        "list_research_artifacts",
    }


def test_tool_args_schema_validation() -> None:
    with pytest.raises(Exception):
        ScholarRagQueryArgs(question="x")  # too short after strip rules via min_length=2
    ok = SearchPapersArgs(query="transformers retrieval", max_results=2)
    assert ok.max_results == 2


def test_direct_answer_no_tools(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create(title="direct")
    model = ScriptedModel([AIMessage(content="Hello, I am ScholarFlow.")])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=4
    )
    result = agent.run_turn(meta.conversation_id, "Say hello briefly.")
    assert result.status == "completed"
    assert result.tool_call_trace == []
    assert "ScholarFlow" in (result.assistant_message.content if result.assistant_message else "")
    msgs = store.list_messages(meta.conversation_id)
    assert [m.role for m in msgs] == ["user", "assistant"]


def test_tool_then_final_answer(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create(title="tool")
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "echo_tool",
                        "args": {"text": "alpha"},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Tool said alpha."),
        ]
    )
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=4
    )
    result = agent.run_turn(meta.conversation_id, "Use the echo tool on alpha.")
    assert result.status == "completed"
    assert len(result.tool_call_trace) == 1
    assert result.tool_call_trace[0].tool_name == "echo_tool"
    assert result.tool_call_trace[0].status == "succeeded"
    assert "alpha" in (result.assistant_message.content or "")
    # Second model call must have received a ToolMessage
    assert any(
        isinstance(m, ToolMessage) for batch in model.calls for m in batch
    ) or any(isinstance(m, ToolMessage) for m in model.calls[-1])


def test_tool_failure_recorded(tmp_path: Path) -> None:
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
                        "id": "call-f",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="The tool failed; I report the error."),
        ]
    )
    agent = ChatAgentRuntime(
        store, tools=[_fail_tool()], model=model, max_tool_iters=4
    )
    result = agent.run_turn(meta.conversation_id, "Call fail_tool.")
    assert result.tool_call_trace[0].status == "failed"
    assert result.tool_call_trace[0].error
    assert result.status == "completed"


def test_max_iterations(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()

    def _always_tool() -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "echo_tool",
                    "args": {"text": "loop"},
                    "id": "call-loop",
                    "type": "tool_call",
                }
            ],
        )

    model = ScriptedModel([_always_tool(), _always_tool(), _always_tool()])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=2
    )
    result = agent.run_turn(meta.conversation_id, "Loop tools.")
    assert result.status == "max_iterations"
    assert result.iterations == 2
    assert len(result.tool_call_trace) == 2


def test_session_isolation(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    a = store.create(title="A")
    b = store.create(title="B")
    agent_a = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=ScriptedModel([AIMessage(content="answer-A")]),
        max_tool_iters=2,
    )
    agent_b = ChatAgentRuntime(
        store,
        tools=[_echo_tool()],
        model=ScriptedModel([AIMessage(content="answer-B")]),
        max_tool_iters=2,
    )
    agent_a.run_turn(a.conversation_id, "q-A")
    agent_b.run_turn(b.conversation_id, "q-B")
    assert [m.content for m in store.list_messages(a.conversation_id)] == [
        "q-A",
        "answer-A",
    ]
    assert [m.content for m in store.list_messages(b.conversation_id)] == [
        "q-B",
        "answer-B",
    ]


def test_history_passed_to_model(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "c")
    meta = store.create()
    store.append_message(meta.conversation_id, role="user", content="prior-user")
    store.append_message(meta.conversation_id, role="assistant", content="prior-asst")
    model = ScriptedModel([AIMessage(content="follow-up")])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=2
    )
    agent.run_turn(meta.conversation_id, "new-question")
    first_call = model.calls[0]
    roles = [type(m).__name__ for m in first_call]
    assert roles[0] == "SystemMessage"
    texts = [_safe_content(m) for m in first_call]
    assert "prior-user" in texts
    assert "prior-asst" in texts
    assert "new-question" in texts


def _safe_content(m: Any) -> str:
    c = getattr(m, "content", "")
    return c if isinstance(c, str) else str(c)


def test_turns_api_with_scripted_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scholarflow_api.chat.router import create_conversation_router

    store = ConversationStore(root=tmp_path / "c")
    model = ScriptedModel([AIMessage(content="api-ok")])
    agent = ChatAgentRuntime(
        store, tools=[_echo_tool()], model=model, max_tool_iters=2
    )
    app = FastAPI()
    app.include_router(create_conversation_router(store, agent))
    client = TestClient(app)
    cid = client.post("/api/v1/conversations", json={"title": "t"}).json()[
        "conversation"
    ]["conversation_id"]
    resp = client.post(
        f"/api/v1/conversations/{cid}/turns",
        json={"content": "hello agent"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["assistant_message"]["content"] == "api-ok"
    assert body["tool_call_trace"] == []
