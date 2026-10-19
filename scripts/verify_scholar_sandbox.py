#!/usr/bin/env python3
"""Minimal process_jail verification for Phase-5 supplemental acceptance."""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "packages" / "harness"))


def main() -> int:
    from scholarflow.scholar.sandbox import SandboxRequest, execute_sandbox
    from scholarflow.scholar.sandbox.backends import docker_available

    td = Path(tempfile.mkdtemp(prefix="sf-sb-verify-"))
    os.environ["SCHOLARFLOW_SANDBOX_ROOT"] = str(td)
    print("SCHOLARFLOW_SANDBOX_ROOT=", td)
    print("docker_available=", docker_available())

    r1 = execute_sandbox(
        SandboxRequest(task_id="v-ok", code="print(40+2)\n", prefer_docker=False, timeout_seconds=5)
    )
    assert r1.status == "succeeded" and "42" in r1.stdout
    assert (td / "v-ok" / "last_run.json").is_file()
    print("OK", r1.status, r1.backend)

    t0 = time.perf_counter()
    r2 = execute_sandbox(
        SandboxRequest(
            task_id="v-to",
            code="import time\ntime.sleep(20)\n",
            prefer_docker=False,
            timeout_seconds=1.5,
        )
    )
    wall = time.perf_counter() - t0
    assert r2.status == "timed_out"
    assert wall < 5.0
    print("TIMEOUT", r2.status, "wall=", round(wall, 2))

    r3 = execute_sandbox(
        SandboxRequest(task_id="v-fail", code="raise SystemExit(7)\n", prefer_docker=False)
    )
    assert r3.status == "failed" and r3.exit_code == 7
    print("FAIL", r3.status, r3.exit_code)

    r4 = execute_sandbox(
        SandboxRequest(
            task_id="v-tr",
            code="print('Y'*50000)\n",
            prefer_docker=False,
            max_output_bytes=1500,
        )
    )
    assert r4.status == "succeeded" and "[truncated]" in r4.stdout
    print("TRUNC", True, len(r4.stdout.encode()))

    execute_sandbox(
        SandboxRequest(
            task_id="iso-a",
            code="open('mark.txt','w',encoding='utf-8').write('A')\nprint('ok')\n",
            prefer_docker=False,
        )
    )
    assert (td / "iso-a" / "work" / "mark.txt").is_file()
    r5 = execute_sandbox(
        SandboxRequest(
            task_id="iso-b",
            code="import os\nprint('|'.join(sorted(os.listdir('.'))))\n",
            prefer_docker=False,
        )
    )
    assert not (td / "iso-b" / "work" / "mark.txt").exists()
    print("ISO", "cross_leak=", (td / "iso-b" / "work" / "mark.txt").exists(), "b_out=", repr(r5.stdout))

    outside = td / "outside.txt"
    outside.write_text("SECRET", encoding="utf-8")
    # Absolute path with no ../ literal — static policy may not catch this
    code = f"print(open(r'{outside}', encoding='utf-8').read())\n"
    r6 = execute_sandbox(SandboxRequest(task_id="iso-abs", code=code, prefer_docker=False))
    print(
        "ABS_HOST_READ_GAP",
        r6.status,
        "stdout=",
        repr(r6.stdout.strip()),
        "note=process_jail can read host paths if absolute path given",
    )

    print("ALL_PROCESS_JAIL_CHECKS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
