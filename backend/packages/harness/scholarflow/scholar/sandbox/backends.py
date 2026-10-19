"""Execution backends: process jail (default) and optional Docker."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scholarflow.scholar.sandbox.models import SandboxRequest, SandboxResult


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    raw = text.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return text, False
    return raw[:limit].decode("utf-8", errors="replace") + "\n...[truncated]...", True


def _strip_env(*, allow_network: bool) -> dict[str, str]:
    """Minimal env — no host secrets, no proxy unless network allowed."""
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATHEXT", "COMSPEC"}
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in keep or k.startswith("PYTHON"):
            # Drop user site / virtualenv hints that expand privilege surface
            if k in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}:
                continue
            env[k] = v
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if not allow_network:
        for k in list(env):
            if "PROXY" in k.upper() or k.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}:
                env.pop(k, None)
        env["NO_PROXY"] = "*"
    return env


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=8,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


def run_process_jail(
    req: SandboxRequest,
    *,
    work_dir: Path,
    script_path: Path,
) -> SandboxResult:
    """Run under a dedicated work directory. NOT a strong security boundary.

    Provides: timeout, output caps, stripped env, cwd jail.
    Does NOT provide: reliable network isolation or memory hard-cap on Windows.
    """
    notes = [
        "backend=process_jail: host process with cwd jail — not equivalent to a hardened container",
        "network isolation is best-effort (imports blocked + proxies cleared); OS firewall not enforced",
        "memory_mb is advisory on Windows process backend (enforced under docker backend)",
    ]
    started = time.perf_counter()
    cmd = [sys.executable, "-I", str(script_path.name)]
    try:
        # stdin=DEVNULL is required when launched under MCP stdio servers:
        # inheriting the JSON-RPC pipe can block the child indefinitely.
        proc = subprocess.run(
            cmd,
            cwd=str(work_dir),
            env=_strip_env(allow_network=req.allow_network),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=req.timeout_seconds,
            check=False,
        )
        duration = int((time.perf_counter() - started) * 1000)
        stdout, trunc_out = _truncate(proc.stdout or "", req.max_output_bytes)
        stderr, trunc_err = _truncate(proc.stderr or "", req.max_output_bytes)
        if trunc_out or trunc_err:
            notes.append("output_truncated")
        status = "succeeded" if proc.returncode == 0 else "failed"
        return SandboxResult(
            task_id=req.task_id,
            status=status,  # type: ignore[arg-type]
            backend="process_jail",
            exit_code=proc.returncode,
            duration_ms=duration,
            stdout=stdout,
            stderr=stderr,
            error_summary=None if status == "succeeded" else (stderr.strip()[:400] or f"exit={proc.returncode}"),
            work_dir=str(work_dir),
            limits={
                "timeout_seconds": req.timeout_seconds,
                "memory_mb": req.memory_mb,
                "max_output_bytes": req.max_output_bytes,
                "allow_network": req.allow_network,
                "memory_enforced": False,
            },
            security_notes=notes,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - started) * 1000)
        stdout, _ = _truncate((exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""), req.max_output_bytes)
        stderr, _ = _truncate((exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or ""), req.max_output_bytes)
        return SandboxResult(
            task_id=req.task_id,
            status="timed_out",
            backend="process_jail",
            exit_code=None,
            duration_ms=duration,
            stdout=stdout,
            stderr=stderr,
            error_summary=f"timed out after {req.timeout_seconds}s",
            work_dir=str(work_dir),
            limits={
                "timeout_seconds": req.timeout_seconds,
                "memory_mb": req.memory_mb,
                "max_output_bytes": req.max_output_bytes,
                "allow_network": req.allow_network,
                "memory_enforced": False,
            },
            security_notes=notes,
        )


def run_docker(
    req: SandboxRequest,
    *,
    work_dir: Path,
    script_name: str,
) -> SandboxResult:
    """Docker-backed execution when daemon is available.

    Uses --network=none by default, memory/cpu caps, read-only rootfs + tmpfs.
    Still not 'absolute' isolation — document residual risks (escape CVEs, misconfig).
    """
    notes = [
        "backend=docker: stronger isolation than process_jail, still not absolute security",
        "image=python:3.12-alpine (pulled on demand if missing)",
    ]
    started = time.perf_counter()
    network = "bridge" if req.allow_network else "none"
    # Mount work as rw under /work; rootfs read-only; tmp for scratch
    cmd = [
        "docker",
        "run",
        "--rm",
        f"--network={network}",
        f"--memory={int(req.memory_mb)}m",
        "--memory-swap={0}m".format(int(req.memory_mb)),
        "--cpus=0.5",
        "--pids-limit=64",
        "--read-only",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,source={work_dir.resolve()},target=/work",
        "-w",
        "/work",
        "--user",
        "65534:65534",
        "python:3.12-alpine",
        "python",
        "-I",
        script_name,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=req.timeout_seconds + 30.0,  # allow image pull headroom once
            check=False,
        )
        duration = int((time.perf_counter() - started) * 1000)
        stdout, trunc_out = _truncate(proc.stdout or "", req.max_output_bytes)
        stderr, trunc_err = _truncate(proc.stderr or "", req.max_output_bytes)
        if trunc_out or trunc_err:
            notes.append("output_truncated")
        # Docker OOM often exit 137
        if proc.returncode in {137, 139}:
            status = "resource_exhausted"
            err = f"resource limit likely hit (exit={proc.returncode})"
        elif proc.returncode == 0:
            status = "succeeded"
            err = None
        else:
            status = "failed"
            err = (stderr.strip()[:400] or f"exit={proc.returncode}")
        return SandboxResult(
            task_id=req.task_id,
            status=status,  # type: ignore[arg-type]
            backend="docker",
            exit_code=proc.returncode,
            duration_ms=duration,
            stdout=stdout,
            stderr=stderr,
            error_summary=err,
            work_dir=str(work_dir),
            limits={
                "timeout_seconds": req.timeout_seconds,
                "memory_mb": req.memory_mb,
                "max_output_bytes": req.max_output_bytes,
                "allow_network": req.allow_network,
                "memory_enforced": True,
                "network_mode": network,
            },
            security_notes=notes,
        )
    except subprocess.TimeoutExpired:
        duration = int((time.perf_counter() - started) * 1000)
        return SandboxResult(
            task_id=req.task_id,
            status="timed_out",
            backend="docker",
            exit_code=None,
            duration_ms=duration,
            error_summary=f"docker run timed out after {req.timeout_seconds}s (+pull headroom)",
            work_dir=str(work_dir),
            limits={
                "timeout_seconds": req.timeout_seconds,
                "memory_mb": req.memory_mb,
                "max_output_bytes": req.max_output_bytes,
                "allow_network": req.allow_network,
                "memory_enforced": True,
                "network_mode": network,
            },
            security_notes=notes,
        )
