#!/usr/bin/env python3
"""Minimal Docker backend verification for Phase-5 (daemon must be up)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "packages" / "harness"))


def main() -> int:
    from scholarflow.scholar.sandbox import SandboxRequest, execute_sandbox
    from scholarflow.scholar.sandbox.backends import docker_available

    td = Path(tempfile.mkdtemp(prefix="sf-docker-verify-"))
    os.environ["SCHOLARFLOW_SANDBOX_ROOT"] = str(td)
    print("SCHOLARFLOW_SANDBOX_ROOT=", td)
    print("docker_available=", docker_available())
    if not docker_available():
        print("DOCKER_UNAVAILABLE — start Docker Desktop engine only (no extra containers needed)")
        return 2

    r = execute_sandbox(
        SandboxRequest(
            task_id="d-ok",
            code="print('in-docker')\nprint(1+1)\n",
            prefer_docker=True,
            timeout_seconds=60,
        )
    )
    print("status=", r.status)
    print("backend=", r.backend)
    print("exit=", r.exit_code)
    print("stdout=", repr(r.stdout.strip()))
    print("err=", r.error_summary)
    print("duration_ms=", r.duration_ms)
    if r.backend != "docker" or r.status != "succeeded" or "in-docker" not in r.stdout:
        print("DOCKER_MIN_FAILED")
        return 1
    print("DOCKER_MIN_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
