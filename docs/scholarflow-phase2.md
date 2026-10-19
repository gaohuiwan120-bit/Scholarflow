# ScholarFlow Phase 2 — LangGraph 多智能体科研工作流

## 架构

```
orchestrator
    ├─► paper_research  ──┐
    └─► repository_analysis ──┼─► join_gate ─► experiment_design ─► review ─► assemble
                              │
         (paper-only / repo-only 单流路径 → review_direct → review → assemble)
```

- 图代码：`apps/scholarflow-api/scholarflow_api/graph/`
- Runtime：`ResearchTaskRuntime`（`research_graph_v1`）实现 `TaskRuntime`
- 仍保留：`RagTaskRuntime`（`rag_v1`）

## 四类工作流入口

| kind | 路径 |
|------|------|
| `research_orchestration` | 论文∥仓库 → 实验 → 审查 → 聚合 |
| `paper_research` | 仅论文 → review_direct → 审查 → 聚合 |
| `repository_analysis` | 仅仓库 → review_direct → 审查 → 聚合 |
| `experiment_design` | 先并行取证再实验方案 |

## 数据模式

- **fixture（默认）**：读取 `docs/scholar-flow/samples/rag-test-001/`，确定性、可离线。
- **live**：尝试 `extensions/scholar_mcp` 的 arXiv/GitHub 客户端；失败则回退 fixture，并在 subtask `data_source` 标明。

**不假装：** LLM 调用、Cross-Encoder、自动 MCP 补检闭环、Sandbox。

## 并行验证

测试 `test_paper_and_repo_parallel_overlap`：`simulate_work_seconds=0.45`，断言 paper/repo 的 `[started_at, ended_at]` 区间相交。

## 运行

```powershell
powershell -File scripts\start_scholarflow_api.ps1
powershell -File scripts\start_scholarflow_web.ps1
```

浏览器 http://127.0.0.1:5173/ 选择「综合科研编排」。

## 测试

```powershell
cd apps\scholarflow-api
$env:PYTHONPATH="$PWD;$PWD\..\..\backend\packages\harness"
..\..\backend\.venv\Scripts\python.exe -m pytest tests/ -q
```

预期：13 passed。
