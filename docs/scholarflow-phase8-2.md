# ScholarFlow Phase 8.2 — Tool-calling Agent 验收记录

- **status**: PASS
- **tested_at (UTC)**: `2026-10-18T05:34:58.200861+00:00`
- **model**: `deepseek-chat`
- **base_url**: `https://api.deepseek.com`
- **invocation**: `ChatDeepSeek.bind_tools` + agent loop (`ChatAgentRuntime.run_turn`)
- **expected_tool_scenarios_met**: `3/3`
- **any_real_tool_calls**: `True`

## Live 场景摘要（脱敏）

```json
[
  {
    "status": "completed",
    "model": "deepseek-chat",
    "iterations": 1,
    "latency_ms": 3678.5,
    "error": null,
    "related_task_id": null,
    "tool_names": [],
    "tool_call_trace": [],
    "answer_preview": "READY",
    "scenario": "direct_no_tool",
    "expect_tool": null,
    "expect_met": true
  },
  {
    "status": "completed",
    "model": "deepseek-chat",
    "iterations": 2,
    "latency_ms": 7095.5,
    "error": null,
    "related_task_id": null,
    "tool_names": [
      "search_papers"
    ],
    "tool_call_trace": [
      {
        "tool_name": "search_papers",
        "status": "succeeded",
        "arguments": {
          "query": "retrieval-augmented generation",
          "max_results": 2
        },
        "error": null,
        "result_summary": "{\"ok\": true, \"tool\": \"search_papers\", \"papers\": [{\"evidence_id\": \"paper-2506.06962v3\", \"title\": \"AR-RAG: Autoregressive Retrieval Augmentation for Image Generation\", \"year\": 2025, \"source_url\": \"https://arxiv.org/abs/2506.06962v3\", \"research_problem\": \"We introduce Autoregressive Retrieval Augmentat"
      }
    ],
    "answer_preview": "Here are 2 arXiv papers on retrieval-augmented generation:\n\n1. **AR-RAG: Autoregressive Retrieval Augmentation for Image Generation** (2025)\n   - https://arxiv.org/abs/2506.06962v3\n   - Introduces autoregressive, patch-level k-nearest-neighbor retrieval for image generation, rather than a single static retrieval before generation.\n\n2. **EVOR: Evolving Retrieval for Code Generation** (2024)\n   - https://arxiv.org/abs/2402.12317v2\n   - Addresses retrieval-augmented code generation (RACG), noting t",
    "scenario": "search_papers",
    "expect_tool": "search_papers",
    "expect_met": true
  },
  {
    "status": "completed",
    "model": "deepseek-chat",
    "iterations": 2,
    "latency_ms": 6516.7,
    "error": null,
    "related_task_id": null,
    "tool_names": [
      "scholar_rag_query"
    ],
    "tool_call_trace": [
      {
        "tool_name": "scholar_rag_query",
        "status": "succeeded",
        "arguments": {
          "question": "hybrid RAG and BM25 retrieval",
          "top_k": 5
        },
        "error": null,
        "result_summary": "{\"ok\": true, \"tool\": \"scholar_rag_query\", \"answer\": \"基于 ScholarFlow 科研证据库检索（backend=fastembed, embed=BAAI/bge-small-en-v1.5, sparse=BM25, fusion=RRF, rerank=hybrid-score）：\\n\\n- [paper] Blended RAG: Improving RAG (Retriever-Augmented Generation) Accuracy with Semantic Search and Hybrid Query-Based Re"
      }
    ],
    "answer_preview": "The index is **not** empty — it returned 5 evidence chunks. Here's what the local corpus says about hybrid RAG / BM25:\n\n**Retrieval setup (from the tool's own metadata):** the index uses `fastembed` with `BAAI/bge-small-en-v1.5` dense embeddings, **BM25** sparse retrieval, **RRF** (Reciprocal Rank Fusion) for combining them, and hybrid-score reranking. So BM25 is a first-class component of the local hybrid pipeline, not just a topic in the corpus.\n\n**Substantive findings:**\n\n1. **Blended RAG** (",
    "scenario": "scholar_rag_query",
    "expect_tool": "scholar_rag_query",
    "expect_met": true
  },
  {
    "status": "completed",
    "model": "deepseek-chat",
    "iterations": 2,
    "latency_ms": 2816.5,
    "error": null,
    "related_task_id": "sf-0a413e86574c",
    "tool_names": [
      "run_research_workflow"
    ],
    "tool_call_trace": [
      {
        "tool_name": "run_research_workflow",
        "status": "succeeded",
        "arguments": {
          "question": "hybrid RAG evaluation plan",
          "data_mode": "fixture",
          "kind": "research_orchestration"
        },
        "error": null,
        "result_summary": "{\"ok\": true, \"tool\": \"run_research_workflow\", \"task_id\": \"sf-0a413e86574c\", \"overall_status\": \"succeeded\", \"workflow_mode\": \"research_orchestration\", \"data_mode\": \"fixture\", \"effective_data_mode\": \"fixture\", \"paper_count\": 3, \"repo_count\": 1, \"artifacts\": [\"evidence_review.json\", \"experiment_plan.md"
      }
    ],
    "answer_preview": "The workflow completed successfully.\n\n- **task_id:** `sf-0a413e86574c`\n- **overall_status:** `succeeded`\n- **workflow_mode:** `research_orchestration` (data_mode: `fixture`)\n- **error:** none\n- **duration:** 94 ms\n\n**Coverage:** 3 papers and 1 repository were processed.\n\n**Artifacts produced:**\n- `research_report.md` — main write-up\n- `research_plan.json` — plan for the hybrid RAG evaluation\n- `experiment_plan.md` — experiment design\n- `evidence_review.json` — synthesized evidence review\n- `pape",
    "scenario": "run_research_workflow",
    "expect_tool": "run_research_workflow",
    "expect_met": true
  },
  {
    "status": "completed",
    "model": "deepseek-chat",
    "iterations": 2,
    "latency_ms": 8382.3,
    "error": null,
    "related_task_id": null,
    "tool_names": [
      "search_papers",
      "scholar_rag_query"
    ],
    "tool_call_trace": [
      {
        "tool_name": "search_papers",
        "status": "succeeded",
        "arguments": {
          "query": "graph neural networks survey",
          "max_results": 5
        },
        "error": null,
        "result_summary": "{\"ok\": true, \"tool\": \"search_papers\", \"papers\": [{\"evidence_id\": \"paper-2306.14753v1\", \"title\": \"The Deep Arbitrary Polynomial Chaos Neural Network or how Deep Artificial Neural Networks could benefit from Data-Driven Homogeneous Chaos Theory\", \"year\": 2023, \"source_url\": \"https://arxiv.org/abs/2306"
      },
      {
        "tool_name": "scholar_rag_query",
        "status": "succeeded",
        "arguments": {
          "question": "What do the indexed artifacts say about graph neural networks (GNN) methods, architectures, and applications?",
          "top_k": 5
        },
        "error": null,
        "result_summary": "{\"ok\": true, \"tool\": \"scholar_rag_query\", \"answer\": \"证据库未检索到足够支撑该问题的已验证证据。已标记 need_mcp_fallback；若补检仍不足将明确拒答。\\n\\n（不足原因：topical_overlap=0.1429 shared_content_tokens=1）\", \"refused\": false, \"evidence\": [], \"artifacts_dir\": \"E:\\\\AgentProject\\\\scholarflow_project\\\\docs\\\\scholar-flow\\\\samples\\\\rag-test-001\", "
      }
    ],
    "answer_preview": "## Summary\n\n**arXiv search (`search_papers`, query \"graph neural networks survey\")** — returned 5 results, but the relevance is weak; only one is genuinely about GNNs:\n\n| Evidence ID | Title | Year | Relevance |\n|---|---|---|---|\n| `paper-2211.12792v2` | MECCH: Metapath Context Convolution-based Heterogeneous Graph Neural Networks — [arxiv.org/abs/2211.12792v2](https://arxiv.org/abs/2211.12792v2) | 2022 | **Directly relevant.** Heterogeneous GNNs (HGNNs) for representation learning on multi-type",
    "scenario": "multi_tool_hint",
    "expect_tool": null,
    "expect_met": true
  },
  {
    "scenario": "isolation",
    "a_preview": "ALPHA42",
    "b_preview": "BETA99",
    "a_tools": [],
    "b_tools": []
  }
]
```

## 说明

- 工具选择来自模型返回的 `tool_calls`，无关键词 if/else 路由。
- Mock 测试见 `tests/test_chat_agent_mock.py`（与 Live 分开）。
- 幂等性：重复 POST `/turns` 会重复执行并落盘（8.2 未做 client request_id）。
- 未实现 SSE / Chat UI。

## API

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/conversations/{id}/turns` | 同步 Agent 回合（保存 user → bind_tools 循环 → 保存 assistant+trace） |

