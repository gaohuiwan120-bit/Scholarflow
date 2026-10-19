# ScholarFlow 面试口述地图

本仓库只保留 ScholarFlow 演示链路（API + Web + MCP + harness）。

## 目录

| 路径 | 作用 |
|------|------|
| `apps/scholarflow-web` | Vite 聊天 + 工作台 UI（:5173） |
| `apps/scholarflow-api` | FastAPI：会话、SSE、研究任务 |
| `backend/packages/harness/scholarflow/scholar` | 证据模型、矩阵、报告、RAG、沙箱 |
| `extensions/scholar_mcp` | arXiv / GitHub MCP 工具 |
| `scripts/start_scholarflow_*.ps1` | 注入 `.env` + PYTHONPATH 后启动 |
| `.env` | DeepSeek / GitHub 等密钥（勿提交） |

## 三条口述链路

1. **Chat SSE**  
   浏览器 → `scholarflow-web` → 代理到 API → 会话存储 + 流式事件回写 UI。

2. **Tools → Graph / MCP**  
   Agent 调工具 → LangGraph 研究图（论文 / 仓库并行）→ `scholar_mcp` 拉 arXiv / GitHub → 相关性门控过滤噪声。

3. **Artifacts**  
   通过证据审查后落盘：`paper_matrix`、`repository_matrix`、`experiment_plan`、`research_report` 等，可在工作台查看。

## 一分钟启动

```powershell
.\scripts\preflight_scholarflow.ps1
.\scripts\start_scholarflow_api.ps1
.\scripts\start_scholarflow_web.ps1
# 打开 http://127.0.0.1:5173
```
