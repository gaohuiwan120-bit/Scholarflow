# ScholarFlow Phase 1 — 独立前端 + FastAPI 最小闭环

## 架构

```
apps/scholarflow-web (Vite:5173)
        │  /api /health proxy
        ▼
apps/scholarflow-api (FastAPI:8100)
        │  TaskRuntime (rag_v1)
        ▼
scholarflow.scholar.rag  (index_artifacts_dir / rag_answer)
        │
docs/scholar-flow/samples/rag-test-001 + evaluation/rag_index
```

**明确未实现（勿对外声称）：** LangGraph 四类工作流、并行 Sub-Agent、Cross-Encoder、Sandbox 产品层。

## 启动

```powershell
# Terminal A — API
powershell -File E:\AgentProject\scholarflow_project\scripts\start_scholarflow_api.ps1

# Terminal B — Web
powershell -File E:\AgentProject\scholarflow_project\scripts\start_scholarflow_web.ps1
```

## 验证

```powershell
curl.exe http://127.0.0.1:8100/health
# 浏览器打开 http://127.0.0.1:5173/ 提交问题
# 或:
curl.exe -X POST http://127.0.0.1:8100/api/v1/tasks -H "Content-Type: application/json" -d "{\"kind\":\"rag_query\",\"question\":\"Blended RAG hybrid dense sparse vs Naive RAG\",\"top_k\":5,\"ensure_index\":true}"
```

## 停止

结束对应 PowerShell / Ctrl+C。不需要 docker compose。

## 原有 RAG CLI（仍可用）

```powershell
cd E:\AgentProject\scholarflow_project\backend
uv run python ../evaluation/run_rag_demo.py
```
