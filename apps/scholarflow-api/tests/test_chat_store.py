"""Phase 8.1 ConversationStore unit tests."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pytest

from scholarflow_api.chat.store import (
    ConversationCorruptError,
    ConversationInvalidIdError,
    ConversationNotFoundError,
    ConversationStore,
)


def test_create_and_get(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create(title="t1")
    assert meta.conversation_id.startswith("cv-")
    assert meta.message_count == 0
    loaded = store.get(meta.conversation_id)
    assert loaded.title == "t1"
    assert (tmp_path / "conversations" / meta.conversation_id / "meta.json").is_file()
    assert (tmp_path / "conversations" / meta.conversation_id / "messages.jsonl").is_file()


def test_message_order_and_persist_across_instances(tmp_path: Path) -> None:
    root = tmp_path / "conversations"
    a = ConversationStore(root=root)
    meta = a.create(title="persist")
    a.append_message(meta.conversation_id, role="user", content="first")
    a.append_message(meta.conversation_id, role="assistant", content="second")
    a.append_message(meta.conversation_id, role="user", content="third")

    b = ConversationStore(root=root)
    msgs = b.list_messages(meta.conversation_id)
    assert [m.content for m in msgs] == ["first", "second", "third"]
    assert [m.role for m in msgs] == ["user", "assistant", "user"]
    detail = b.get(meta.conversation_id)
    assert detail.message_count == 3


def test_session_isolation(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    c1 = store.create(title="A")
    c2 = store.create(title="B")
    store.append_message(c1.conversation_id, role="user", content="only-a")
    store.append_message(c2.conversation_id, role="user", content="only-b")
    assert [m.content for m in store.list_messages(c1.conversation_id)] == ["only-a"]
    assert [m.content for m in store.list_messages(c2.conversation_id)] == ["only-b"]


def test_delete_conversation(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    keep = store.create(title="keep")
    gone = store.create(title="gone")
    store.append_message(gone.conversation_id, role="user", content="bye")
    store.delete(gone.conversation_id)
    assert not (tmp_path / "conversations" / gone.conversation_id).exists()
    with pytest.raises(ConversationNotFoundError):
        store.get(gone.conversation_id)
    assert store.get(keep.conversation_id).title == "keep"
    ids = {c.conversation_id for c in store.list_conversations()}
    assert keep.conversation_id in ids
    assert gone.conversation_id not in ids
    with pytest.raises(ConversationNotFoundError):
        store.delete(gone.conversation_id)


def test_invalid_id(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    with pytest.raises(ConversationInvalidIdError):
        store.get("../etc/passwd")
    with pytest.raises(ConversationInvalidIdError):
        store.get("not-a-valid-id")
    with pytest.raises(ConversationNotFoundError):
        store.get("cv-deadbeef0000")


def test_corrupt_meta(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create(title="ok")
    path = tmp_path / "conversations" / meta.conversation_id / "meta.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ConversationCorruptError):
        store.get(meta.conversation_id)


def test_corrupt_messages_line(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create(title="ok")
    store.append_message(meta.conversation_id, role="user", content="good")
    path = tmp_path / "conversations" / meta.conversation_id / "messages.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{bad-line\n")
    with pytest.raises(ConversationCorruptError):
        store.list_messages(meta.conversation_id)


def test_reserved_fields_default_empty(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create()
    msg = store.append_message(meta.conversation_id, role="user", content="hi")
    assert msg.tool_call_trace == []
    assert msg.evidence_refs == []
    assert msg.related_task_id is None


def test_related_task_ids(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create()
    store.append_message(
        meta.conversation_id, role="assistant", content="done", related_task_id="sf-aaa"
    )
    store.append_message(
        meta.conversation_id, role="assistant", content="again", related_task_id="sf-aaa"
    )
    store.append_message(
        meta.conversation_id, role="assistant", content="other", related_task_id="sf-bbb"
    )
    assert store.related_task_ids(meta.conversation_id) == ["sf-aaa", "sf-bbb"]


def test_concurrent_appends(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    meta = store.create(title="concurrent")
    cid = meta.conversation_id
    n = 40

    def _write(i: int) -> str:
        msg = store.append_message(cid, role="user", content=f"m-{i:03d}")
        return msg.message_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_write, i) for i in range(n)]
        ids = [f.result() for f in as_completed(futs)]
    assert len(ids) == n
    assert len(set(ids)) == n
    msgs = store.list_messages(cid)
    assert len(msgs) == n
    assert store.get(cid).message_count == n
    # All contents present (order may interleave by timestamp)
    contents = {m.content for m in msgs}
    assert contents == {f"m-{i:03d}" for i in range(n)}


def test_list_skips_corrupt_dirs(tmp_path: Path) -> None:
    store = ConversationStore(root=tmp_path / "conversations")
    good = store.create(title="good")
    bad_dir = tmp_path / "conversations" / "cv-aaaaaaaaaaaa"
    bad_dir.mkdir()
    (bad_dir / "meta.json").write_text("NOPE", encoding="utf-8")
    listed = store.list_conversations()
    ids = {c.conversation_id for c in listed}
    assert good.conversation_id in ids
    assert "cv-aaaaaaaaaaaa" not in ids
