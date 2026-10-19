#!/usr/bin/env python3
"""Phase 8.5 E2E: exercise the same APIs the Chat UI uses (real SSE + TaskStore).

Does not open a GUI browser; pairs with manual/browser check of :5173.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8100"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            ctype = resp.headers.get("content-type", "")
            if "json" in ctype:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def stream_turn(cid: str, content: str) -> list[dict]:
    data = json.dumps({"content": content}).encode("utf-8")
    r = urllib.request.Request(
        f"{BASE}/api/v1/conversations/{cid}/turns/stream",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    events: list[dict] = []
    with urllib.request.urlopen(r, timeout=180) as resp:
        assert "text/event-stream" in (resp.headers.get("content-type") or "")
        buf = ""
        while True:
            chunk = resp.read(256)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                data_lines = [
                    ln[5:].strip() for ln in block.splitlines() if ln.startswith("data:")
                ]
                if data_lines:
                    events.append(json.loads("\n".join(data_lines)))
    return events


def main() -> int:
    tested_at = datetime.now(timezone.utc).isoformat()
    print("=== ScholarFlow Chat UI API E2E (Phase 8.5) ===")
    code, health = req("GET", "/health")
    print("health", code, health if isinstance(health, dict) else health[:200])
    if code != 200:
        return 1

    code, created = req("POST", "/api/v1/conversations", {"title": "ui-e2e"})
    assert code == 200 and isinstance(created, dict)
    cid = created["conversation"]["conversation_id"]
    print("created", cid)

    events = stream_turn(
        cid,
        "Reply with exactly: UI E2E OK. Do not use tools.",
    )
    names = [e.get("event") for e in events]
    print("sse_events", names)
    assert names[0] == "turn_start"
    assert "token" in names
    assert names[-1] == "done"
    tokens = "".join(e.get("text", "") for e in events if e.get("event") == "token")
    print("token_preview", tokens[:80])

    code, hist = req("GET", f"/api/v1/conversations/{cid}/messages")
    assert code == 200 and isinstance(hist, dict)
    assert hist["total"] >= 2
    print("messages", hist["total"])

    code, listed = req("GET", "/api/v1/conversations")
    assert code == 200 and isinstance(listed, dict)
    assert any(c["conversation_id"] == cid for c in listed["conversations"])

    # Tool path smoke (fixture workflow) — same as Chat task card path
    events2 = stream_turn(
        cid,
        "Use run_research_workflow with data_mode=fixture wait=true on: UI chat task card. "
        "Then report task_id.",
    )
    names2 = [e.get("event") for e in events2]
    print("sse2", names2[:12], "...", names2[-3:])
    assert "tool_start" in names2
    done = next(e for e in events2 if e.get("event") == "done")
    tid = done.get("related_task_id")
    print("related_task_id", tid)
    assert tid
    code, st = req("GET", f"/api/v1/tasks/{tid}")
    assert code == 200
    code, arts = req("GET", f"/api/v1/tasks/{tid}/artifacts")
    print("artifacts_status", code)

    evidence = {
        "tested_at": tested_at,
        "conversation_id": cid,
        "direct_sse_events": names,
        "token_preview": tokens[:120],
        "tool_sse_has_tool_start": "tool_start" in names2,
        "related_task_id": tid,
        "task_http_status": code,
        "message": "API path used by Chat UI verified against live backend",
    }
    # Keep full phase doc; only rewrite a sidecar JSON for re-runs.
    out = ROOT / "docs" / "scholarflow-phase8-5-api-e2e.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)
    print("API E2E PASS — see docs/scholarflow-phase8-5.md for full acceptance notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
