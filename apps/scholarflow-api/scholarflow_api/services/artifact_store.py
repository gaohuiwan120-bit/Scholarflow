"""Persist ScholarFlow 9-pack artifacts under per-task directories."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from scholarflow_api.config import repo_root

SAFE_TASK_RE = re.compile(r"^sf-[a-zA-Z0-9_-]{4,64}$|^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
REQUIRED = (
    "research_report.md",
    "research_plan.json",
    "paper_evidence.json",
    "paper_matrix.csv",
    "repository_evidence.json",
    "repository_matrix.csv",
    "experiment_plan.md",
    "evidence_review.json",
    "sources.json",
)


class ArtifactMeta(BaseModel):
    artifact_id: str
    artifact_type: str
    filename: str
    path: str
    created_at: str
    data_mode: str
    schema_valid: bool | None = None
    schema_error: str | None = None
    size_bytes: int = 0
    evidence_refs: list[str] = Field(default_factory=list)


class ArtifactManifest(BaseModel):
    task_id: str
    created_at: str
    data_mode: str
    overwrite_policy: str = "replace"
    artifacts: list[ArtifactMeta] = Field(default_factory=list)


def tasks_root() -> Path:
    root = Path(os_getenv_tasks_root())
    root.mkdir(parents=True, exist_ok=True)
    return root


def os_getenv_tasks_root() -> str:
    import os

    env = os.getenv("SCHOLARFLOW_TASKS_DIR")
    if env:
        return env
    return str(repo_root() / "apps" / "scholarflow-api" / "data" / "tasks")


def validate_task_id(task_id: str) -> str:
    tid = task_id.strip()
    if not SAFE_TASK_RE.match(tid) or ".." in tid or "/" in tid or "\\" in tid:
        raise ValueError(f"invalid task_id: {task_id}")
    return tid


def task_dir(task_id: str) -> Path:
    tid = validate_task_id(task_id)
    path = tasks_root() / tid / "artifacts"
    return path


def resolve_artifact_path(task_id: str, filename: str) -> Path:
    if filename not in REQUIRED:
        raise ValueError(f"unknown artifact filename: {filename}")
    base = task_dir(task_id).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("path traversal rejected")
    return target


def _schema_check(filename: str, content: str) -> tuple[bool | None, str | None]:
    if not filename.endswith(".json"):
        return None, None
    try:
        from scholarflow_api.config import ensure_harness_on_path

        ensure_harness_on_path()
        from scholarflow.scholar.validation import validate_json_artifact

        payload = json.loads(content)
        validate_json_artifact(filename, payload)
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def persist_artifacts(
    task_id: str,
    contents: dict[str, str],
    *,
    data_mode: str,
    evidence_refs: list[str] | None = None,
    overwrite: bool = True,
) -> ArtifactManifest:
    """Write artifact files + manifest. Returns metadata."""
    out_dir = task_dir(task_id)
    if out_dir.exists() and overwrite:
        for child in out_dir.iterdir():
            if child.is_file():
                child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    metas: list[ArtifactMeta] = []
    refs = evidence_refs or []

    for name in REQUIRED:
        if name not in contents:
            continue
        text = contents[name]
        path = resolve_artifact_path(task_id, name)
        path.write_text(text, encoding="utf-8")
        ok, err = _schema_check(name, text)
        metas.append(
            ArtifactMeta(
                artifact_id=f"{task_id}:{name}",
                artifact_type=name.rsplit(".", 1)[-1],
                filename=name,
                path=str(path),
                created_at=now,
                data_mode=data_mode,
                schema_valid=ok,
                schema_error=err,
                size_bytes=len(text.encode("utf-8")),
                evidence_refs=refs,
            )
        )

    manifest = ArtifactManifest(
        task_id=task_id,
        created_at=now,
        data_mode=data_mode,
        overwrite_policy="replace" if overwrite else "keep",
        artifacts=metas,
    )
    # manifest.json is metadata (not one of the 9 research artifacts)
    base = task_dir(task_id).resolve()
    mp = (base / "manifest.json").resolve()
    if not str(mp).startswith(str(base)):
        raise ValueError("path traversal rejected")
    mp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def list_artifacts(task_id: str) -> ArtifactManifest | None:
    base = task_dir(task_id)
    mp = base / "manifest.json"
    if not mp.is_file():
        return None
    return ArtifactManifest.model_validate_json(mp.read_text(encoding="utf-8"))


def read_artifact_bytes(task_id: str, filename: str) -> tuple[bytes, str]:
    if filename == "manifest.json":
        path = task_dir(task_id) / "manifest.json"
    else:
        path = resolve_artifact_path(task_id, filename)
    if not path.is_file():
        raise FileNotFoundError(filename)
    media = "application/octet-stream"
    if filename.endswith(".json"):
        media = "application/json"
    elif filename.endswith(".md"):
        media = "text/markdown; charset=utf-8"
    elif filename.endswith(".csv"):
        media = "text/csv; charset=utf-8"
    return path.read_bytes(), media
