"""Chat Agent Runtime — real LLM bind_tools loop + SSE streaming (Phase 8.2/8.3).

Uses model-returned tool_calls only. No keyword if/else tool routing.
Streaming uses ChatDeepSeek.stream / AIMessageChunk aggregation — not fake token slicing.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool

from scholarflow_api.chat.events import (
    DoneEvent,
    ErrorEvent,
    SseEventBase,
    TokenEvent,
    ToolEndEvent,
    ToolStartEvent,
    TurnFinalStatus,
    TurnStartEvent,
    WorkflowProgressEvent,
    summarize_args,
)
from scholarflow_api.chat.schemas import (
    ChatMessage,
    EvidenceRef,
    ToolCallTraceItem,
)
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.tools import (
    SYSTEM_PROMPT,
    build_chat_tools,
    set_workflow_progress_callback,
)
from scholarflow_api.chat.turns import TurnHandle, TurnRegistry, default_turn_registry
from scholarflow_api.llm.client import LlmNotConfiguredError, build_chat_model
from scholarflow_api.llm.guards import redact_secrets, safe_exc_message
from scholarflow_api.llm.settings import get_llm_settings
from scholarflow_api.models import utc_now

logger = logging.getLogger("scholarflow_api.chat.agent")

TurnStatus = Literal["completed", "max_iterations", "error", "cancelled", "timeout"]


@dataclass
class AgentTurnResult:
    conversation_id: str
    user_message: ChatMessage
    assistant_message: ChatMessage | None
    tool_call_trace: list[ToolCallTraceItem] = field(default_factory=list)
    related_task_id: str | None = None
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    status: TurnStatus = "completed"
    error: str | None = None
    model: str | None = None
    iterations: int = 0
    latency_ms: float | None = None
    turn_id: str | None = None


class TurnCancelled(Exception):
    """Raised when a turn cancel flag is set mid-execution."""


def _content_to_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def _history_to_lc(messages: list[ChatMessage]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in messages:
        if m.role == "user":
            out.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content))
        elif m.role == "system":
            out.append(SystemMessage(content=m.content))
    return out


def _summarize_tool_result(
    text: str, *, limit: int = 400, tool_name: str | None = None
) -> str:
    if tool_name == "search_papers":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if not data.get("ok"):
                    return redact_secrets(
                        f"search_papers failed: {data.get('error') or 'unknown'}"
                    )[:limit]
                papers = data.get("papers") or []
                titles = [
                    str(p.get("title") or "")[:80]
                    for p in papers
                    if isinstance(p, dict)
                ]
                return redact_secrets(
                    f"ok count={data.get('count', len(papers))} "
                    f"candidates={data.get('candidates_fetched')} "
                    f"reranked={data.get('reranked')} titles={titles}"
                )[:limit]
        except Exception:  # noqa: BLE001
            # Truncated JSON — still surface count if present.
            m = re.search(r'"count"\s*:\s*(\d+)', text or "")
            if m:
                return f"ok count={m.group(1)} (summary truncated)"
            return "search_papers completed (result summary truncated)"
    s = redact_secrets((text or "").replace("\n", " ").strip())
    if len(s) > limit:
        return s[: limit - 3] + "..."
    return s


def _parse_related_task_id(tool_name: str, result_text: str) -> str | None:
    if tool_name not in {
        "run_research_workflow",
        "get_research_task",
        "list_research_artifacts",
    }:
        return None
    try:
        data = json.loads(result_text)
    except Exception:  # noqa: BLE001
        return None
    tid = data.get("task_id")
    return str(tid) if tid else None


def _parse_evidence_refs(tool_name: str, result_text: str) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    try:
        data = json.loads(result_text)
    except Exception:  # noqa: BLE001
        return refs
    if not isinstance(data, dict):
        return refs
    # Allow evidence extraction even when ok=false but papers present? Prefer ok paths.
    if tool_name == "scholar_rag_query" and data.get("ok"):
        for e in data.get("evidence") or []:
            if isinstance(e, dict):
                refs.append(
                    EvidenceRef(
                        evidence_id=e.get("evidence_id"),
                        source_url=e.get("source_url"),
                        title=e.get("title"),
                        kind="rag",
                    )
                )
    elif tool_name == "search_papers" and data.get("ok"):
        from scholarflow_api.chat.paper_rank import sanitize_source_url

        for p in data.get("papers") or []:
            if isinstance(p, dict):
                authors = p.get("authors") or []
                if not isinstance(authors, list):
                    authors = []
                year = p.get("year")
                year_i = int(year) if isinstance(year, int) else None
                score = p.get("relevance_score")
                score_f = float(score) if isinstance(score, (int, float)) else None
                refs.append(
                    EvidenceRef(
                        evidence_id=p.get("evidence_id"),
                        source_url=sanitize_source_url(p.get("source_url")) or None,
                        title=p.get("title"),
                        kind="paper",
                        authors=[str(a) for a in authors if str(a).strip()],
                        year=year_i,
                        abstract=(p.get("abstract") or p.get("research_problem") or None),
                        kind_hint=p.get("kind_hint"),
                        relevance_score=score_f,
                    )
                )
    elif tool_name in {"run_research_workflow", "get_research_task"}:
        for p in data.get("papers") or []:
            if isinstance(p, dict):
                refs.append(
                    EvidenceRef(
                        evidence_id=p.get("evidence_id"),
                        source_url=p.get("source_url"),
                        title=p.get("title"),
                        kind="paper",
                    )
                )
        for r in data.get("repositories") or []:
            if isinstance(r, dict):
                refs.append(
                    EvidenceRef(
                        evidence_id=r.get("evidence_id"),
                        source_url=r.get("source_url"),
                        title=r.get("repository") or r.get("title"),
                        kind="repository",
                    )
                )
    return refs


def _tool_failed(result_text: str) -> tuple[bool, str | None]:
    try:
        data = json.loads(result_text)
        if isinstance(data, dict) and data.get("ok") is False:
            return True, str(data.get("error") or "tool reported failure")
    except Exception:  # noqa: BLE001
        return False, None
    return False, None


def _truncate_any(obj: Any, limit: int = 6000) -> str:
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, default=str)
    text = redact_secrets(text)
    if len(text) > limit:
        return text[: limit - 20] + "\n...[truncated]"
    return text


def _chunk_to_aimessage(acc: AIMessageChunk) -> AIMessage:
    """Convert aggregated stream chunk into a final AIMessage with complete tool_calls."""
    tool_calls = list(getattr(acc, "tool_calls", None) or [])
    # Prefer aggregated tool_calls; fall back to tool_call_chunks only if needed
    if not tool_calls and getattr(acc, "tool_call_chunks", None):
        # LangChain usually fills tool_calls on merge; keep empty if incomplete
        tool_calls = list(acc.tool_calls or [])
    return AIMessage(
        content=acc.content,
        tool_calls=tool_calls,
        additional_kwargs=dict(getattr(acc, "additional_kwargs", None) or {}),
        response_metadata=dict(getattr(acc, "response_metadata", None) or {}),
        id=getattr(acc, "id", None),
    )


class ChatAgentRuntime:
    """Tool-calling agent bound to a ConversationStore (sync + SSE stream)."""

    def __init__(
        self,
        store: ConversationStore,
        *,
        tools: list[BaseTool] | None = None,
        model: Any | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        max_tool_iters: int | None = None,
        turn_registry: TurnRegistry | None = None,
        max_duration_seconds: float | None = None,
    ) -> None:
        self.store = store
        self.tools = tools if tools is not None else build_chat_tools()
        self._tools_by_name = {t.name: t for t in self.tools}
        self._injected_model = model
        self.system_prompt = system_prompt
        cfg = get_llm_settings()
        self.max_tool_iters = max_tool_iters or cfg.max_tool_iters
        self._model_id = cfg.model
        self.turn_registry = turn_registry or default_turn_registry
        self.max_duration_seconds = (
            max_duration_seconds
            if max_duration_seconds is not None
            else self.turn_registry.max_duration_seconds
        )

    def _get_model(self) -> Any:
        if self._injected_model is not None:
            # Injected models may already be bound or scripted
            if hasattr(self._injected_model, "bind_tools") and not getattr(
                self._injected_model, "_sf_skip_bind", False
            ):
                try:
                    return self._injected_model.bind_tools(self.tools)
                except Exception:  # noqa: BLE001
                    return self._injected_model
            return self._injected_model
        base = build_chat_model()
        return base.bind_tools(self.tools)

    def _check_cancel(self, handle: TurnHandle | None) -> None:
        if handle is None:
            return
        if handle.cancelled:
            raise TurnCancelled("client cancelled")
        if (time.monotonic() - handle.created_at) > self.max_duration_seconds:
            handle.request_cancel()
            raise TurnCancelled("turn timeout")

    def _invoke_or_stream_model(
        self,
        model: Any,
        lc_messages: list[BaseMessage],
        *,
        handle: TurnHandle | None,
        conversation_id: str,
        turn_id: str,
        iteration: int,
        emit_tokens: bool,
    ) -> tuple[AIMessage, list[SseEventBase]]:
        """Run one model step. Prefer .stream for real tokens when available."""
        events: list[SseEventBase] = []
        if emit_tokens and hasattr(model, "stream"):
            acc: AIMessageChunk | None = None
            try:
                for chunk in model.stream(lc_messages):
                    self._check_cancel(handle)
                    if not isinstance(chunk, AIMessageChunk):
                        # Some wrappers yield AIMessage directly
                        if isinstance(chunk, AIMessage):
                            return chunk, events
                        continue
                    delta = _content_to_str(chunk.content)
                    if delta:
                        events.append(
                            TokenEvent(
                                turn_id=turn_id,
                                conversation_id=conversation_id,
                                text=delta,
                                iteration=iteration,
                            )
                        )
                    acc = chunk if acc is None else acc + chunk
            except TurnCancelled:
                raise
            except Exception:
                # Fall back to invoke if stream fails mid-way without tokens yet
                if acc is None:
                    self._check_cancel(handle)
                    ai = model.invoke(lc_messages)
                    return ai, events  # type: ignore[return-value]
                raise
            if acc is None:
                # Empty stream — fall back
                ai = model.invoke(lc_messages)
                return ai, events  # type: ignore[return-value]
            return _chunk_to_aimessage(acc), events

        self._check_cancel(handle)
        ai = model.invoke(lc_messages)
        # Sync path: do NOT fake-split content into tokens
        return ai, events  # type: ignore[return-value]

    def _run_one_tool(
        self,
        *,
        name: str,
        args: dict[str, Any],
        call_id: str,
        handle: TurnHandle | None,
    ) -> tuple[ToolCallTraceItem, str]:
        self._check_cancel(handle)
        started = utc_now()
        t0 = time.perf_counter()
        trace = ToolCallTraceItem(
            tool_name=name,
            tool_call_id=str(call_id),
            arguments=args,
            status="running",
            started_at=started,
        )
        tool = self._tools_by_name.get(name)
        if tool is None:
            result_text = json.dumps(
                {"ok": False, "error": f"Unknown tool: {name}"},
                ensure_ascii=False,
            )
            trace.status = "failed"
            trace.error = f"Unknown tool: {name}"
            trace.result_summary = _summarize_tool_result(
                result_text, tool_name=name
            )
            trace.finished_at = utc_now()
            return trace, result_text

        try:
            raw = tool.invoke(args)
            result_text = raw if isinstance(raw, str) else _truncate_any(raw)
        except Exception as exc:  # noqa: BLE001
            result_text = json.dumps(
                {"ok": False, "error": safe_exc_message(exc)},
                ensure_ascii=False,
            )
            trace.status = "failed"
            trace.error = safe_exc_message(exc)
            logger.warning("tool %s failed: %s", name, safe_exc_message(exc))
        else:
            failed, ferr = _tool_failed(result_text)
            if failed:
                trace.status = "failed"
                trace.error = ferr
            else:
                trace.status = "succeeded"

        trace.result_summary = _summarize_tool_result(result_text, tool_name=name)
        trace.finished_at = utc_now()
        # duration stored only in SSE ToolEndEvent
        _ = t0
        return trace, result_text

    def run_turn(self, conversation_id: str, user_content: str) -> AgentTurnResult:
        """Sync turn — consumes stream_turn events without requiring a client."""
        final: AgentTurnResult | None = None
        for ev in self.stream_turn(conversation_id, user_content, emit_tokens=False):
            if isinstance(ev, DoneEvent):
                # Reconstruct from store
                msgs = self.store.list_messages(conversation_id)
                user_msg = next(
                    (m for m in reversed(msgs) if m.role == "user"),
                    msgs[0] if msgs else None,
                )
                asst = next(
                    (m for m in reversed(msgs) if m.role == "assistant"),
                    None,
                )
                if user_msg is None:
                    raise RuntimeError("turn finished without user message")
                final = AgentTurnResult(
                    conversation_id=conversation_id,
                    user_message=user_msg,
                    assistant_message=asst,
                    tool_call_trace=list(asst.tool_call_trace) if asst else [],
                    related_task_id=asst.related_task_id if asst else None,
                    evidence_refs=list(asst.evidence_refs) if asst else [],
                    status=ev.status,  # type: ignore[arg-type]
                    error=ev.error,
                    model=self._model_id,
                    iterations=ev.iterations,
                    latency_ms=ev.latency_ms,
                    turn_id=ev.turn_id,
                )
        if final is None:
            raise RuntimeError("stream_turn ended without done event")
        return final

    def stream_turn(
        self,
        conversation_id: str,
        user_content: str,
        *,
        emit_tokens: bool = True,
        handle: TurnHandle | None = None,
    ) -> Iterator[SseEventBase]:
        """Yield real SSE events while executing one agent turn."""
        t0 = time.perf_counter()
        text = (user_content or "").strip()
        if not text:
            raise ValueError("user content must not be empty")

        own_handle = handle is None
        if handle is None:
            handle = self.turn_registry.begin(conversation_id)
        turn_id = handle.turn_id

        prior = self.store.list_messages(conversation_id)
        user_msg = self.store.append_message(
            conversation_id, role="user", content=text
        )

        yield TurnStartEvent(
            turn_id=turn_id,
            conversation_id=conversation_id,
            user_message_id=user_msg.message_id,
            model=self._model_id,
        )

        traces: list[ToolCallTraceItem] = []
        evidence_refs: list[EvidenceRef] = []
        related_task_id: str | None = None
        iterations = 0
        status: TurnFinalStatus = "completed"
        error: str | None = None
        final_text = ""
        progress_events: list[WorkflowProgressEvent] = []

        def _progress(message: str, fields: dict[str, Any]) -> None:
            progress_events.append(
                WorkflowProgressEvent(
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                    message=message,
                    task_id=fields.get("task_id"),
                    overall_status=fields.get("overall_status"),
                )
            )

        set_workflow_progress_callback(_progress)
        try:
            try:
                model = self._get_model()
            except LlmNotConfiguredError as exc:
                err = safe_exc_message(exc)
                yield ErrorEvent(
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                    message=err,
                    stage="model_init",
                )
                asst = self.store.append_message(
                    conversation_id,
                    role="assistant",
                    content=f"LLM is not configured: {err}",
                    tool_call_trace=[],
                )
                yield DoneEvent(
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                    status="error",
                    assistant_message_id=asst.message_id,
                    error=err,
                    iterations=0,
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
                return

            lc_messages: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]
            lc_messages.extend(_history_to_lc(prior))
            lc_messages.append(HumanMessage(content=text))

            try:
                for _ in range(self.max_tool_iters):
                    self._check_cancel(handle)
                    iterations += 1
                    ai, token_events = self._invoke_or_stream_model(
                        model,
                        lc_messages,
                        handle=handle,
                        conversation_id=conversation_id,
                        turn_id=turn_id,
                        iteration=iterations,
                        emit_tokens=emit_tokens,
                    )
                    for te in token_events:
                        yield te

                    lc_messages.append(ai)
                    tool_calls = getattr(ai, "tool_calls", None) or []
                    if not tool_calls:
                        final_text = _content_to_str(ai.content).strip()
                        # If sync path (no stream tokens) but we want tokens for tests
                        # with scripted models — do not fabricate.
                        break

                    for tc in tool_calls:
                        self._check_cancel(handle)
                        name = (
                            tc.get("name")
                            if isinstance(tc, dict)
                            else getattr(tc, "name", None)
                        )
                        args = (
                            tc.get("args")
                            if isinstance(tc, dict)
                            else getattr(tc, "args", {})
                        )
                        call_id = (
                            tc.get("id")
                            if isinstance(tc, dict)
                            else getattr(tc, "id", None)
                        ) or f"call-{iterations}-{name}"
                        name = str(name or "unknown")
                        args = dict(args or {})
                        # Tool calls are executed only after full stream aggregation
                        # into AIMessage.tool_calls (never mid-chunk).

                        yield ToolStartEvent(
                            turn_id=turn_id,
                            conversation_id=conversation_id,
                            tool_name=name,
                            tool_call_id=str(call_id),
                            arguments_summary=summarize_args(args),
                        )
                        tool_t0 = time.perf_counter()
                        # Drain any progress events produced during tool run
                        progress_events.clear()
                        trace, result_text = self._run_one_tool(
                            name=name,
                            args=args,
                            call_id=str(call_id),
                            handle=handle,
                        )
                        for pe in progress_events:
                            yield pe
                        progress_events.clear()

                        duration_ms = int((time.perf_counter() - tool_t0) * 1000)
                        traces.append(trace)
                        if trace.status == "succeeded":
                            tid = _parse_related_task_id(name, result_text)
                            if tid:
                                related_task_id = tid
                            evidence_refs.extend(
                                _parse_evidence_refs(name, result_text)
                            )

                        yield ToolEndEvent(
                            turn_id=turn_id,
                            conversation_id=conversation_id,
                            tool_name=name,
                            tool_call_id=str(call_id),
                            status="succeeded" if trace.status == "succeeded" else "failed",
                            duration_ms=duration_ms,
                            result_summary=trace.result_summary,
                            error=trace.error,
                        )
                        lc_messages.append(
                            ToolMessage(content=result_text, tool_call_id=str(call_id))
                        )
                else:
                    status = "max_iterations"
                    final_text = (
                        "Stopped: reached maximum tool-calling iterations "
                        f"({self.max_tool_iters}) without a final answer."
                    )
                    error = "max_tool_iterations"

                if not final_text and status == "completed":
                    final_text = (
                        "I could not produce a final answer after tool calls. "
                        "Please retry or rephrase."
                    )
                    status = "error"
                    error = "empty_final_answer"

            except TurnCancelled as exc:
                msg = str(exc)
                if "timeout" in msg:
                    status = "timeout"
                    error = "turn_timeout"
                    final_text = (
                        final_text
                        or "Stopped: turn exceeded maximum duration."
                    )
                else:
                    status = "cancelled"
                    error = "cancelled"
                    final_text = (
                        final_text
                        or "Stopped: generation cancelled."
                    )
                yield ErrorEvent(
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                    message=final_text,
                    stage=status,
                )
            except Exception as exc:  # noqa: BLE001
                status = "error"
                error = safe_exc_message(exc)
                final_text = f"Agent error: {error}"
                logger.error("agent turn failed: %s", error)
                yield ErrorEvent(
                    turn_id=turn_id,
                    conversation_id=conversation_id,
                    message=error,
                    stage="agent",
                )

            deduped: list[EvidenceRef] = []
            seen: set[str] = set()
            for ref in evidence_refs:
                key = f"{ref.evidence_id}|{ref.source_url}|{ref.title}"
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(ref)

            asst = self.store.append_message(
                conversation_id,
                role="assistant",
                content=final_text or "(empty)",
                related_task_id=related_task_id,
                evidence_refs=deduped,
                tool_call_trace=traces,
            )
            yield DoneEvent(
                turn_id=turn_id,
                conversation_id=conversation_id,
                status=status,
                assistant_message_id=asst.message_id,
                related_task_id=related_task_id,
                iterations=iterations,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                error=error,
            )
        finally:
            # Prefer set(None) over token.reset — StreamingResponse may run the
            # generator in a different ContextVar context than begin().
            try:
                set_workflow_progress_callback(None)
            except Exception:  # noqa: BLE001
                pass
            if own_handle:
                self.turn_registry.finish(turn_id)
