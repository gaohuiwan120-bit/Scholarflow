"""FastAPI TestClient helpers for Agent Bench (Phase 6)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "apps" / "scholarflow-api"
HARNESS = ROOT / "backend" / "packages" / "harness"


def ensure_paths() -> None:
    for p in (str(API_ROOT), str(HARNESS), str(ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)


def prepare_env(work_root: Path) -> dict[str, str]:
    """Set isolation env before importing the FastAPI app."""
    tasks = work_root / "tasks"
    sandbox = work_root / "sandbox"
    rag_index = work_root / "rag_index"
    tasks.mkdir(parents=True, exist_ok=True)
    sandbox.mkdir(parents=True, exist_ok=True)
    rag_index.mkdir(parents=True, exist_ok=True)
    updates = {
        "SCHOLARFLOW_TASKS_DIR": str(tasks),
        "SCHOLARFLOW_SANDBOX_ROOT": str(sandbox),
        "SCHOLAR_RAG_INDEX_DIR": str(rag_index),
    }
    os.environ.update(updates)
    return updates


def get_client():
    ensure_paths()
    from fastapi.testclient import TestClient
    from scholarflow_api.app import app

    return TestClient(app)


def create_and_wait(
    client,
    body: dict[str, Any],
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    created = client.post("/api/v1/tasks", json=body)
    if created.status_code != 200:
        return {
            "ok": False,
            "error": f"create status={created.status_code} body={created.text}",
            "create_status": created.status_code,
        }
    tid = created.json()["task_id"]
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        st = client.get(f"/api/v1/tasks/{tid}").json()
        last = st
        if st["status"] in {"succeeded", "partial_succeeded", "failed", "timed_out"}:
            result = client.get(f"/api/v1/tasks/{tid}/result").json()
            result["_poll_status"] = st
            result["ok"] = True
            return result
        time.sleep(0.15)
    return {
        "ok": False,
        "error": f"timeout waiting for {tid}",
        "task_id": tid,
        "last_status": last,
    }


def sandbox_execute(client, body: dict[str, Any]) -> dict[str, Any]:
    resp = client.post("/api/v1/sandbox/execute", json=body)
    return {"http_status": resp.status_code, "body": resp.json() if resp.content else {}}


def mcp_tools(client) -> dict[str, Any]:
    resp = client.get("/api/v1/mcp/tools")
    return {"http_status": resp.status_code, "body": resp.json() if resp.content else {}}


def list_artifacts(client, task_id: str) -> dict[str, Any]:
    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts")
    return {"http_status": resp.status_code, "body": resp.json() if resp.content else {}}


def download_artifact(client, task_id: str, filename: str) -> dict[str, Any]:
    resp = client.get(f"/api/v1/tasks/{task_id}/artifacts/{filename}")
    return {
        "http_status": resp.status_code,
        "content": resp.content if resp.status_code == 200 else b"",
        "text": resp.text if resp.status_code == 200 else "",
    }


def git_meta(repo: Path | None = None) -> dict[str, Any]:
    import subprocess

    root = repo or ROOT
    meta: dict[str, Any] = {"git_commit": None, "git_dirty": None, "git_error": None}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root), text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(root), text=True, stderr=subprocess.DEVNULL
        )
        meta["git_commit"] = commit
        meta["git_dirty"] = bool(dirty.strip())
    except Exception as exc:  # noqa: BLE001
        meta["git_error"] = str(exc)
    return meta
