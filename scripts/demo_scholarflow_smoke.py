#!/usr/bin/env python3
"""Phase-7 demo smoke against a RUNNING ScholarFlow API (fixture mode).

Does not start ScholarFlow Docker. Does not claim live MCP success.
Writes JSON report under evaluation/reports/phase7-demo-smoke.json
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8100"
OUT = ROOT / "evaluation" / "reports" / "phase7-demo-smoke.json"


def _req(method: str, path: str, body: dict | None = None, timeout: float = 60.0) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


def wait_task(task_id: str, timeout: float = 90.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, st = _req("GET", f"/api/v1/tasks/{task_id}")
        if code != 200:
            return {"ok": False, "error": f"status http={code}", "body": st}
        if st.get("status") in {"succeeded", "partial_succeeded", "failed", "timed_out"}:
            _, result = _req("GET", f"/api/v1/tasks/{task_id}/result")
            return {"ok": True, "result": result}
        time.sleep(0.25)
    return {"ok": False, "error": "timeout", "task_id": task_id}


def run_case(name: str, body: dict, *, expect_status: set[str] | None = None) -> dict:
    started = time.perf_counter()
    code, created = _req("POST", "/api/v1/tasks", body)
    if code != 200:
        return {
            "name": name,
            "ok": False,
            "error": f"create http={code}",
            "body": created,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    tid = created["task_id"]
    waited = wait_task(tid)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not waited.get("ok"):
        return {"name": name, "ok": False, "task_id": tid, "error": waited.get("error"), "duration_ms": duration_ms}
    result = waited["result"]
    status = result.get("status")
    expect = expect_status or {"succeeded", "partial_succeeded"}
    ok = status in expect
    entry: dict[str, Any] = {
        "name": name,
        "ok": ok,
        "task_id": tid,
        "status": status,
        "kind": body.get("kind"),
        "data_mode": body.get("data_mode", "fixture"),
        "duration_ms": duration_ms,
        "runtime": result.get("runtime"),
    }
    if result.get("research"):
        research = result["research"]
        entry["artifact_count"] = (research.get("artifact_summary") or {}).get("artifact_count")
        entry["papers"] = len(research.get("papers") or [])
        entry["repos"] = len(research.get("repositories") or [])
        entry["review_decision"] = research.get("review_decision")
    if result.get("result"):
        rag = result["result"]
        entry["need_mcp_fallback"] = rag.get("need_mcp_fallback")
        entry["evidence_n"] = len(rag.get("evidence") or [])
        entry["answer_snip"] = (rag.get("answer") or "")[:120]
    if not ok:
        entry["error"] = result.get("error")
    # artifact list/download when succeeded research
    if ok and body.get("persist_artifacts", True) and body.get("kind") != "rag_query":
        ac, listed = _req("GET", f"/api/v1/tasks/{tid}/artifacts")
        entry["artifacts_list_http"] = ac
        if ac == 200:
            files = listed.get("files") or listed.get("artifacts") or []
            entry["artifact_files"] = len(files) if isinstance(files, list) else listed
            dc, _ = _req("GET", f"/api/v1/tasks/{tid}/artifacts/research_plan.json")
            entry["download_plan_http"] = dc
    return entry


def sandbox_case() -> dict:
    code, body = _req(
        "POST",
        "/api/v1/sandbox/execute",
        {
            "task_id": "phase7-demo-sb",
            "code": "print(2+2)\n",
            "prefer_docker": False,
            "timeout_seconds": 5,
        },
    )
    ok = code == 200 and body.get("status") == "succeeded" and "4" in (body.get("stdout") or "")
    return {
        "name": "sandbox_process_jail",
        "ok": ok,
        "http": code,
        "status": body.get("status"),
        "backend": body.get("backend"),
        "stdout": body.get("stdout"),
        "note": "process_jail demo only — not production isolation",
    }


def main() -> int:
    code, health = _req("GET", "/health", timeout=5.0)
    if code != 200:
        print(json.dumps({"error": "API not healthy", "code": code, "body": health}, indent=2))
        return 2

    cases = [
        run_case(
            "paper_research",
            {
                "kind": "paper_research",
                "question": "Blended RAG hybrid dense sparse vs Naive RAG",
                "data_mode": "fixture",
                "persist_artifacts": True,
            },
        ),
        run_case(
            "repository_analysis",
            {
                "kind": "repository_analysis",
                "question": "Open-source RAG repositories for Blended RAG",
                "data_mode": "fixture",
                "persist_artifacts": True,
            },
        ),
        run_case(
            "research_orchestration",
            {
                "kind": "research_orchestration",
                "question": "Blended RAG hybrid dense sparse vs Naive RAG",
                "data_mode": "fixture",
                "persist_artifacts": True,
            },
        ),
        run_case(
            "rag_query_ok",
            {
                "kind": "rag_query",
                "question": "Blended RAG hybrid dense sparse vs Naive RAG",
                "ensure_index": True,
                "data_mode": "fixture",
            },
        ),
        run_case(
            "rag_insufficient_refuse_signal",
            {
                "kind": "rag_query",
                "question": "zzzxqyx nonexistent quantum banana ontology 99999",
                "ensure_index": True,
                "enable_mcp_fallback": True,
                "data_mode": "fixture",
            },
            expect_status={"succeeded"},  # task completes; need_mcp_fallback expected
        ),
        run_case(
            "force_fail_review",
            {
                "kind": "research_orchestration",
                "question": "force fail review demo",
                "data_mode": "fixture",
                "force_fail_review": True,
                "persist_artifacts": True,
            },
            expect_status={"failed"},
        ),
        sandbox_case(),
    ]

    # Mark refuse-signal case ok only if need_mcp_fallback
    for c in cases:
        if c.get("name") == "rag_insufficient_refuse_signal" and c.get("ok"):
            c["ok"] = bool(c.get("need_mcp_fallback"))
            if not c["ok"]:
                c["error"] = "expected need_mcp_fallback=true under fixture"

    # MCP tools (may be slow / 503)
    mcp_code, mcp_body = _req("GET", "/api/v1/mcp/tools", timeout=60.0)
    mcp_case = {
        "name": "mcp_tools",
        "ok": mcp_code == 200 and bool((mcp_body or {}).get("tools")),
        "http": mcp_code,
        "tool_count": len((mcp_body or {}).get("tools") or []),
        "note": "fixture demo stack; live MCP outages are allowed to fail this check",
    }
    cases.append(mcp_case)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "api": API,
        "data_mode": "fixture",
        "health": health,
        "cases": cases,
        "passed": sum(1 for c in cases if c.get("ok")),
        "total": len(cases),
        "disclaimer": (
            "fixture-mode smoke for Phase-7 demo; NOT live integration; "
            "sandbox process_jail is NOT production isolation"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "total": report["total"], "report": str(OUT)}, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
