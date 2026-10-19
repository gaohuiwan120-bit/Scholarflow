"""ScholarFlow sandbox facade — policy → workdir → backend."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from scholarflow.scholar.sandbox.backends import docker_available, run_docker, run_process_jail
from scholarflow.scholar.sandbox.models import SandboxRequest, SandboxResult
from scholarflow.scholar.sandbox.path_guard import resolve_under, safe_filename, validate_task_id
from scholarflow.scholar.sandbox.policy import validate_python_source

logger = logging.getLogger("scholarflow.scholar.sandbox")


def _default_root() -> Path:
    env = os.getenv("SCHOLARFLOW_SANDBOX_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "apps" / "scholarflow-api").is_dir():
            return parent / "apps" / "scholarflow-api" / "data" / "sandbox"
    return Path.cwd() / "data" / "sandbox"


def execute_sandbox(req: SandboxRequest) -> SandboxResult:
    """Execute untrusted Python under ScholarFlow policy.

    Prefer Docker when available and ``prefer_docker=True``; otherwise process jail.
    Never silently claim process_jail is container-grade isolation.
    """
    tid = validate_task_id(req.task_id)
    rejects = validate_python_source(req.code, allow_network=req.allow_network)
    if rejects:
        return SandboxResult(
            task_id=tid,
            status="rejected",
            backend="unavailable",
            error_summary="; ".join(rejects),
            security_notes=[
                "static_policy_rejected",
                "code was not executed on host",
            ],
            limits={
                "timeout_seconds": req.timeout_seconds,
                "memory_mb": req.memory_mb,
                "max_output_bytes": req.max_output_bytes,
                "allow_network": req.allow_network,
            },
        )

    root = _default_root()
    root.mkdir(parents=True, exist_ok=True)
    work = resolve_under(root, tid, "work")
    work.mkdir(parents=True, exist_ok=True)
    # wipe previous run files in work (keep directory)
    for child in work.iterdir():
        if child.is_file():
            child.unlink()

    fname = safe_filename(req.filename)
    script = resolve_under(work, fname)
    script.write_text(req.code, encoding="utf-8")

    use_docker = bool(req.prefer_docker) and docker_available()
    if req.prefer_docker and not use_docker:
        logger.info("docker unavailable — falling back to process_jail for task=%s", tid)

    if use_docker:
        result = run_docker(req, work_dir=work, script_name=fname)
    else:
        result = run_process_jail(req, work_dir=work, script_path=script)

    # Persist run metadata next to work dir (outside script cwd name collision)
    meta_dir = resolve_under(root, tid)
    meta = {
        "task_id": tid,
        "status": result.status,
        "backend": result.backend,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "error_summary": result.error_summary,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "limits": result.limits,
        "security_notes": result.security_notes,
    }
    (meta_dir / "last_run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "sandbox task=%s status=%s backend=%s duration_ms=%s",
        tid,
        result.status,
        result.backend,
        result.duration_ms,
    )
    return result
