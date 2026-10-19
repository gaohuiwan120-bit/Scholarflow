"""Phase 8.1 conversation REST API tests."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from scholarflow_api.chat.router import create_conversation_router
from scholarflow_api.chat.store import ConversationStore


def _client(tmp_path: Path) -> tuple[TestClient, ConversationStore]:
    store = ConversationStore(root=tmp_path / "conversations")
    app = FastAPI()
    app.include_router(create_conversation_router(store))
    return TestClient(app), store


def test_create_list_get_messages(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    created = client.post("/api/v1/conversations", json={"title": "demo"}).json()
    cid = created["conversation"]["conversation_id"]
    assert cid.startswith("cv-")

    listed = client.get("/api/v1/conversations").json()
    assert listed["total"] >= 1
    assert any(c["conversation_id"] == cid for c in listed["conversations"])

    detail = client.get(f"/api/v1/conversations/{cid}").json()
    assert detail["title"] == "demo"
    assert detail["message_count"] == 0

    r1 = client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"role": "user", "content": "hello"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"role": "assistant", "content": "world", "related_task_id": "sf-abc123"},
    )
    assert r2.status_code == 200
    hist = client.get(f"/api/v1/conversations/{cid}/messages").json()
    assert hist["total"] == 2
    assert [m["content"] for m in hist["messages"]] == ["hello", "world"]
    assert hist["messages"][0]["tool_call_trace"] == []
    assert hist["messages"][1]["related_task_id"] == "sf-abc123"

    tasks = client.get(f"/api/v1/conversations/{cid}/tasks").json()
    assert tasks["related_task_ids"] == ["sf-abc123"]


def test_api_restart_restores_history(tmp_path: Path) -> None:
    root = tmp_path / "conversations"
    c1, store = _client(tmp_path)
    cid = c1.post("/api/v1/conversations", json={"title": "r"}).json()["conversation"][
        "conversation_id"
    ]
    c1.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"role": "user", "content": "survive"},
    )
    assert store.root == root

    # New process / new store instance sharing same disk root
    c2, _ = _client(tmp_path)
    hist = c2.get(f"/api/v1/conversations/{cid}/messages").json()
    assert [m["content"] for m in hist["messages"]] == ["survive"]
    detail = c2.get(f"/api/v1/conversations/{cid}").json()
    assert detail["message_count"] == 1


def test_isolation_via_api(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    a = client.post("/api/v1/conversations", json={"title": "A"}).json()["conversation"][
        "conversation_id"
    ]
    b = client.post("/api/v1/conversations", json={"title": "B"}).json()["conversation"][
        "conversation_id"
    ]
    client.post(f"/api/v1/conversations/{a}/messages", json={"role": "user", "content": "a-only"})
    client.post(f"/api/v1/conversations/{b}/messages", json={"role": "user", "content": "b-only"})
    assert client.get(f"/api/v1/conversations/{a}/messages").json()["messages"][0]["content"] == "a-only"
    assert client.get(f"/api/v1/conversations/{b}/messages").json()["messages"][0]["content"] == "b-only"


def test_invalid_and_missing_ids(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert client.get("/api/v1/conversations/not-valid").status_code == 400
    assert client.get("/api/v1/conversations/cv-ffffffffffff").status_code == 404
    assert (
        client.post(
            "/api/v1/conversations/cv-ffffffffffff/messages",
            json={"role": "user", "content": "x"},
        ).status_code
        == 404
    )
    assert client.delete("/api/v1/conversations/not-valid").status_code == 400
    assert client.delete("/api/v1/conversations/cv-ffffffffffff").status_code == 404


def test_delete_conversation_api(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    cid = client.post("/api/v1/conversations", json={"title": "to-delete"}).json()[
        "conversation"
    ]["conversation_id"]
    client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"role": "user", "content": "hello"},
    )
    resp = client.delete(f"/api/v1/conversations/{cid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert not (store.root / cid).exists()
    assert client.get(f"/api/v1/conversations/{cid}").status_code == 404
    listed = client.get("/api/v1/conversations").json()
    assert all(c["conversation_id"] != cid for c in listed["conversations"])


def test_corrupt_meta_returns_409(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    cid = client.post("/api/v1/conversations", json={}).json()["conversation"][
        "conversation_id"
    ]
    (store.root / cid / "meta.json").write_text("{broken", encoding="utf-8")
    assert client.get(f"/api/v1/conversations/{cid}").status_code == 409


def test_empty_content_rejected(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    cid = client.post("/api/v1/conversations", json={}).json()["conversation"][
        "conversation_id"
    ]
    resp = client.post(
        f"/api/v1/conversations/{cid}/messages",
        json={"role": "user", "content": "   "},
    )
    assert resp.status_code == 422


def test_main_app_mounts_conversations() -> None:
    from scholarflow_api.app import app

    client = TestClient(app)
    # Ensure route exists on the real app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/conversations" in paths
    # Smoke create against default data dir (gitignored)
    resp = client.post("/api/v1/conversations", json={"title": "mount-smoke"})
    assert resp.status_code == 200
    assert resp.json()["conversation"]["conversation_id"].startswith("cv-")
