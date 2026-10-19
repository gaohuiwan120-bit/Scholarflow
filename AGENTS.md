# AGENTS.md — ScholarFlow

面向本仓库的编码代理说明。本仓库是 **ScholarFlow** 研究编排演示栈，不是完整的通用 Agent 产品外壳。

## 服务

| 服务 | 端口 | 目录 |
|------|------|------|
| API | 8100 | `apps/scholarflow-api` |
| Web | 5173 | `apps/scholarflow-web` |

启动：`scripts/start_scholarflow_api.ps1` + `scripts/start_scholarflow_web.ps1`。开演示前可跑 `scripts/preflight_scholarflow.ps1`。

## 依赖关系

- API / MCP 通过 `PYTHONPATH` 使用 `backend/packages/harness`（包名 `scholarflow`）与 `extensions/scholar_mcp`
- 业务导入形如 `from scholarflow.scholar...`
- 配置与密钥：根目录 `.env`（勿提交真实密钥）

## 约定

- 改功能请同步更新相关 `docs/scholarflow-*.md` 或 apps 内 README
- API 测试在 `apps/scholarflow-api/tests/`
- 不要重新引入已删除的通用 Gateway / Next.js / Docker 全栈外壳
