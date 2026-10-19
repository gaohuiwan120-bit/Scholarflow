"""ScholarFlow FastAPI application (Phase 1 RAG + Phase 2 LangGraph)."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from scholarflow_api import __version__
from scholarflow_api.config import ensure_harness_on_path, get_settings
from scholarflow_api.models import (
    HealthResponse,
    SandboxExecuteRequest,
    SandboxExecuteResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskKind,
    TaskResultResponse,
    TaskStatus,
    TaskStatusResponse,
)
from scholarflow_api.chat.agent import ChatAgentRuntime
from scholarflow_api.chat.router import create_conversation_router
from scholarflow_api.chat.store import ConversationStore
from scholarflow_api.chat.workflow_bridge import configure_workflow_bridge
from scholarflow_api.runtime.base import TaskRuntime
from scholarflow_api.runtime.rag_runtime import RagTaskRuntime
from scholarflow_api.runtime.research_runtime import ResearchTaskRuntime
from scholarflow_api.services.task_runner import execute_stored_task
from scholarflow_api.services.task_store import TaskStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("scholarflow_api")

settings = get_settings()
store = TaskStore()
conversation_store = ConversationStore()
_rag_runtime = RagTaskRuntime(settings)
_research_runtime = ResearchTaskRuntime(settings)
# Chat tools share the same TaskStore + ResearchTaskRuntime as the task API
configure_workflow_bridge(store, _research_runtime, settings)
chat_agent = ChatAgentRuntime(conversation_store)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sf-task")

_RESEARCH_KINDS = {
    TaskKind.research_orchestration,
    TaskKind.paper_research,
    TaskKind.repository_analysis,
    TaskKind.experiment_design,
}


def _select_runtime(kind: TaskKind) -> TaskRuntime:
    if kind == TaskKind.rag_query:
        return _rag_runtime
    if kind in _RESEARCH_KINDS:
        return _research_runtime
    raise HTTPException(status_code=400, detail=f"Unsupported task kind: {kind}")


def _langgraph_ok() -> bool:
    try:
        from langgraph.graph import StateGraph  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _harness_ok() -> bool:
    try:
        ensure_harness_on_path()
        import scholarflow.scholar.rag  # noqa: F401

        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("harness import failed: %s", exc)
        return False


def _sandbox_flags() -> tuple[bool, bool]:
    try:
        ensure_harness_on_path()
        from scholarflow.scholar.sandbox.backends import docker_available
        from scholarflow.scholar.sandbox.runner import execute_sandbox  # noqa: F401

        return True, docker_available()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sandbox import failed: %s", exc)
        return False, False


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "ScholarFlow API — Phase 1 RAG + Phase 2 LangGraph + Phase 3 MCP/artifacts. "
        "Does not claim Cross-Encoder, 50-QA metrics, or Sandbox productization."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 8.1–8.2 — conversation REST + agent turns (SSE deferred to 8.3)
app.include_router(create_conversation_router(conversation_store, chat_agent))


def _llm_health() -> tuple[bool, str | None, str | None]:
    """Return (configured, model_id, provider) — never include API key."""
    try:
        from scholarflow_api.llm.settings import get_llm_settings

        cfg = get_llm_settings()
        if cfg.configured:
            return True, cfg.model, "deepseek"
        return False, cfg.model, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("llm settings read failed: %s", exc)
        return False, None, None


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    sb_ok, sb_docker = _sandbox_flags()
    llm_ok, llm_model, llm_provider = _llm_health()
    return HealthResponse(
        version=__version__,
        runtime="multi",
        runtimes=[_rag_runtime.name, _research_runtime.name],
        harness_importable=_harness_ok(),
        artifacts_dir_exists=settings.default_artifacts_dir.is_dir(),
        langgraph_available=_langgraph_ok(),
        sandbox_available=sb_ok,
        sandbox_docker=sb_docker,
        llm_configured=llm_ok,
        llm_model=llm_model,
        llm_provider=llm_provider,
    )


@app.post("/api/v1/tasks", response_model=TaskCreateResponse)
def create_task(body: TaskCreateRequest) -> TaskCreateResponse:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    runtime = _select_runtime(body.kind)
    record = store.create(
        kind=body.kind,
        question=body.question.strip(),
        runtime=runtime.name,
        params=body.model_dump(),
    )
    threading.Thread(
        target=_execute_task,
        args=(record.task_id,),
        name=f"sf-{record.task_id}",
        daemon=True,
    ).start()
    return TaskCreateResponse(
        task_id=record.task_id,
        status=record.status,
        kind=record.kind,
        created_at=record.created_at,
        message="Task queued; poll /api/v1/tasks/{id} for status",
    )


@app.get("/api/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskStatusResponse(
        task_id=record.task_id,
        status=record.status,
        kind=record.kind,
        question=record.question,
        created_at=record.created_at,
        updated_at=record.updated_at,
        runtime=record.runtime,
        error=record.error,
        progress=record.progress,
        subtasks=record.subtasks,
    )


@app.get("/api/v1/tasks/{task_id}/result", response_model=TaskResultResponse)
def get_task_result(task_id: str) -> TaskResultResponse:
    record = store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="task not found")
    return TaskResultResponse(
        task_id=record.task_id,
        status=record.status,
        kind=record.kind,
        question=record.question,
        runtime=record.runtime,
        result=record.result,
        research=record.research,
        artifacts=record.artifacts,
        index_info=record.index_info,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        duration_ms=record.duration_ms,
        subtasks=record.subtasks,
    )


@app.get("/api/v1/tasks/{task_id}/artifacts")
def list_task_artifacts(task_id: str) -> dict:
    from scholarflow_api.services.artifact_store import list_artifacts

    man = list_artifacts(task_id)
    if man is None:
        record = store.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task or artifacts not found")
        if record.research and record.research.artifact_manifest:
            return record.research.artifact_manifest
        raise HTTPException(status_code=404, detail="artifacts not found")
    return man.model_dump()


@app.get("/api/v1/tasks/{task_id}/artifacts/{filename}")
def download_task_artifact(task_id: str, filename: str) -> Response:
    from scholarflow_api.services.artifact_store import read_artifact_bytes

    try:
        data, media = read_artifact_bytes(task_id, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/v1/sandbox/execute", response_model=SandboxExecuteResponse)
def sandbox_execute(body: SandboxExecuteRequest) -> SandboxExecuteResponse:
    """Run a short Python snippet under ScholarFlow sandbox policy.

    Prefer Docker when the daemon is up; otherwise process_jail.
    Process jail is NOT claimed as production-grade isolation.
    """
    ensure_harness_on_path()
    from scholarflow.scholar.sandbox import SandboxRequest, execute_sandbox

    try:
        result = execute_sandbox(
            SandboxRequest(
                task_id=body.task_id,
                code=body.code,
                timeout_seconds=body.timeout_seconds,
                memory_mb=body.memory_mb,
                max_output_bytes=body.max_output_bytes,
                allow_network=body.allow_network,
                prefer_docker=body.prefer_docker,
                filename=body.filename,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SandboxExecuteResponse.model_validate(result.model_dump())


@app.get("/api/v1/mcp/tools")
def mcp_tools() -> dict:
    """List tools exposed by scholar_mcp via real MCP protocol (stdio)."""
    try:
        from scholarflow_api.mcp.client import list_mcp_tools

        tools = list_mcp_tools(timeout_seconds=45.0)
        return {"ok": True, "tools": tools, "transport": "stdio"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"MCP unavailable: {exc}") from exc


def _execute_task(task_id: str) -> None:
    record = store.get(task_id)
    if record is None:
        return
    runtime = _select_runtime(record.kind)
    execute_stored_task(
        store=store,
        runtime=runtime,
        settings=settings,
        task_id=task_id,
        executor=_executor,
    )
