# ScholarFlow Phase 3 — 真实 MCP 集成与产物持久化

## 目标

打通：`LangGraph 节点 → MCP Client (stdio) → scholar_mcp Server → 外部工具 → 状态 → Review → 9 类产物落盘 / API 下载`。

## 通信方式

| 组件 | 实现 |
|------|------|
| MCP Server | `extensions/scholar_mcp` · FastMCP · `python -m scholar_mcp.server` · transport=`stdio` |
| MCP Client | `apps/scholarflow-api/scholarflow_api/mcp/client.py` · 官方 `mcp` SDK `ClientSession` + `stdio_client` |
| 禁止 | 工作流 live 路径不得直接 `import` arXiv/GitHub 客户端函数绕过协议 |

## 已接通工具调用链

1. **search_academic_papers**  
   `paper_research_node` → `fetch_papers_via_mcp` → MCP `call_tool` → arXiv HTTP → 归一化 `source_url`/`identifier`/`fetched_at` → `state.papers`
2. **get_repository_overview**  
   `repository_analysis_node` → `fetch_repo_via_mcp` → MCP → GitHub API（可选 `GITHUB_TOKEN`）→ `default_branch`/`root_listing` → `state.repositories`
3. **validate_evidence_schema**  
   Review 本地 Pydantic + 可选 MCP 工具；API `/api/v1/mcp/tools` 可发现
4. **assemble_task_artifacts** / 本地 `build_task_artifacts`  
   live 优先 MCP assemble；失败则本地组装并记入 `degradation_events`（不得静默标为纯 live 成功）

## fixture vs live

| 模式 | 行为 | 标记 |
|------|------|------|
| `fixture`（默认） | 读 `docs/scholar-flow/samples/...` | `data_mode=fixture`，`data_source=fixture` |
| `live` | 真实 MCP；失败且未允许降级 → 任务 `failed` | `data_source=live_mcp` |
| `live` + `allow_fixture_fallback=true` | 显式降级到样本 | `effective_data_mode=mixed_degraded`，`partial_succeeded` |

**禁止**：live 失败后静默用 fixture 并标记为真实成功。

## 产物持久化

- 根目录：`SCHOLARFLOW_TASKS_DIR` 或 `apps/scholarflow-api/data/tasks/{task_id}/artifacts/`
- 重试策略：`overwrite_policy=replace`
- 路径校验：拒绝 `..` / 未知文件名
- API：`GET /api/v1/tasks/{id}/artifacts` · `GET /api/v1/tasks/{id}/artifacts/{filename}`
- 前端：产物列表 + 下载链接 + data_mode 选择

## 启动 / 停止 / 验证

```powershell
# API（建议用 backend venv，已含 mcp/langgraph）
cd apps/scholarflow-api
..\..\backend\.venv\Scripts\python.exe -m uvicorn scholarflow_api.app:app --reload --port 8100

# Web
cd apps/scholarflow-web
pnpm dev

# 离线测试
cd apps/scholarflow-api
..\..\backend\.venv\Scripts\python.exe -m pytest tests -q

# 含真实网络 MCP
$env:SCHOLARFLOW_LIVE_MCP="1"
..\..\backend\.venv\Scripts\python.exe -m pytest tests/test_mcp_protocol.py -q -k live
```

## 仍未完成（勿提前宣称）

- Cross-Encoder 重排
- 50 题 RAG 评测指标可复现
- MCP 证据不足自动补检闭环
- Sandbox 产品化
- ScholarFlow 全栈 Docker 演示稳定性（8GB）
