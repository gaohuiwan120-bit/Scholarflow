# ScholarFlow Web (Phase 1)

## 演示启动（面试用）

```powershell
# 先起 API，再起 Web（仓库根目录）
.\scripts\start_scholarflow_api.ps1
.\scripts\start_scholarflow_web.ps1
# 浏览器打开 http://127.0.0.1:5173
```

Independent React + Vite workbench for the ScholarFlow demo.

## Run

```powershell
cd E:\AgentProject\scholarflow_project\apps\scholarflow-web
npm install
npm run dev
```

Open http://127.0.0.1:5173/

Vite proxies `/api` and `/health` to FastAPI on port 8100.
