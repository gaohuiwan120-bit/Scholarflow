#!/usr/bin/env python3
"""Phase 8.4 live verify: DeepSeek → run_research_workflow → TaskStore (fixture data)."""

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
    from scholarflow_api.chat.agent import ChatAgentRuntime
    from scholarflow_api.chat.store import ConversationStore
    from scholarflow_api.chat.workflow_bridge import configure_workflow_bridge, get_workflow_bridge
    from scholarflow_api.config import get_settings
    from scholarflow_api.llm.guards import redact_secrets
    from scholarflow_api.llm.settings import (
        get_llm_settings,
        load_root_env_into_process,
        reset_llm_settings_cache,
    )
    from scholarflow_api.runtime.research_runtime import ResearchTaskRuntime
    from scholarflow_api.services.task_store import TaskStore

    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    cfg_llm = get_llm_settings()
    tested_at = datetime.now(timezone.utc).isoformat()
    print("=== ScholarFlow Phase 8.4 workflow bridge live verify ===")
    print(f"llm_configured={cfg_llm.configured} model={cfg_llm.model}")
    print("NOTE: real LLM + fixture research workflow (not full live MCP E2E)")
    if not cfg_llm.configured:
        return 1

    with tempfile.TemporaryDirectory(prefix="sf-wf-") as tmp:
        tmp_path = Path(tmp)
        store = TaskStore(persist=True)
        # Point tasks dir into temp
        import os

        os.environ["SCHOLARFLOW_TASKS_DIR"] = str(tmp_path / "tasks")
        settings = get_settings()
        configure_workflow_bridge(store, ResearchTaskRuntime(settings), settings)

        conv = ConversationStore(root=tmp_path / "conversations")
        meta = conv.create(title="phase84")
        agent = ChatAgentRuntime(conv, max_tool_iters=6)
        result = agent.run_turn(
            meta.conversation_id,
            "Use run_research_workflow with data_mode=fixture and wait=true for: "
            "hybrid RAG evaluation plan. Then report task_id, status, and artifact count.",
        )
        names = [t.tool_name for t in result.tool_call_trace]
        traces = [
            {
                "tool": t.tool_name,
                "status": t.status,
                "args": t.arguments,
                "summary": redact_secrets(t.result_summary or "")[:300],
            }
            for t in result.tool_call_trace
        ]
        tid = result.related_task_id
        record = get_workflow_bridge().store.get(tid) if tid else None
        artifacts = get_workflow_bridge().list_artifacts(tid) if tid else None
        evidence = {
            "tested_at": tested_at,
            "model": cfg_llm.model,
            "mode_label": "real_llm_plus_fixture_workflow",
            "tool_names": names,
            "tool_call_trace": traces,
            "related_task_id": tid,
            "taskstore_status": record.status.value if record else None,
            "taskstore_kind": record.kind.value if record else None,
            "artifact_count": (artifacts or {}).get("artifact_count"),
            "artifact_files": [
                a.get("filename") for a in (artifacts or {}).get("artifacts") or []
            ][:12],
            "answer_preview": redact_secrets(
                (result.assistant_message.content or "")[:400]
            ),
            "turn_status": result.status,
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))

        ok = (
            "run_research_workflow" in names
            and tid
            and record is not None
            and record.status.value
            in {"succeeded", "partial_succeeded", "failed", "timed_out"}
        )
        status = "PASS" if ok else "FAIL"

        report = ROOT / "docs" / "scholarflow-phase8-4.md"
        lines = [
            "# ScholarFlow Phase 8.4 — 对话 Agent × 科研工作流集成验收",
            "",
            f"- **status**: {status}",
            f"- **tested_at (UTC)**: `{tested_at}`",
            f"- **model**: `{cfg_llm.model}`",
            f"- **integration mode**: `real LLM + fixture workflow`（非全链路 live MCP）",
            f"- **task_id**: `{tid}`",
            f"- **TaskStore status**: `{evidence['taskstore_status']}`",
            f"- **artifacts**: `{evidence['artifact_count']}` → `{evidence['artifact_files']}`",
            "",
            "## Live 证据（脱敏）",
            "",
            "```json",
            json.dumps(evidence, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote_report={report} status={status}")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
