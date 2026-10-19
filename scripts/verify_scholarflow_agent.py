#!/usr/bin/env python3
"""Phase 8.2 live agent verification — real DeepSeek tool-calling.

Writes redacted evidence to docs/scholarflow-phase8-2.md.
Never prints API keys.
"""

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


def _summarize_result(result) -> dict:
    from scholarflow_api.llm.guards import redact_secrets

    traces = []
    for t in result.tool_call_trace:
        traces.append(
            {
                "tool_name": t.tool_name,
                "status": t.status,
                "arguments": t.arguments,
                "error": redact_secrets(t.error) if t.error else None,
                "result_summary": redact_secrets(t.result_summary or "")[:300],
            }
        )
    answer = ""
    if result.assistant_message:
        answer = redact_secrets(result.assistant_message.content or "")[:500]
    return {
        "status": result.status,
        "model": result.model,
        "iterations": result.iterations,
        "latency_ms": result.latency_ms,
        "error": redact_secrets(result.error) if result.error else None,
        "related_task_id": result.related_task_id,
        "tool_names": [t["tool_name"] for t in traces],
        "tool_call_trace": traces,
        "answer_preview": answer,
    }


def main() -> int:
    from scholarflow_api.chat.agent import ChatAgentRuntime
    from scholarflow_api.chat.store import ConversationStore
    from scholarflow_api.llm.settings import (
        get_llm_settings,
        load_root_env_into_process,
        reset_llm_settings_cache,
    )

    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    cfg = get_llm_settings()
    tested_at = datetime.now(timezone.utc).isoformat()
    print("=== ScholarFlow Agent Phase 8.2 live verify ===")
    print(f"llm_configured={cfg.configured} model={cfg.model} base_url={cfg.base_url}")
    if not cfg.configured:
        print("FAIL: DEEPSEEK_API_KEY not configured")
        return 1

    scenarios: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="sf-agent-") as tmp:
        store = ConversationStore(root=Path(tmp) / "conversations")
        agent = ChatAgentRuntime(store, max_tool_iters=6)

        cases = [
            (
                "direct_no_tool",
                "Reply with exactly the word READY and nothing else. Do not call tools.",
                None,  # expected tool optional
            ),
            (
                "search_papers",
                "Use the search_papers tool to find 2 arXiv papers about retrieval-augmented generation. "
                "Then briefly list their titles and source_url.",
                "search_papers",
            ),
            (
                "scholar_rag_query",
                "Use scholar_rag_query to answer: what does the local corpus say about hybrid RAG or BM25? "
                "If the index is empty, say so based on the tool result.",
                "scholar_rag_query",
            ),
            (
                "run_research_workflow",
                "Run a full ScholarFlow research task using run_research_workflow with "
                "data_mode=fixture on the question: hybrid RAG evaluation plan. "
                "Return the task_id and overall_status from the tool.",
                "run_research_workflow",
            ),
            (
                "multi_tool_hint",
                "First use search_papers for 'graph neural networks survey', then if useful "
                "also call scholar_rag_query about GNN. Summarize with tool evidence.",
                None,
            ),
        ]

        ok_count = 0
        for name, prompt, expect_tool in cases:
            print(f"--- scenario={name} ---")
            meta = store.create(title=name)
            result = agent.run_turn(meta.conversation_id, prompt)
            summary = _summarize_result(result)
            summary["scenario"] = name
            summary["expect_tool"] = expect_tool
            hit = True
            if expect_tool:
                hit = expect_tool in summary["tool_names"]
                summary["expect_met"] = hit
            else:
                summary["expect_met"] = True
            scenarios.append(summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if summary["status"] in {"completed", "max_iterations"} and summary["expect_met"]:
                ok_count += 1

        # Isolation mini-check
        a = store.create(title="iso-a")
        b = store.create(title="iso-b")
        agent.run_turn(a.conversation_id, "Secret codeword for this chat is ALPHA42. Reply OK.")
        agent.run_turn(b.conversation_id, "Secret codeword for this chat is BETA99. Reply OK.")
        ra = agent.run_turn(a.conversation_id, "What is the secret codeword? Answer with the codeword only.")
        rb = agent.run_turn(b.conversation_id, "What is the secret codeword? Answer with the codeword only.")
        iso = {
            "scenario": "isolation",
            "a_preview": (ra.assistant_message.content or "")[:120],
            "b_preview": (rb.assistant_message.content or "")[:120],
            "a_tools": [t.tool_name for t in ra.tool_call_trace],
            "b_tools": [t.tool_name for t in rb.tool_call_trace],
        }
        scenarios.append(iso)
        print(json.dumps(iso, ensure_ascii=False, indent=2))

    # Compatibility probe: did any scenario produce real tool calls?
    any_tools = any(s.get("tool_names") for s in scenarios if isinstance(s.get("tool_names"), list))
    expected_hits = [s for s in scenarios if s.get("expect_tool")]
    met = sum(1 for s in expected_hits if s.get("expect_met"))
    status = "PASS" if met >= 2 and any_tools else "PARTIAL" if any_tools else "FAIL"

    report = ROOT / "docs" / "scholarflow-phase8-2.md"
    lines = [
        "# ScholarFlow Phase 8.2 — Tool-calling Agent 验收记录",
        "",
        f"- **status**: {status}",
        f"- **tested_at (UTC)**: `{tested_at}`",
        f"- **model**: `{cfg.model}`",
        f"- **base_url**: `{cfg.base_url}`",
        f"- **invocation**: `ChatDeepSeek.bind_tools` + agent loop (`ChatAgentRuntime.run_turn`)",
        f"- **expected_tool_scenarios_met**: `{met}/{len(expected_hits)}`",
        f"- **any_real_tool_calls**: `{any_tools}`",
        "",
        "## Live 场景摘要（脱敏）",
        "",
        "```json",
        json.dumps(scenarios, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 说明",
        "",
        "- 工具选择来自模型返回的 `tool_calls`，无关键词 if/else 路由。",
        "- Mock 测试见 `tests/test_chat_agent_mock.py`（与 Live 分开）。",
        "- 幂等性：重复 POST `/turns` 会重复执行并落盘（8.2 未做 client request_id）。",
        "- 未实现 SSE / Chat UI。",
        "",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote_report={report} status={status}")
    return 0 if status in {"PASS", "PARTIAL"} and any_tools else 1


if __name__ == "__main__":
    raise SystemExit(main())
