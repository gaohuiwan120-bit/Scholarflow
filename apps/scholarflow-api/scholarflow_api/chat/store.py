"""Lightweight JSON/JSONL conversation persistence (Phase 8.1).

Layout (separate from TaskStore / RAG artifacts)::

    {root}/{conversation_id}/meta.json
    {root}/{conversation_id}/messages.jsonl

Root defaults to ``apps/scholarflow-api/data/conversations`` or
``$SCHOLARFLOW_CONVERSATIONS_DIR``. When unset but ``SCHOLARFLOW_TASKS_DIR``
is set, uses sibling ``../conversations``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from scholarflow_api.chat.schemas import (
    ChatMessage,
    ConversationMeta,
    EvidenceRef,
    MessageRole,
    ToolCallTraceItem,
    new_conversation_title,
)
from scholarflow_api.models import utc_now

logger = logging.getLogger("scholarflow_api.chat.store")

_ID_RE = re.compile(r"^cv-[a-f0-9]{12}$")


class ConversationNotFoundError(LookupError):
    pass


class ConversationInvalidIdError(ValueError):
    pass


class ConversationCorruptError(RuntimeError):
    pass


def conversations_root() -> Path:
    env = os.getenv("SCHOLARFLOW_CONVERSATIONS_DIR")
    if env:
        return Path(env)
    tasks = os.getenv("SCHOLARFLOW_TASKS_DIR")
    if tasks:
        return Path(tasks).resolve().parent / "conversations"
    from scholarflow_api.config import repo_root

    return repo_root() / "apps" / "scholarflow-api" / "data" / "conversations"


def validate_conversation_id(conversation_id: str) -> str:
    cid = (conversation_id or "").strip()
    if not _ID_RE.match(cid):
        raise ConversationInvalidIdError(
            f"Invalid conversation_id: {conversation_id!r} "
            "(expected cv- + 12 hex chars)"
        )
    if ".." in cid or "/" in cid or "\\" in cid:
        raise ConversationInvalidIdError("Invalid conversation_id path characters")
    return cid


class ConversationStore:
    """Thread-safe file-backed conversation store."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else conversations_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._global = threading.RLock()
        self._locks: dict[str, threading.RLock] = {}

    def _conv_lock(self, conversation_id: str) -> threading.RLock:
        with self._global:
            lock = self._locks.get(conversation_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[conversation_id] = lock
            return lock

    def _dir(self, conversation_id: str) -> Path:
        return self.root / conversation_id

    def _meta_path(self, conversation_id: str) -> Path:
        return self._dir(conversation_id) / "meta.json"

    def _messages_path(self, conversation_id: str) -> Path:
        return self._dir(conversation_id) / "messages.jsonl"

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _write_meta(self, meta: ConversationMeta) -> None:
        path = self._meta_path(meta.conversation_id)
        payload = meta.model_dump(mode="json")
        self._atomic_write_text(
            path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )

    def _read_meta(self, conversation_id: str) -> ConversationMeta:
        path = self._meta_path(conversation_id)
        if not path.is_file():
            raise ConversationNotFoundError(conversation_id)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return ConversationMeta.model_validate(data)
        except ConversationNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConversationCorruptError(
                f"Corrupt conversation meta for {conversation_id}: {exc}"
            ) from exc

    def create(self, *, title: str | None = None, metadata: dict[str, Any] | None = None) -> ConversationMeta:
        now = utc_now()
        conversation_id = f"cv-{uuid.uuid4().hex[:12]}"
        meta = ConversationMeta(
            conversation_id=conversation_id,
            title=new_conversation_title(title),
            created_at=now,
            updated_at=now,
            message_count=0,
            metadata=dict(metadata or {}),
        )
        with self._conv_lock(conversation_id):
            self._dir(conversation_id).mkdir(parents=True, exist_ok=True)
            self._write_meta(meta)
            # Touch empty messages file for a consistent layout
            msg_path = self._messages_path(conversation_id)
            if not msg_path.exists():
                msg_path.write_text("", encoding="utf-8")
        return meta

    def get(self, conversation_id: str) -> ConversationMeta:
        cid = validate_conversation_id(conversation_id)
        with self._conv_lock(cid):
            return self._read_meta(cid)

    def delete(self, conversation_id: str) -> None:
        """Permanently remove a conversation directory (meta + messages).

        Path is constrained to ``cv-[hex]{12}`` under store root — no traversal.
        """
        cid = validate_conversation_id(conversation_id)
        with self._conv_lock(cid):
            conv_dir = self._dir(cid)
            if not conv_dir.is_dir():
                raise ConversationNotFoundError(cid)
            # Ensure we only delete under the configured root.
            root_resolved = self.root.resolve()
            target = conv_dir.resolve()
            if root_resolved not in target.parents and target != root_resolved:
                raise ConversationInvalidIdError("Refusing to delete outside store root")
            if target.parent != root_resolved:
                raise ConversationInvalidIdError("Refusing to delete nested path")
            shutil.rmtree(target)
        with self._global:
            self._locks.pop(cid, None)

    def list_conversations(self) -> list[ConversationMeta]:
        items: list[ConversationMeta] = []
        with self._global:
            if not self.root.is_dir():
                return []
            dirs = sorted(
                (p for p in self.root.iterdir() if p.is_dir()),
                key=lambda p: p.name,
            )
        for d in dirs:
            try:
                cid = validate_conversation_id(d.name)
            except ConversationInvalidIdError:
                logger.warning("skip non-conversation dir: %s", d.name)
                continue
            try:
                with self._conv_lock(cid):
                    items.append(self._read_meta(cid))
            except ConversationNotFoundError:
                continue
            except ConversationCorruptError as exc:
                logger.warning("skip corrupt conversation %s: %s", cid, exc)
                continue
        items.sort(key=lambda m: m.updated_at, reverse=True)
        return items

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        cid = validate_conversation_id(conversation_id)
        with self._conv_lock(cid):
            # Ensure meta exists / is readable
            self._read_meta(cid)
            path = self._messages_path(cid)
            if not path.is_file():
                return []
            messages: list[ChatMessage] = []
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                raise ConversationCorruptError(
                    f"Cannot read messages for {cid}: {exc}"
                ) from exc
            for i, line in enumerate(lines, start=1):
                s = line.strip()
                if not s:
                    continue
                try:
                    data = json.loads(s)
                    messages.append(ChatMessage.model_validate(data))
                except Exception as exc:  # noqa: BLE001
                    raise ConversationCorruptError(
                        f"Corrupt messages.jsonl for {cid} at line {i}: {exc}"
                    ) from exc
            messages.sort(key=lambda m: (m.created_at, m.message_id))
            return messages

    def append_message(
        self,
        conversation_id: str,
        *,
        role: MessageRole,
        content: str,
        related_task_id: str | None = None,
        evidence_refs: list[EvidenceRef] | None = None,
        tool_call_trace: list[ToolCallTraceItem] | None = None,
    ) -> ChatMessage:
        cid = validate_conversation_id(conversation_id)
        text = (content or "").strip()
        if not text:
            raise ValueError("message content must not be empty")
        with self._conv_lock(cid):
            meta = self._read_meta(cid)
            now = utc_now()
            msg = ChatMessage(
                message_id=f"msg-{uuid.uuid4().hex[:12]}",
                conversation_id=cid,
                role=role,
                content=text,
                created_at=now,
                tool_call_trace=list(tool_call_trace or []),
                related_task_id=related_task_id,
                evidence_refs=list(evidence_refs or []),
            )
            path = self._messages_path(cid)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(msg.model_dump_json() + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            meta.message_count = int(meta.message_count) + 1
            meta.updated_at = now
            # Keep title useful: first user message can refine empty-ish titles
            if role == "user" and meta.message_count == 1:
                preview = text.replace("\n", " ")[:80]
                if meta.title.startswith("Conversation "):
                    meta.title = preview or meta.title
            self._write_meta(meta)
            return msg

    def related_task_ids(self, conversation_id: str) -> list[str]:
        seen: list[str] = []
        for msg in self.list_messages(conversation_id):
            tid = msg.related_task_id
            if tid and tid not in seen:
                seen.append(tid)
        return seen