保留 8.1 的 CRUD / 纯落盘 `POST .../messages`。

## 工具（复用已有能力）

| Tool | 底层 |
|------|------|
| `scholar_rag_query` | `scholarflow.scholar.rag.rag_answer` |
| `search_papers` | `fetch_papers_via_mcp` → arXiv |
| `run_research_workflow` | `graph.workflow.run_research_workflow`（默认 fixture） |

## 测试结果（分开统计）

| 类型 | 套件 | 结果 |
|------|------|------|
| Mock/单元 | `test_chat_agent_mock.py` + chat store/api | 含在回归内 |
| 回归（非 live） | `pytest tests/ -m "not live_llm"` | **62 passed**, 1 skipped, 5 deselected |
| Live | `test_chat_agent_live.py` + `verify_scholarflow_agent.py` | **4 passed** + 脚本 **PASS**（3/3 期望工具命中；多工具同轮；隔离 ALPHA/BETA） |

## 修改文件

- `scholarflow_api/chat/agent.py`（新建）
- `scholarflow_api/chat/tools.py`（新建）
- `scholarflow_api/chat/router.py` / `schemas.py` / `__init__.py`
- `scholarflow_api/app.py`
- `tests/test_chat_agent_mock.py` / `test_chat_agent_live.py`
- `scripts/verify_scholarflow_agent.py`
- `docs/scholarflow-phase8-2.md` / `docs/scholarflow-requirements-matrix.md`（§J）

未改：API-Key、评测冻结数据、ScholarFlow Docker、Chat UI、SSE。

## 已知限制

1. **非幂等**：同一内容重复 `POST /turns` 会再次调用模型/工具并追加消息。
2. 历史回放不重建中间 `ToolMessage`（仅 user/assistant 文本）；多轮追问依赖最终 assistant 摘要。
3. `run_research_workflow` 默认 `data_mode=fixture`（快）；live MCP 由模型参数可选。
4. 单轮内多工具并行来自一次 AIMessage 的多个 `tool_calls`；跨轮连续工具靠迭代循环。
5. 无 SSE（8.3）、无 Chat UI（8.5）。

## deepseek-chat 工具兼容性结论

**已验证**：`deepseek-chat` 经 `ChatDeepSeek.bind_tools` 可返回原生 `tool_calls`，并在工具结果回灌后继续生成最终回答。无需切换模型，无需硬编码路由。

## 8.3 前置条件

1. Agent 同步回合稳定（已满足）。
2. `tool_call_trace` 已落盘（已满足）。
3. 下一阶段：将 `run_turn` 改为真正 SSE 事件流（token / tool_start / tool_end），禁止伪流式。

