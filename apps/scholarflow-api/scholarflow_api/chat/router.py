"""Conversation REST API (store + sync turns + SSE stream)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.events import format_sse
from scholarflow_api.chat.schemas import (
    AgentTurnRequest,
    AgentTurnResponse,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetail,
    ConversationListResponse,
    ConversationTasksResponse,
    MessageCreateRequest,
    MessageListResponse,
    TurnCancelResponse,
)
from scholarflow_api.chat.store import (
    ConversationCorruptError,
    ConversationInvalidIdError,
    ConversationNotFoundError,
    ConversationStore,
)
from scholarflow_api.llm.client import LlmNotConfiguredError
from scholarflow_api.llm.guards import safe_exc_message

logger = logging.getLogger("scholarflow_api.chat.router")

_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _http_from_store(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationInvalidIdError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ConversationNotFoundError):
        return HTTPException(status_code=404, detail=f"Conversation not found: {exc}")
    if isinstance(exc, ConversationCorruptError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Internal conversation store error")


def create_conversation_router(
    store: ConversationStore,
    agent: ChatAgentRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
    runtime = agent or ChatAgentRuntime(store)

    @router.post("", response_model=ConversationCreateResponse)
    def create_conversation(body: ConversationCreateRequest) -> ConversationCreateResponse:
        meta = store.create(title=body.title, metadata=body.metadata)
        return ConversationCreateResponse(conversation=meta)

    @router.get("", response_model=ConversationListResponse)
    def list_conversations() -> ConversationListResponse:
        items = store.list_conversations()
        return ConversationListResponse(conversations=items, total=len(items))

    @router.get("/{conversation_id}", response_model=ConversationDetail)
    def get_conversation(conversation_id: str) -> ConversationDetail:
        try:
            meta = store.get(conversation_id)
            return ConversationDetail.model_validate(meta.model_dump())
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

    @router.delete("/{conversation_id}")
    def delete_conversation(conversation_id: str) -> dict[str, str]:
        """Delete one conversation and its message history from disk."""
        try:
            store.delete(conversation_id)
            return {"conversation_id": conversation_id, "status": "deleted"}
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

    @router.get("/{conversation_id}/messages", response_model=MessageListResponse)
    def get_messages(conversation_id: str) -> MessageListResponse:
        try:
            messages = store.list_messages(conversation_id)
            return MessageListResponse(
                conversation_id=conversation_id,
                messages=messages,
                total=len(messages),
            )
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

    @router.post("/{conversation_id}/messages", response_model=MessageListResponse)
    def append_message(conversation_id: str, body: MessageCreateRequest) -> MessageListResponse:
        """Phase 8.1: persist message only (no LLM invoke / SSE)."""
        try:
            store.append_message(
                conversation_id,
                role=body.role,
                content=body.content,
                related_task_id=body.related_task_id,
                evidence_refs=body.evidence_refs,
                tool_call_trace=body.tool_call_trace,
            )
            messages = store.list_messages(conversation_id)
            return MessageListResponse(
                conversation_id=conversation_id,
                messages=messages,
                total=len(messages),
            )
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

    @router.post("/{conversation_id}/turns", response_model=AgentTurnResponse)
    def run_agent_turn(conversation_id: str, body: AgentTurnRequest) -> AgentTurnResponse:
        """Phase 8.2: synchronous agent turn (kept for regression / simple clients)."""
        try:
            store.get(conversation_id)
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc
        try:
            result = runtime.run_turn(conversation_id, body.content)
        except LlmNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=safe_exc_message(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500, detail=safe_exc_message(exc)
            ) from exc
        return AgentTurnResponse(
            conversation_id=result.conversation_id,
            user_message=result.user_message,
            assistant_message=result.assistant_message,
            tool_call_trace=result.tool_call_trace,
            related_task_id=result.related_task_id,
            evidence_refs=result.evidence_refs,
            status=result.status,
            error=result.error,
            model=result.model,
            iterations=result.iterations,
            latency_ms=result.latency_ms,
            turn_id=result.turn_id,
        )

    @router.post("/{conversation_id}/turns/stream")
    async def stream_agent_turn(
        conversation_id: str,
        body: AgentTurnRequest,
        request: Request,
    ) -> StreamingResponse:
        """Phase 8.3: real SSE stream of agent turn events."""
        try:
            store.get(conversation_id)
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

        try:
            handle = runtime.turn_registry.begin(conversation_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

        def event_generator() -> Iterator[str]:
            try:
                for ev in runtime.stream_turn(
                    conversation_id,
                    body.content,
                    emit_tokens=True,
                    handle=handle,
                ):
                    # Best-effort disconnect detection (ASGI)
                    if getattr(request, "is_disconnected", None):
                        # is_disconnected is async — check via sync flag if present
                        pass
                    yield format_sse(ev)
            except GeneratorExit:
                handle.request_cancel()
                logger.info("SSE client disconnected turn=%s", handle.turn_id)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("SSE stream failed: %s", safe_exc_message(exc))
                from scholarflow_api.chat.events import DoneEvent, ErrorEvent

                yield format_sse(
                    ErrorEvent(
                        turn_id=handle.turn_id,
                        conversation_id=conversation_id,
                        message=safe_exc_message(exc),
                        stage="stream",
                    )
                )
                yield format_sse(
                    DoneEvent(
                        turn_id=handle.turn_id,
                        conversation_id=conversation_id,
                        status="error",
                        error=safe_exc_message(exc),
                    )
                )
            finally:
                runtime.turn_registry.finish(handle.turn_id)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    @router.post(
        "/{conversation_id}/turns/{turn_id}/cancel",
        response_model=TurnCancelResponse,
    )
    def cancel_turn(conversation_id: str, turn_id: str) -> TurnCancelResponse:
        try:
            store.get(conversation_id)
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc
        handle = runtime.turn_registry.get(turn_id)
        if handle is None:
            return TurnCancelResponse(
                turn_id=turn_id,
                cancelled=False,
                message="Turn not found or already finished",
            )
        if handle.conversation_id != conversation_id:
            raise HTTPException(status_code=404, detail="Turn not in this conversation")
        handle.request_cancel()
        return TurnCancelResponse(
            turn_id=turn_id,
            cancelled=True,
            message="Cancel requested",
        )

    @router.get("/{conversation_id}/tasks", response_model=ConversationTasksResponse)
    def list_related_tasks(conversation_id: str) -> ConversationTasksResponse:
        try:
            ids = store.related_task_ids(conversation_id)
            return ConversationTasksResponse(
                conversation_id=conversation_id,
                related_task_ids=ids,
            )
        except Exception as exc:  # noqa: BLE001
            raise _http_from_store(exc) from exc

    return router
