"""Run the 10 E2E Agent Bench tasks via FastAPI TestClient."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evaluation.agent_bench.api_client import (
    create_and_wait,
    download_artifact,
    list_artifacts,
    sandbox_execute,
)
from evaluation.agent_bench.assertions import load_persisted_artifacts, run_assertions
from evaluation.agent_bench.outcomes import Outcome

V1 = Path(__file__).resolve().parent / "v1"


def load_e2e_tasks(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or (V1 / "e2e_tasks.json")
    return json.loads(p.read_text(encoding="utf-8"))["tasks"]


def _decide_outcome(spec: dict[str, Any], assertions_ok: bool, infra: bool) -> str:
    if infra:
        return Outcome.infra_error.value
    expected = spec.get("expect_outcome") or "succeeded"
    if assertions_ok:
        return expected
    return Outcome.failed.value


def run_one(client, spec: dict[str, Any], *, data_mode: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    ctx: dict[str, Any] = {"schema_checks": {"passed": 0, "total": 0, "details": []}, "meta": {}}
    infra = False
    error: str | None = None
    mcp_calls: list[Any] = []
    status = None
    entry = spec.get("entry")
    effective_mode = body_data_mode(spec, data_mode)

    try:
        if entry == "api_task":
            body = {"kind": spec["kind"], **(spec.get("input") or {})}
            body["data_mode"] = effective_mode
            result = create_and_wait(client, body, timeout=timeout)
            if not result.get("ok"):
                infra = True
                error = result.get("error")
            else:
                ctx["result"] = result
                status = result.get("status")
                research = result.get("research") or {}
                mcp_calls = research.get("mcp_calls") or []
                tid = result.get("task_id")
                if tid:
                    ctx["artifacts"] = load_persisted_artifacts(tid)
                    if "artifacts_api_listable" in (spec.get("assertions") or []):
                        ctx["artifacts_list"] = list_artifacts(client, tid)
                    if "artifacts_api_download" in (spec.get("assertions") or []):
                        ctx["artifact_download"] = download_artifact(
                            client, tid, "research_plan.json"
                        )

        elif entry == "api_sandbox_pair":
            inp = spec.get("input") or {}
            ctx["sandbox_ok"] = sandbox_execute(client, inp.get("ok") or {})
            ctx["sandbox_reject"] = sandbox_execute(client, inp.get("reject") or {})
            status = "succeeded"

        else:
            infra = True
            error = f"unknown entry={entry}"

        assertions_ok, assertion_results = run_assertions(spec.get("assertions") or [], ctx)
    except Exception as exc:  # noqa: BLE001
        infra = True
        error = str(exc)
        assertions_ok = False
        assertion_results = [{"name": "_runner", "ok": False, "detail": str(exc)}]

    outcome = _decide_outcome(spec, assertions_ok, infra)
    duration_ms = int((time.perf_counter() - started) * 1000)
    schema = ctx.get("schema_checks") or {"passed": 0, "total": 0, "details": []}
    research = ((ctx.get("result") or {}).get("research") or {})
    roles = sorted({s.get("role") for s in (research.get("subtasks") or []) if s.get("role")})

    return {
        "task_id": spec["id"],
        "title": spec.get("title"),
        "task_type": "e2e",
        "entry": spec.get("entry"),
        "kind": spec.get("kind"),
        "data_mode": effective_mode,
        "expect_outcome": spec.get("expect_outcome"),
        "outcome": outcome,
        "status": status,
        "assertions": assertion_results,
        "schema_checks": schema,
        "artifact_checks": {
            "count": len(ctx.get("artifacts") or {}),
            "names": sorted((ctx.get("artifacts") or {}).keys()),
        },
        "traceability": next(
            (a for a in assertion_results if a["name"] == "source_traceability"),
            None,
        ),
        "duration_ms": duration_ms,
        "error": error,
        "mcp_calls": mcp_calls,
        "meta": ctx.get("meta") or {},
        "golden_fields": {
            "outcome": outcome,
            "status": status,
            "artifact_count": ((research.get("artifact_summary") or {}).get("artifact_count")
                               or len(ctx.get("artifacts") or {})),
            "schema_ok": (schema.get("total", 0) == 0)
            or (schema.get("passed", 0) == schema.get("total", 0)),
            "subtask_roles": roles,
            "need_mcp_fallback": bool(
                ((ctx.get("result") or {}).get("result") or {}).get("need_mcp_fallback")
            ),
            "sandbox_ok_status": ((ctx.get("sandbox_ok") or {}).get("body") or {}).get("status"),
            "sandbox_reject_status": ((ctx.get("sandbox_reject") or {}).get("body") or {}).get(
                "status"
            ),
        },
    }


def body_data_mode(spec: dict[str, Any], suite_mode: str) -> str:
    if suite_mode == "live":
        return "live"
    return spec.get("data_mode") or "fixture"


def run_e2e_suite(
    client,
    *,
    data_mode: str = "fixture",
    timeout: float = 120.0,
    limit: int = 0,
) -> list[dict[str, Any]]:
    tasks = load_e2e_tasks()
    if limit > 0:
        tasks = tasks[:limit]
    return [run_one(client, spec, data_mode=data_mode, timeout=timeout) for spec in tasks]
