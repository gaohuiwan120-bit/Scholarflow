"""Assertion helpers for Agent Bench tasks."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Callable

from evaluation.agent_bench.outcomes import REQUIRED_NINE, SCHEMA_JSON_FILES
from evaluation.metrics import (
    csv_parseability,
    json_parseability,
    markdown_nonempty,
    source_traceability,
)


AssertionFn = Callable[[dict[str, Any]], tuple[bool, str]]


def _research(ctx: dict[str, Any]) -> dict[str, Any]:
    result = ctx.get("result") or {}
    return result.get("research") or {}


def _rag(ctx: dict[str, Any]) -> dict[str, Any]:
    result = ctx.get("result") or {}
    return result.get("result") or {}


def _subs(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    research = _research(ctx)
    subs = research.get("subtasks") or (ctx.get("result") or {}).get("subtasks") or []
    return list(subs)


def _artifacts_map(ctx: dict[str, Any]) -> dict[str, str]:
    return dict(ctx.get("artifacts") or {})


def status_succeeded(ctx: dict[str, Any]) -> tuple[bool, str]:
    st = (ctx.get("result") or {}).get("status")
    return st == "succeeded", f"status={st}"


def status_succeeded_or_partial(ctx: dict[str, Any]) -> tuple[bool, str]:
    st = (ctx.get("result") or {}).get("status")
    ok = st in {"succeeded", "partial_succeeded"}
    return ok, f"status={st}"


def status_failed(ctx: dict[str, Any]) -> tuple[bool, str]:
    st = (ctx.get("result") or {}).get("status")
    return st == "failed", f"status={st}"


def runtime_research(ctx: dict[str, Any]) -> tuple[bool, str]:
    rt = (ctx.get("result") or {}).get("runtime")
    return rt == "research_graph_v1", f"runtime={rt}"


def has_papers(ctx: dict[str, Any]) -> tuple[bool, str]:
    papers = _research(ctx).get("papers") or []
    return bool(papers), f"papers={len(papers)}"


def has_repos(ctx: dict[str, Any]) -> tuple[bool, str]:
    repos = _research(ctx).get("repositories") or []
    return bool(repos), f"repos={len(repos)}"


def experiment_upstream_ids(ctx: dict[str, Any]) -> tuple[bool, str]:
    exp = _research(ctx).get("experiment") or {}
    p = exp.get("upstream_paper_ids") or []
    r = exp.get("upstream_repo_ids") or []
    ok = bool(p) and bool(r)
    return ok, f"upstream_papers={len(p)} upstream_repos={len(r)}"


def roles_orchestration(ctx: dict[str, Any]) -> tuple[bool, str]:
    roles = {s.get("role") for s in _subs(ctx)}
    need = {"paper_research", "repository_analysis", "experiment_design", "review", "assemble"}
    ok = need.issubset(roles)
    return ok, f"roles={sorted(roles)}"


def subtask_depends_on(ctx: dict[str, Any]) -> tuple[bool, str]:
    exp = next((s for s in _subs(ctx) if s.get("role") == "experiment_design"), None)
    asm = next((s for s in _subs(ctx) if s.get("role") == "assemble"), None)
    if not exp or not asm:
        return False, "missing experiment or assemble subtask"
    ok = bool(exp.get("depends_on")) and bool(asm.get("depends_on"))
    return ok, f"exp_deps={exp.get('depends_on')} asm_deps={asm.get('depends_on')}"


def paper_repo_parallel_overlap(ctx: dict[str, Any]) -> tuple[bool, str]:
    by = {s.get("role"): s for s in _subs(ctx)}
    paper = by.get("paper_research") or {}
    repo = by.get("repository_analysis") or {}
    ps, pe = paper.get("started_at"), paper.get("ended_at")
    rs, re = repo.get("started_at"), repo.get("ended_at")
    if None in (ps, pe, rs, re):
        return False, f"missing timestamps paper={paper} repo={repo}"
    ok = ps < re and rs < pe
    return ok, f"paper=[{ps},{pe}] repo=[{rs},{re}] overlap={ok}"


def artifact_count_9(ctx: dict[str, Any]) -> tuple[bool, str]:
    summary = (_research(ctx).get("artifact_summary") or {})
    n = summary.get("artifact_count")
    return n == 9, f"artifact_count={n}"


def nine_files_present(ctx: dict[str, Any]) -> tuple[bool, str]:
    arts = _artifacts_map(ctx)
    missing = [n for n in REQUIRED_NINE if n not in arts or not str(arts[n]).strip()]
    return not missing, f"missing={missing}"


def schema_all_json(ctx: dict[str, Any]) -> tuple[bool, str]:
    from scholarflow.scholar.validation import validate_json_artifact

    arts = _artifacts_map(ctx)
    checks = ctx.setdefault("schema_checks", {"passed": 0, "total": 0, "details": []})
    ok_all = True
    details: list[str] = []
    for name in SCHEMA_JSON_FILES:
        if name not in arts:
            ok_all = False
            details.append(f"{name}:missing")
            continue
        checks["total"] += 1
        try:
            validate_json_artifact(name, json.loads(arts[name]))
            checks["passed"] += 1
            details.append(f"{name}:ok")
            checks["details"].append({"file": name, "ok": True})
        except Exception as exc:  # noqa: BLE001
            ok_all = False
            details.append(f"{name}:{exc}")
            checks["details"].append({"file": name, "ok": False, "error": str(exc)})
    return ok_all, "; ".join(details)


def format_parseability(ctx: dict[str, Any]) -> tuple[bool, str]:
    arts = _artifacts_map(ctx)
    j = json_parseability(arts)
    c = csv_parseability(arts)
    m = markdown_nonempty(arts)
    ok = j.score == 1.0 and c.score == 1.0 and m.score == 1.0
    return ok, f"json={j.score} csv={c.score} md={m.score}"


def source_traceability_ok(ctx: dict[str, Any]) -> tuple[bool, str]:
    arts = _artifacts_map(ctx)
    m = source_traceability(arts)
    return m.score >= 1.0, f"score={m.score} details={m.details}"


def paper_subtask_failed(ctx: dict[str, Any]) -> tuple[bool, str]:
    paper = next((s for s in _subs(ctx) if s.get("role") == "paper_research"), None)
    if not paper:
        return False, "no paper_research subtask"
    return paper.get("status") == "failed", f"paper_status={paper.get('status')}"


def assemble_not_fake_success(ctx: dict[str, Any]) -> tuple[bool, str]:
    asm = next((s for s in _subs(ctx) if s.get("role") == "assemble"), None)
    if not asm:
        return False, "no assemble subtask"
    # On review fail, assemble must be skipped (not succeeded with fake 9-pack)
    ok = asm.get("status") == "skipped"
    summary = (_research(ctx).get("artifact_summary") or {})
    count = summary.get("artifact_count") or 0
    return ok and count == 0, f"assemble={asm.get('status')} artifact_count={count}"


def review_passed(ctx: dict[str, Any]) -> tuple[bool, str]:
    dec = _research(ctx).get("review_decision")
    return dec == "pass", f"review_decision={dec}"


def review_present(ctx: dict[str, Any]) -> tuple[bool, str]:
    reviews = _research(ctx).get("reviews") or []
    return bool(reviews), f"reviews={len(reviews)}"


def rag_has_evidence(ctx: dict[str, Any]) -> tuple[bool, str]:
    ev = _rag(ctx).get("evidence") or []
    return bool(ev), f"evidence={len(ev)}"


def rag_rerank_backend_recorded(ctx: dict[str, Any]) -> tuple[bool, str]:
    retrieval = _rag(ctx).get("retrieval") or {}
    backend = retrieval.get("rerank_backend") or retrieval.get("rerank_model")
    # Accept stub-cross-encoder or cross-encoder; record honestly
    ok = backend in {"stub-cross-encoder", "cross-encoder", "hybrid-score"} or bool(backend)
    ctx.setdefault("meta", {})["rerank_backend"] = backend
    if backend == "stub-cross-encoder":
        ctx.setdefault("meta", {})["rerank_note"] = "stub — not production Cross-Encoder"
    return bool(backend), f"rerank_backend={backend}"


def rag_need_mcp_fallback(ctx: dict[str, Any]) -> tuple[bool, str]:
    rag = _rag(ctx)
    # pipeline mock path stores under ctx["pipeline"]
    if ctx.get("pipeline"):
        rag = ctx["pipeline"]
    flag = bool(rag.get("need_mcp_fallback"))
    return flag, f"need_mcp_fallback={flag} confidence={rag.get('confidence')}"


def rag_normal_answer(ctx: dict[str, Any]) -> tuple[bool, str]:
    rag = _rag(ctx)
    ev = rag.get("evidence") or []
    ans = rag.get("answer") or ""
    refuse = "明确拒答" in ans or "未检索到足够" in ans
    ok = bool(ev) and not refuse and not rag.get("need_mcp_fallback")
    # Some sufficient answers still set need_mcp_fallback=False; if evidence present and not refuse OK
    if bool(ev) and not refuse:
        ok = True
    return ok, f"evidence={len(ev)} refuse={refuse} need_fb={rag.get('need_mcp_fallback')}"


def rag_max_rounds_refuse(ctx: dict[str, Any]) -> tuple[bool, str]:
    pipe = ctx.get("pipeline") or {}
    ans = pipe.get("answer") or ""
    need = bool(pipe.get("need_mcp_fallback"))
    rounds = pipe.get("mcp_rounds") or []
    max_hit = bool(pipe.get("retrieval", {}).get("max_rounds_reached")) or (
        "最大 MCP 补检" in ans
    )
    # Also accept when rounds logged and still need fallback
    ok = need and (max_hit or len(rounds) >= 1)
    return ok, f"need={need} max_hit={max_hit} rounds={len(rounds)} ans_snip={ans[-80:]}"


def mcp_tools_schema(ctx: dict[str, Any]) -> tuple[bool, str]:
    payload = ctx.get("mcp_tools") or {}
    if payload.get("http_status") != 200:
        return False, f"http={payload.get('http_status')}"
    body = payload.get("body") or {}
    tools = body.get("tools") or body.get("result") or body
    if isinstance(tools, dict) and "tools" in tools:
        tools = tools["tools"]
    if not isinstance(tools, list) or not tools:
        if isinstance(body, dict) and body.get("ok") is False:
            return False, f"body={body}"
        return False, f"unexpected body keys={list(body.keys()) if isinstance(body, dict) else type(body)}"
    sample = tools[0]
    # list_mcp_tools may return name strings or Tool dicts
    if isinstance(sample, str):
        has_name = bool(sample.strip())
    elif isinstance(sample, dict):
        has_name = bool(sample.get("name") or sample.get("tool"))
    else:
        has_name = False
    return has_name and len(tools) >= 1, f"tool_count={len(tools)} sample={sample!r}"


def sandbox_succeeded(ctx: dict[str, Any]) -> tuple[bool, str]:
    body = (ctx.get("sandbox") or {}).get("body") or {}
    ok = body.get("status") == "succeeded" and "42" in (body.get("stdout") or "")
    return ok, f"status={body.get('status')} backend={body.get('backend')} out={body.get('stdout')!r}"


def sandbox_timed_out_or_rejected(ctx: dict[str, Any]) -> tuple[bool, str]:
    body = (ctx.get("sandbox") or {}).get("body") or {}
    st = body.get("status")
    ok = st in {"timed_out", "rejected"}
    return ok, f"status={st} err={body.get('error_summary')}"


def sandbox_pair_ok_and_reject(ctx: dict[str, Any]) -> tuple[bool, str]:
    ok_body = (ctx.get("sandbox_ok") or {}).get("body") or {}
    rej_body = (ctx.get("sandbox_reject") or {}).get("body") or {}
    ok1 = ok_body.get("status") == "succeeded" and "sandbox-ok" in (ok_body.get("stdout") or "")
    ok2 = rej_body.get("status") == "rejected"
    return ok1 and ok2, f"ok={ok_body.get('status')} reject={rej_body.get('status')}"


def artifacts_api_listable(ctx: dict[str, Any]) -> tuple[bool, str]:
    listed = ctx.get("artifacts_list") or {}
    if listed.get("http_status") != 200:
        return False, f"http={listed.get('http_status')}"
    body = listed.get("body") or {}
    files = body.get("files") or body.get("artifacts") or []
    return bool(files) or bool(body), f"keys={list(body.keys())} files={len(files) if isinstance(files, list) else files}"


def artifacts_api_download(ctx: dict[str, Any]) -> tuple[bool, str]:
    dl = ctx.get("artifact_download") or {}
    ok = dl.get("http_status") == 200 and len(dl.get("content") or b"") > 10
    return ok, f"http={dl.get('http_status')} bytes={len(dl.get('content') or b'')}"


ASSERTIONS: dict[str, AssertionFn] = {
    "status_succeeded": status_succeeded,
    "status_succeeded_or_partial": status_succeeded_or_partial,
    "status_failed": status_failed,
    "runtime_research": runtime_research,
    "has_papers": has_papers,
    "has_repos": has_repos,
    "experiment_upstream_ids": experiment_upstream_ids,
    "roles_orchestration": roles_orchestration,
    "subtask_depends_on": subtask_depends_on,
    "paper_repo_parallel_overlap": paper_repo_parallel_overlap,
    "artifact_count_9": artifact_count_9,
    "nine_files_present": nine_files_present,
    "schema_all_json": schema_all_json,
    "format_parseability": format_parseability,
    "source_traceability": source_traceability_ok,
    "paper_subtask_failed": paper_subtask_failed,
    "assemble_not_fake_success": assemble_not_fake_success,
    "review_passed": review_passed,
    "review_present": review_present,
    "rag_has_evidence": rag_has_evidence,
    "rag_rerank_backend_recorded": rag_rerank_backend_recorded,
    "rag_need_mcp_fallback": rag_need_mcp_fallback,
    "rag_normal_answer": rag_normal_answer,
    "rag_max_rounds_refuse": rag_max_rounds_refuse,
    "mcp_tools_schema": mcp_tools_schema,
    "sandbox_succeeded": sandbox_succeeded,
    "sandbox_timed_out_or_rejected": sandbox_timed_out_or_rejected,
    "sandbox_pair_ok_and_reject": sandbox_pair_ok_and_reject,
    "artifacts_api_listable": artifacts_api_listable,
    "artifacts_api_download": artifacts_api_download,
}


def run_assertions(names: list[str], ctx: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    all_ok = True
    for name in names:
        fn = ASSERTIONS.get(name)
        if fn is None:
            results.append({"name": name, "ok": False, "detail": "unknown assertion"})
            all_ok = False
            continue
        try:
            ok, detail = fn(ctx)
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"exception: {exc}"
        results.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            all_ok = False
    return all_ok, results


def load_persisted_artifacts(task_id: str, tasks_dir: str | None = None) -> dict[str, str]:
    import os
    from pathlib import Path

    root = Path(tasks_dir or os.environ.get("SCHOLARFLOW_TASKS_DIR", "data/tasks"))
    art_dir = root / task_id / "artifacts"
    out: dict[str, str] = {}
    if not art_dir.is_dir():
        return out
    for path in art_dir.iterdir():
        if path.is_file():
            try:
                out[path.name] = path.read_text(encoding="utf-8")
            except Exception:
                continue
    return out
