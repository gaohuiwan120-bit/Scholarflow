"""Phase-2 runtime: LangGraph research orchestration via TaskRuntime interface."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scholarflow_api.config import Settings
from scholarflow_api.graph.state import WorkflowMode
from scholarflow_api.graph.workflow import run_research_workflow
from scholarflow_api.models import (
    ArtifactRef,
    EvidenceItem,
    RagResultPayload,
    ResearchWorkflowPayload,
    SubtaskStatusItem,
)
from scholarflow_api.runtime.base import ProgressCallback, RuntimeRequest, RuntimeResult, TaskRuntime

logger = logging.getLogger("scholarflow_api.runtime.research")

_MODE_MAP: dict[str, WorkflowMode] = {
    "research_orchestration": "research_orchestration",
    "paper_research": "paper_research",
    "repository_analysis": "repository_analysis",
    "experiment_design": "experiment_design",
}


class ResearchTaskRuntime(TaskRuntime):
    name = "research_graph_v1"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(
        self,
        request: RuntimeRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RuntimeResult:
        def progress(msg: str) -> None:
            logger.info("[%s] %s", request.task_id, msg)
            if on_progress:
                on_progress(msg)

        kind = request.kind.value if hasattr(request.kind, "value") else str(request.kind)
        mode = _MODE_MAP.get(kind, "research_orchestration")
        artifacts_dir = Path(request.artifacts_dir or self._settings.default_artifacts_dir)
        if not artifacts_dir.is_dir():
            raise FileNotFoundError(f"artifacts directory not found: {artifacts_dir}")

        progress(f"Starting LangGraph workflow mode={mode}")
        final = run_research_workflow(
            task_id=request.task_id,
            question=request.question,
            workflow_mode=mode,
            artifacts_dir=str(artifacts_dir),
            data_mode=request.data_mode or "fixture",
            allow_fixture_fallback=bool(request.allow_fixture_fallback),
            force_fail_review=bool(request.force_fail_review),
            force_fail_paper=bool(request.force_fail_paper),
            simulate_work_seconds=float(request.simulate_work_seconds or 0.0),
            persist_artifacts=bool(request.persist_artifacts),
        )
        progress(f"Graph finished overall={final.get('overall_status')}")

        subtasks = [
            SubtaskStatusItem.model_validate(
                {
                    "subtask_id": s.get("subtask_id"),
                    "role": s.get("role"),
                    "status": s.get("status"),
                    "depends_on": s.get("depends_on") or [],
                    "started_at": s.get("started_at"),
                    "ended_at": s.get("ended_at"),
                    "duration_ms": s.get("duration_ms"),
                    "error": s.get("error"),
                    "summary": s.get("summary"),
                    "data_source": s.get("data_source"),
                }
            )
            for s in (final.get("subtasks") or [])
            if s.get("subtask_id")
        ]

        papers = final.get("papers") or []
        evidence = [
            EvidenceItem(
                evidence_id=p.get("evidence_id"),
                kind="paper",
                title=p.get("title"),
                text=(p.get("research_problem") or "")[:400],
                source_url=p.get("source_url"),
                verification_status=p.get("verification_status"),
            )
            for p in papers[:5]
        ]
        for r in (final.get("repositories") or [])[:3]:
            evidence.append(
                EvidenceItem(
                    evidence_id=r.get("evidence_id"),
                    kind="repository",
                    title=r.get("repository"),
                    text=(r.get("description") or "")[:400],
                    source_url=r.get("source_url"),
                    verification_status=r.get("verification_status"),
                )
            )

        report = final.get("report_excerpt") or ""
        answer = report or f"Workflow finished with status={final.get('overall_status')}"
        payload = RagResultPayload(
            question=request.question,
            answer=answer,
            confidence="high" if final.get("overall_status") == "succeeded" else "medium",
            evidence=evidence,
            need_mcp_fallback=False,
            retrieval={
                "runtime": self.name,
                "workflow_mode": mode,
                "review_decision": final.get("review_decision"),
                "overall_status": final.get("overall_status"),
            },
        )

        research = ResearchWorkflowPayload(
            workflow_mode=mode,
            overall_status=str(final.get("overall_status") or "failed"),
            review_decision=final.get("review_decision"),
            research_plan=final.get("research_plan"),
            papers=papers,
            repositories=final.get("repositories") or [],
            experiment=final.get("experiment") or {},
            reviews=final.get("reviews") or [],
            subtasks=subtasks,
            events=list(final.get("events") or []),
            mcp_calls=list(final.get("mcp_calls") or []),
            degradation_events=list(final.get("degradation_events") or []),
            artifact_summary=final.get("artifact_summary"),
            artifact_manifest=final.get("artifact_manifest"),
            report_excerpt=final.get("report_excerpt"),
            data_mode=request.data_mode or "fixture",
            effective_data_mode=final.get("effective_data_mode"),
        )

        artifacts: list[ArtifactRef] = []
        man = final.get("artifact_manifest") or {}
        man_items = man.get("artifacts") if isinstance(man, dict) else None
        if isinstance(man_items, list) and man_items:
            for item in man_items:
                if not isinstance(item, dict):
                    continue
                fname = str(item.get("filename") or "")
                artifacts.append(
                    ArtifactRef(
                        label=fname or str(item.get("artifact_id") or "artifact"),
                        path=str(item.get("path") or f"/api/v1/tasks/{request.task_id}/artifacts/{fname}"),
                        kind="file",
                    )
                )
        else:
            artifacts.append(
                ArtifactRef(
                    label="sample_artifacts",
                    path=str(artifacts_dir.resolve()),
                    kind="artifacts_dir",
                )
            )
            for name in (final.get("artifact_summary") or {}).get("artifacts") or []:
                artifacts.append(
                    ArtifactRef(
                        label=name,
                        path=f"/api/v1/tasks/{request.task_id}/artifacts/{name}",
                        kind="file",
                    )
                )

        raw: dict[str, Any] = {
            "overall_status": final.get("overall_status"),
            "review_decision": final.get("review_decision"),
            "artifact_summary": final.get("artifact_summary"),
            "error": final.get("error"),
        }
        overall = str(final.get("overall_status") or "failed")
        return RuntimeResult(
            payload=payload,
            research=research,
            artifacts=artifacts,
            index_info=None,
            raw=raw,
            overall_status=overall,
        )
