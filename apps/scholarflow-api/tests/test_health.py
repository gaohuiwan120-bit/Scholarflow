"""Health endpoint smoke test (no RAG model load required for import path check)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from scholarflow_api.app import app


def test_health_ok() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "scholarflow-api"
    assert data["runtime"] == "multi"
    assert "rag_v1" in data.get("runtimes", [])
    assert "research_graph_v1" in data.get("runtimes", [])
    assert data.get("langgraph_available") is True
    assert "harness_importable" in data
    assert data["artifacts_dir_exists"] is True
    assert "llm_configured" in data
    assert "llm_model" in data
    assert "sk-" not in str(data)
