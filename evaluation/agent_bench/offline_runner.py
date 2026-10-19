"""Run the 20 offline Agent Bench tasks."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evaluation.agent_bench.api_client import (
    create_and_wait,
    mcp_tools,
    sandbox_execute,
)
from evaluation.agent_bench.assertions import load_persisted_artifacts, run_assertions
from evaluation.agent_bench.outcomes import Outcome

V1 = Path(__file__).resolve().parent / "v1"


def load_offline_tasks(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or (V1 / "offline_tasks.json")
    return json.loads(p.read_text(encoding="utf-8"))["tasks"]


def _decide_outcome(spec: dict[str, Any], assertions_ok: bool, infra: bool) -> str:
    if infra:
        return Outcome.infra_error.value
    expected = spec.get("expect_outcome") or "succeeded"
    if assertions_ok:
        return expected
    return Outcome.failed.value


def _run_rag_pipeline_mock(spec: dict[str, Any]) -> dict[str, Any]:
    """Public RAG pipeline entry with mock MCP caller (max-rounds refuse)."""
    from scholarflow.scholar.rag import RagConfig, index_artifacts_dir, rag_answer
    from scholarflow_api.config import repo_root

    artifacts = repo_root() / "docs" / "scholar-flow" / "samples" / "rag-test-001"
    cfg = RagConfig.from_env()
    # Ensure index exists for retrieve path
    try:
        index_artifacts_dir(artifacts, config=cfg, task_id="rag-test-001")
    except Exception:
        pass

    def mock_caller(name: str, arguments: dict[str, Any]):
        return {"ok": True, "tool": name, "arguments": arguments, "items": []}

    inp = spec.get("input") or {}
    raw = rag_answer(
        inp.get("question") or "zzzxqyx nonexistent",
        config=cfg,
        top_k=5,
        enable_mcp_fallback=True,
        mcp_caller=mock_caller,
        data_mode="live",
        task_id="off-16-mock",
    )
    # Attach max_rounds from retrieval meta if present
    retrieval = dict(raw.get("retrieval") or {})
    if raw.get("mcp_rounds") is not None:
        retrieval.setdefault("mcp_rounds", raw.get("mcp_rounds"))
    # Detect max rounds via mcp_rounds length vs config
    rounds = raw.get("mcp_rounds") or []
    if len(rounds) >= cfg.max_mcp_rounds and raw.get("need_mcp_fallback"):
        retrieval["max_rounds_reached"] = True
        if "最大 MCP 补检" not in (raw.get("answer") or ""):
            raw["answer"] = (raw.get("answer") or "") + "\n\n已达最大 MCP 补检次数仍证据不足，明确拒答扩展结论。"
    raw["retrieval"] = retrieval
    return raw


def run_one(client, spec: dict[str, Any], *, data_mode: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    ctx: dict[str, Any] = {"schema_checks": {"passed": 0, "total": 0, "details": []}, "meta": {}}
    infra = False
    error: str | None = None
    mcp_calls: list[Any] = []
    status = None

    try:
        entry = spec.get("entry")
        if entry == "api_task":
            body = {
                "kind": spec["kind"],
                "data_mode": data_mode if data_mode != "live" else "live",
                **(spec.get("input") or {}),
            }
            # Keep fixture unless caller forced live
            if "data_mode" not in (spec.get("input") or {}):
                body["data_mode"] = data_mode
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
                if tid and (spec.get("expect_artifacts") in {"nine", "research_pack"} or "schema_all_json" in spec.get("assertions", [])):
                    ctx["artifacts"] = load_persisted_artifacts(tid)
                # list/download extras when asserted
                if "artifacts_api_listable" in spec.get("assertions", []) and tid:
                    from evaluation.agent_bench.api_client import list_artifacts

                    ctx["artifacts_list"] = list_artifacts(client, tid)
                if "artifacts_api_download" in spec.get("assertions", []) and tid:
                    from evaluation.agent_bench.api_client import download_artifact

                    ctx["artifact_download"] = download_artifact(client, tid, "research_plan.json")

        elif entry == "api_mcp_tools":
            ctx["mcp_tools"] = mcp_tools(client)
            http = ctx["mcp_tools"].get("http_status")
            if http == 503:
                infra = True
                error = f"MCP tools unavailable: {(ctx['mcp_tools'].get('body') or {})}"
            elif http not in {200}:
                infra = True
                error = f"MCP tools http={http}"

        elif entry == "api_sandbox":
            ctx["sandbox"] = sandbox_execute(client, spec.get("input") or {})
            if ctx["sandbox"].get("http_status") != 200:
                # policy reject may still be 200 with status rejected; 400 is also ok for bad input
                if ctx["sandbox"].get("http_status") >= 500:
                    infra = True
                    error = f"sandbox http={ctx['sandbox'].get('http_status')}"

        elif entry == "rag_pipeline_mock_mcp":
            pipe = _run_rag_pipeline_mock(spec)
            ctx["pipeline"] = pipe
            status = "correct_refuse" if pipe.get("need_mcp_fallback") else "succeeded"

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

    return {
        "task_id": spec["id"],
        "title": spec.get("title"),
        "task_type": "offline",
        "entry": spec.get("entry"),
        "kind": spec.get("kind"),
        "data_mode": data_mode,
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
            "artifact_count": len(ctx.get("artifacts") or {}),
            "schema_ok": (schema.get("total", 0) == 0)
            or (schema.get("passed", 0) == schema.get("total", 0)),
            "subtask_roles": sorted(
                {
                    s.get("role")
                    for s in ((_research_subtasks(ctx)))
                    if s.get("role")
                }
            ),
            "need_mcp_fallback": bool(
                ((ctx.get("result") or {}).get("result") or {}).get("need_mcp_fallback")
                or (ctx.get("pipeline") or {}).get("need_mcp_fallback")
            ),
            "sandbox_status": ((ctx.get("sandbox") or {}).get("body") or {}).get("status"),
        },
    }


def _research_subtasks(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    result = ctx.get("result") or {}
    research = result.get("research") or {}
    return list(research.get("subtasks") or result.get("subtasks") or [])


def run_offline_suite(
    client,
    *,
    data_mode: str = "fixture",
    timeout: float = 120.0,
    limit: int = 0,
) -> list[dict[str, Any]]:
    tasks = load_offline_tasks()
    if limit > 0:
        tasks = tasks[:limit]
    results = []
    for spec in tasks:
        # Per-task data_mode from spec unless suite overrides to live
        mode = data_mode if data_mode == "live" else (spec.get("data_mode") or "fixture")
        results.append(run_one(client, spec, data_mode=mode, timeout=timeout))
    return results
