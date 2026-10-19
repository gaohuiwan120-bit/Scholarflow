"""API-level sandbox execute tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from scholarflow_api.app import app

client = TestClient(app)


def test_health_reports_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLARFLOW_SANDBOX_ROOT", str(tmp_path / "sb"))
    h = client.get("/health").json()
    assert h["sandbox_available"] is True


def test_sandbox_execute_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLARFLOW_SANDBOX_ROOT", str(tmp_path / "sb"))
    resp = client.post(
        "/api/v1/sandbox/execute",
        json={
            "task_id": "sf-api-1",
            "code": "print('api-ok')\n",
            "prefer_docker": False,
            "timeout_seconds": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert "api-ok" in body["stdout"]
    assert body["backend"] == "process_jail"


def test_sandbox_execute_rejects_dangerous(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOLARFLOW_SANDBOX_ROOT", str(tmp_path / "sb"))
    resp = client.post(
        "/api/v1/sandbox/execute",
        json={
            "task_id": "sf-api-bad",
            "code": "import subprocess\nprint(1)\n",
            "prefer_docker": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
