# ScholarFlow

ScholarFlow 是面向科研文献与开源实现的多 Agent 研究编排系统：对话驱动检索论文 / GitHub 仓库、证据门控、实验方案生成，并落盘结构化 artifacts。

## 演示（本地）

```powershell
# 仓库根目录
.\scripts\preflight_scholarflow.ps1
.\scripts\start_scholarflow_api.ps1   # http://127.0.0.1:8100
.\scripts\start_scholarflow_web.ps1   # http://127.0.0.1:5173
```

浏览器打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)。密钥放在根目录 `.env`（参考 `.env.example`）。

## 仓库结构

| 路径 | 说明 |
|------|------|
| `apps/scholarflow-web` | Vite + React 聊天 / 工作台 |
| `apps/scholarflow-api` | FastAPI：会话 SSE、研究任务、LangGraph |
| `backend/packages/harness/scholarflow` | 证据模型、矩阵、报告、RAG、沙箱 |
| `extensions/scholar_mcp` | arXiv / GitHub MCP 工具 |
| `scripts/` | 启动、preflight、校验脚本 |
| `docs/scholarflow-interview-map.md` | 面试口述地图 |

## 口述链路

1. **Chat SSE** — Web → API 会话流式事件  
2. **Tools → Graph / MCP** — Agent 工具 → 研究图并行拉论文/仓库 → 相关性过滤  
3. **Artifacts** — 审查通过后写入 paper/repo matrix、experiment plan、research report  

更多见 [docs/scholarflow-interview-map.md](docs/scholarflow-interview-map.md)。

## License

MIT（见 [LICENSE](LICENSE)）。
