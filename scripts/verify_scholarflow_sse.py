#!/usr/bin/env python3
"""Phase 8.3 live SSE verification against real DeepSeek streaming."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "scholarflow-api"
HARNESS = ROOT / "backend" / "packages" / "harness"
for p in (API, HARNESS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


def main() -> int:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scholarflow_api.chat.agent import ChatAgentRuntime
    from scholarflow_api.chat.router import create_conversation_router
    from scholarflow_api.chat.store import ConversationStore
    from scholarflow_api.llm.guards import redact_secrets
    from scholarflow_api.llm.settings import (
        get_llm_settings,
        load_root_env_into_process,
        reset_llm_settings_cache,
    )

    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    cfg = get_llm_settings()
    tested_at = datetime.now(timezone.utc).isoformat()
    print("=== ScholarFlow SSE Phase 8.3 live verify ===")
    print(f"llm_configured={cfg.configured} model={cfg.model}")
    if not cfg.configured:
        return 1

    evidence: dict = {"tested_at": tested_at, "model": cfg.model, "scenarios": []}

    with tempfile.TemporaryDirectory(prefix="sf-sse-") as tmp:
        store = ConversationStore(root=Path(tmp) / "c")
        agent = ChatAgentRuntime(store, max_tool_iters=6)
        app = FastAPI()
        app.include_router(create_conversation_router(store, agent))
        client = TestClient(app)

        def run_stream(title: str, content: str) -> dict:
            cid = client.post("/api/v1/conversations", json={"title": title}).json()[
                "conversation"
            ]["conversation_id"]
            with client.stream(
                "POST",
                f"/api/v1/conversations/{cid}/turns/stream",
                json={"content": content},
            ) as resp:
                ctype = resp.headers.get("content-type", "")
                body = "".join(resp.iter_text())
            events = []
            for block in body.split("\n\n"):
                for line in block.splitlines():
                    if line.startswith("data:"):
                        events.append(json.loads(line[5:].strip()))
            names = [e.get("event") for e in events]
            tokens = [e.get("text", "") for e in events if e.get("event") == "token"]
            return {
                "title": title,
                "content_type": ctype,
                "event_names": names,
                "token_count": len(tokens),
                "token_preview": redact_secrets("".join(tokens)[:200]),
                "tool_starts": [
                    e.get("tool_name") for e in events if e.get("event") == "tool_start"
                ],
                "tool_ends": [
                    {
                        "tool": e.get("tool_name"),
                        "status": e.get("status"),
                        "summary": redact_secrets(str(e.get("result_summary") or ""))[:180],
                    }
                    for e in events
                    if e.get("event") == "tool_end"
                ],
                "done": next((e for e in events if e.get("event") == "done"), None),
            }

        evidence["scenarios"].append(
            run_stream(
                "sse-direct",
                "Reply with exactly: STREAM OK. Do not use tools.",
            )
        )
        evidence["scenarios"].append(
            run_stream(
                "sse-papers",
                "Use search_papers for 1 paper about BM25. Then name the title briefly.",
            )
        )

    s0 = evidence["scenarios"][0]
    s1 = evidence["scenarios"][1]
    ok_tokens = s0["token_count"] >= 1
    ok_tools = "search_papers" in s1["tool_starts"] and s1["token_count"] >= 1
    # tokens after tool: check event order
    names = s1["event_names"]
    if "tool_end" in names and "token" in names:
        ok_order = names.index("tool_end") < max(
            i for i, n in enumerate(names) if n == "token"
        )
    else:
        ok_order = False
    status = "PASS" if ok_tokens and ok_tools and ok_order else "PARTIAL" if ok_tokens else "FAIL"

    report = ROOT / "docs" / "scholarflow-phase8-3.md"
    lines = [
        "# ScholarFlow Phase 8.3 — SSE 流式输出验收记录",
        "",
        f"- **status**: {status}",
        f"- **tested_at (UTC)**: `{tested_at}`",
        f"- **model**: `{cfg.model}`",
        f"- **stream path**: `ChatDeepSeek.stream` → `AIMessageChunk` 聚合 → SSE `token`",
        f"- **API**: `POST /api/v1/conversations/{{id}}/turns/stream`",
        f"- **direct token_count**: `{s0['token_count']}`",
        f"- **tool scenario tool_starts**: `{s1['tool_starts']}`",
        f"- **tool then later tokens**: `{ok_order}`",
        "",
        "## Live 证据（脱敏）",
        "",
        "```json",
        json.dumps(evidence, ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(f"wrote_report={report} status={status}")
    return 0 if status in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
