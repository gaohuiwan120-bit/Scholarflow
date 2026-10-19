# ScholarFlow API (Phase 1)

## 演示启动（面试用）

```powershell
# 仓库根目录
.\scripts\start_scholarflow_api.ps1
# 健康检查
# http://127.0.0.1:8100/health
# 前端另开：.\scripts\start_scholarflow_web.ps1 → http://127.0.0.1:5173
# 开演示前可跑：.\scripts\preflight_scholarflow.ps1
```

FastAPI entry for ScholarFlow chat + research orchestration. Uses
`scholarflow.scholar` (RAG / artifacts / sandbox) under `backend/packages/harness`.

## Run (from repo root, using backend venv)

```powershell
cd E:\AgentProject\scholarflow_project\apps\scholarflow-api
# Prefer scripts\start_scholarflow_api.ps1 (injects .env + PYTHONPATH).
# Manual PYTHONPATH must include scholar_mcp for in-process GitHub search:
$env:PYTHONPATH = "$PWD;$PWD\..\..\backend\packages\harness;$PWD\..\..\extensions\scholar_mcp"
# Prefer backend uv env which already has fastembed etc.
cd ..\..\backend
uv pip install fastapi uvicorn pydantic httpx pytest
uv run --directory ..\apps\scholarflow-api python -m scholarflow_api
```

Simpler path if `backend/.venv` is active:

```powershell
cd E:\AgentProject\scholarflow_project\backend
.\.venv\Scripts\Activate.ps1
cd ..\apps\scholarflow-api
$env:PYTHONPATH = "$((Get-Location).Path);$((Resolve-Path ..\..\backend\packages\harness).Path);$((Resolve-Path ..\..\extensions\scholar_mcp).Path)"
pip install fastapi "uvicorn[standard]" pydantic
python -m scholarflow_api
```

Health: http://127.0.0.1:8100/health

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness + harness/artifacts checks |
| POST | `/api/v1/tasks` | Create `rag_query` task |
| GET | `/api/v1/tasks/{id}` | Status / progress |
| GET | `/api/v1/tasks/{id}/result` | Final payload + artifact refs |

## Phase-2 boundary

`scholarflow_api/runtime/base.py` defines `TaskRuntime`. Phase 2 should add
`LangGraphResearchRuntime` without changing route shapes.
