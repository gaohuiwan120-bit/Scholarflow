"""API integration: research_orchestration + rag_query regression."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from scholarflow_api.app import app


client = TestClient(app)


def _wait(task_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"/api/v1/tasks/{task_id}").json()
        if st["status"] in {"succeeded", "partial_succeeded", "failed", "timed_out"}:
            return client.get(f"/api/v1/tasks/{task_id}/result").json()
        time.sleep(0.2)
    raise AssertionError(f"timeout waiting for {task_id}")


def test_health_lists_runtimes() -> None:
    h = client.get("/health").json()
    assert h["status"] == "ok"
    assert h["langgraph_available"] is True
    assert "rag_v1" in h["runtimes"]
    assert "research_graph_v1" in h["runtimes"]


def test_rag_query_still_works() -> None:
    created = client.post(
        "/api/v1/tasks",
        json={
            "kind": "rag_query",
            "question": "Blended RAG hybrid dense sparse vs Naive RAG",
            "ensure_index": True,
        },
    )
    assert created.status_code == 200
    tid = created.json()["task_id"]
    result = _wait(tid)
    assert result["status"] == "succeeded"
    assert result["result"]["evidence"]
    assert result["runtime"] == "rag_v1"


def test_research_orchestration_api() -> None:
    created = client.post(
        "/api/v1/tasks",
        json={
            "kind": "research_orchestration",
            "question": "Blended RAG hybrid dense sparse vs Naive RAG",
            "data_mode": "fixture",
        },
    )
    assert created.status_code == 200
    tid = created.json()["task_id"]
    # poll status should eventually include subtasks
    deadline = time.time() + 60
    saw_subtasks = False
    while time.time() < deadline:
        st = client.get(f"/api/v1/tasks/{tid}").json()
        if st.get("subtasks"):
            saw_subtasks = True
        if st["status"] in {"succeeded", "partial_succeeded", "failed", "timed_out"}:
            break
        time.sleep(0.2)
    result = client.get(f"/api/v1/tasks/{tid}/result").json()
    assert result["status"] in {"succeeded", "partial_succeeded"}
    assert result["runtime"] == "research_graph_v1"
    assert result["research"] is not None
    assert result["research"]["artifact_summary"]["artifact_count"] == 9
    assert len(result["subtasks"]) >= 4
    assert saw_subtasks or result["subtasks"]


def test_research_review_failure_api() -> None:
    created = client.post(
        "/api/v1/tasks",
        json={
            "kind": "research_orchestration",
            "question": "force fail",
            "data_mode": "fixture",
            "force_fail_review": True,
        },
    )
    tid = created.json()["task_id"]
    result = _wait(tid)
    assert result["status"] == "failed"
    assert result["error"]


def test_invalid_kind_rejected_via_empty() -> None:
    bad = client.post("/api/v1/tasks", json={"kind": "rag_query", "question": "x"})
    # min length 2
    assert bad.status_code == 422


def test_artifacts_list_and_download(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SCHOLARFLOW_TASKS_DIR", str(tmp_path / "tasks"))
    created = client.post(
        "/api/v1/tasks",
        json={
            "kind": "research_orchestration",
            "question": "Blended RAG hybrid dense sparse vs Naive RAG",
            "data_mode": "fixture",
            "persist_artifacts": True,
        },
    )
    assert created.status_code == 200
    tid = created.json()["task_id"]
    result = _wait(tid)
    assert result["status"] in {"succeeded", "partial_succeeded"}
    assert result["research"]["artifact_manifest"]
    assert result["research"]["data_mode"] == "fixture"

    listed = client.get(f"/api/v1/tasks/{tid}/artifacts")
    assert listed.status_code == 200
    body = listed.json()
    assert body["task_id"] == tid
    assert len(body["artifacts"]) == 9
    assert body["data_mode"] == "fixture"

    name = body["artifacts"][0]["filename"]
    dl = client.get(f"/api/v1/tasks/{tid}/artifacts/{name}")
    assert dl.status_code == 200
    assert len(dl.content) > 0

    bad = client.get(f"/api/v1/tasks/{tid}/artifacts/../secrets.txt")
    assert bad.status_code in {400, 404, 422}
