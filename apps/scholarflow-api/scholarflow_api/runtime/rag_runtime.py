"""Phase-1 runtime: wrap existing ScholarFlow hybrid RAG (no CLI subprocess)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from scholarflow_api.config import Settings, ensure_harness_on_path
from scholarflow_api.models import ArtifactRef, EvidenceItem, RagResultPayload
from scholarflow_api.runtime.base import ProgressCallback, RuntimeRequest, RuntimeResult, TaskRuntime

logger = logging.getLogger("scholarflow_api.runtime.rag")


class RagTaskRuntime(TaskRuntime):
    """Calls ``index_artifacts_dir`` / ``rag_answer`` from scholarflow.scholar.rag.

    Does not shell out to ``run_rag_demo.py`` (avoids wiping index every request
    and keeps structured dict results for the API).
    """

    name = "rag_v1"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(
        self,
        request: RuntimeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RuntimeResult:
        ensure_harness_on_path()
        from scholarflow.scholar.rag import RagConfig, index_artifacts_dir, rag_answer

        def progress(msg: str) -> None:
            logger.info("[%s] %s", request.task_id, msg)
            if on_progress:
                on_progress(msg)

        artifacts_dir = Path(
            request.artifacts_dir or self._settings.default_artifacts_dir
        )
        if not artifacts_dir.is_dir():
            raise FileNotFoundError(f"artifacts directory not found: {artifacts_dir}")

        import os

        if request.rerank_model:
            os.environ["SCHOLAR_RAG_RERANK_MODEL"] = request.rerank_model
        cfg = RagConfig.from_env()
        index_info: dict[str, Any] | None = None

        need_index = request.force_reindex or request.ensure_index
        corpus = cfg.persist_dir / "corpus.json"
        if request.ensure_index and not request.force_reindex and corpus.is_file():
            need_index = False
            progress("Using existing RAG index")

        if need_index:
            if request.force_reindex and cfg.persist_dir.exists():
                progress("Force reindex: clearing persist_dir")
                shutil.rmtree(cfg.persist_dir, ignore_errors=True)
            progress(f"Indexing artifacts from {artifacts_dir}")
            index_info = index_artifacts_dir(
                artifacts_dir,
                config=cfg,
                task_id=self._settings.default_task_id_for_index,
            )
            progress(f"Indexed upserted={index_info.get('upserted')}")

        mcp_caller = None
        enable_fb = bool(request.enable_mcp_fallback)
        data_mode = request.data_mode or "fixture"
        if enable_fb and data_mode == "live":
            from scholarflow_api.mcp.client import call_mcp_tool

            def mcp_caller(name: str, arguments: dict[str, Any]):
                progress(f"MCP supplement tool={name}")
                return call_mcp_tool(name, arguments, timeout_seconds=90.0)

        progress(
            f"Running hybrid RAG query rerank={cfg.rerank_model} "
            f"mcp_fallback={enable_fb} data_mode={data_mode}"
        )
        raw = rag_answer(
            request.question,
            config=cfg,
            top_k=request.top_k,
            verified_only=request.verified_only,
            enable_mcp_fallback=enable_fb,
            mcp_caller=mcp_caller,
            data_mode=data_mode,
            task_id=request.task_id,
        )
        progress("RAG query finished")

        evidence = [EvidenceItem.model_validate(e) for e in raw.get("evidence") or []]
        retrieval = dict(raw.get("retrieval") or {})
        retrieval["citation_report"] = raw.get("citation_report")
        retrieval["mcp_rounds"] = raw.get("mcp_rounds") or []
        payload = RagResultPayload(
            question=raw.get("question") or request.question,
            answer=raw.get("answer") or "",
            confidence=str(raw.get("confidence") or "low"),
            evidence=evidence,
            need_mcp_fallback=bool(raw.get("need_mcp_fallback")),
            retrieval=retrieval,
        )
        artifacts = [
            ArtifactRef(
                label="sample_artifacts",
                path=str(artifacts_dir.resolve()),
                kind="artifacts_dir",
            ),
            ArtifactRef(
                label="rag_index",
                path=str(cfg.persist_dir.resolve()),
                kind="rag_index",
            ),
        ]
        return RuntimeResult(
            payload=payload,
            artifacts=artifacts,
            index_info=index_info,
            raw=raw,
            overall_status="succeeded",
        )
