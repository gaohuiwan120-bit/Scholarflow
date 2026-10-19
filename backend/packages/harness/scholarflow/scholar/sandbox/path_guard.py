"""Path jail helpers — keep all file access under a task work directory."""

from __future__ import annotations

import re
from pathlib import Path

_SAFE_TASK = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def validate_task_id(task_id: str) -> str:
    tid = (task_id or "").strip()
    if not _SAFE_TASK.match(tid) or ".." in tid:
        raise ValueError(f"invalid task_id for sandbox: {task_id!r}")
    return tid


def resolve_under(root: Path, *parts: str) -> Path:
    """Resolve path and ensure it stays inside root (no traversal)."""
    base = root.resolve()
    target = (base.joinpath(*parts)).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path traversal rejected: {target}") from exc
    return target


def safe_filename(name: str) -> str:
    base = Path(name).name
    if not base or base in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError(f"invalid filename: {name!r}")
    if not re.match(r"^[a-zA-Z0-9._-]{1,64}$", base):
        raise ValueError(f"invalid filename chars: {name!r}")
    return base
