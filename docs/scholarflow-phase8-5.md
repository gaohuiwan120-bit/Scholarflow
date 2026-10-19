# ScholarFlow Phase 8.5 — 对话式科研 Agent 前端验收

- **status**: PASS
- **tested_at (UTC)**: `2026-10-18`（API E2E 详见下方 JSON；浏览器 E2E 同日）
- **前端**: `apps/scholarflow-web`（Vite + React + TypeScript，未换栈）
- **后端**: 未改 Agent / API-Key；仅消费阶段 8.1–8.4 已验收接口
- **未进入**: 8.6

## 1. 修改文件清单

| 路径 | 说明 |
|------|------|
| `apps/scholarflow-web/src/App.tsx` | 默认 Tab=`chat`；保留「科研工作台」；localStorage 恢复 Tab |
| `apps/scholarflow-web/src/ChatPage.tsx` | 新建：会话栏、消息区、SSE 发送/停止、工具态、任务卡片 |
| `apps/scholarflow-web/src/Workbench.tsx` | 原工作台抽离为独立入口（功能保留） |
| `apps/scholarflow-web/src/api.ts` | 会话 REST + `fetch` SSE 流式解析 + 任务/产物 API |
| `apps/scholarflow-web/src/markdown.tsx` | Markdown / 代码块 / 链接渲染 |
| `apps/scholarflow-web/src/styles.css` | Chat 布局与消息/工具/任务卡片样式 |
| `scripts/verify_scholarflow_chat_ui.py` | 与 Chat 同路径的真实 API+SSE E2E |
| `docs/scholarflow-phase8-5.md` | 本验收文档 |
| `docs/scholarflow-requirements-matrix.md` | §J 8.5 状态更新 |

## 2. 新页面结构

```
App
├── Header: ScholarFlow 品牌 + Chat | 科研工作台 + /health
├── Chat（默认）
│   ├── 左侧：新建会话 + 历史列表（切换 / 刷新恢复 activeConversationId）
│   ├── 中央：欢迎 / 消息气泡（user | assistant）+ Markdown
│   │         工具执行条（真实 SSE tool_*，不混入正文）
│   │         科研任务卡片（task_id / status / data_mode / 产物下载）
│   └── 底部：多行输入 · Enter 发送 · Shift+Enter 换行 · 停止生成
└── 科研工作台（独立 Tab）：原任务提交 / 轮询 / 产物下载
```

视觉：科研产品风（绿灰暖底 + IBM Plex），非 ScholarFlow 品牌/布局照搬。

## 3. 实际接入的 API（以后端为准）

| 能力 | 方法 | 路径 |
|------|------|------|
| 健康检查 | GET | `/health` |
| 会话列表 | GET | `/api/v1/conversations` |
| 创建会话 | POST | `/api/v1/conversations` |
| 会话详情 | GET | `/api/v1/conversations/{id}` |
| 消息历史 | GET | `/api/v1/conversations/{id}/messages` |
| SSE 对话 | POST | `/api/v1/conversations/{id}/turns/stream`（`Accept: text/event-stream`，body `{content}`） |
| 取消 turn | POST | `/api/v1/conversations/{id}/turns/{turn_id}/cancel` |
| 任务状态 | GET | `/api/v1/tasks/{task_id}` |
| 任务结果 | GET | `/api/v1/tasks/{task_id}/result` |
| 产物清单 | GET | `/api/v1/tasks/{task_id}/artifacts` |
| 产物下载 | GET | `/api/v1/tasks/{task_id}/artifacts/{filename}` |
| 工作台提交 | POST | `/api/v1/tasks`（Workbench 保留） |

SSE 使用 **`fetch` + `ReadableStream`**，不用 `EventSource`（POST body 与现有协议一致）。

解析事件：`turn_start` · `token` · `tool_start` · `tool_end` · `workflow_progress` · `error` · `done`。

## 4. 真实 SSE 事件验证

### API 路径（`scripts/verify_scholarflow_chat_ui.py`）

```json
{
  "tested_at": "2026-10-18T06:05:10.500506+00:00",
  "conversation_id": "cv-2335ab7f87bc",
  "direct_sse_events": [
    "turn_start",
    "token",
    "token",
    "token",
    "token",
    "token",
    "done"
  ],
  "token_preview": "UI E2E OK",
  "tool_sse_has_tool_start": true,
  "related_task_id": "sf-31b7110aa1a8",
  "task_http_status": 200,
  "message": "API path used by Chat UI verified against live backend"
}
```

直答 turn：`turn_start` → 多段 `token` → `done`（非一次性假打字）。  
工具 turn：`tool_start` → `tool_end` → `token*` → `done`，且 `related_task_id` 可查 TaskStore。

### 浏览器端到端（真实页面，非组件 Mock）

- 入口：`http://127.0.0.1:5173/`（Vite），代理至 `127.0.0.1:8100`
- `/health`：`llm_configured=true`，`llm_provider=deepseek`，`llm_model=deepseek-chat`
- 发送：「你好，用一句话介绍 ScholarFlow。」
- UI：出现「停止生成」→ 流式完成后 assistant 气泡展示真实 DeepSeek 回答
- 会话列表条目更新为该问题标题，消息数 `2 条`
- 历史均来自后端持久化 / 当前流，无预置假聊天记录

## 5. 真实任务与产物展示验证

- API E2E 工具路径产出 `related_task_id=sf-31b7110aa1a8`，`GET .../artifacts` → **200**
- Chat 内任务卡片字段：真实 `task_id`、状态、`data_mode`/`effective_data_mode`（fixture ≠ live）、产物下载链、失败信息
- 仅展示后端确认存在的产物；running 不标成功；fixture 不标为外部 live 检索

## 6. 测试结果

| 类型 | 结果 |
|------|------|
| Mock / 组件冒充历史 | **未使用**；消息仅来自 REST 历史或真实 SSE |
| API E2E（同 Chat 调用路径） | **PASS**（`verify_scholarflow_chat_ui.py`） |
| 浏览器 E2E | **PASS**：默认 Chat、新建/切换会话、真实 token 流、停止按钮可见、工作台 Tab 可切换 |
| 后端回归 `pytest -m "not live_llm"` | **PASS**：**81 passed**, 1 skipped, 8 deselected |

验收项对照：

1. 首次打开默认 Chat  
2. 新建会话  
3. 加载历史会话  
4. 多轮对话（API + UI）  
5. 真实 token 流式  
6. 工具调用状态（API SSE `tool_start`/`tool_end`；UI 映射脱敏摘要）  
7. 多工具事件顺序（按 SSE 到达顺序渲染，不混入正文）  
8. 科研任务状态卡片  
9. 产物列表与下载 URL  
10. 生成中「停止生成」→ `AbortController` + cancel API  
11. 网络/后端错误区分展示  
12. 刷新恢复 `localStorage` → `activeConversationId`（不自动重放 turn）  
13. 会话切换隔离  
14. 原工作台仍可用  
15. 阶段 1–8.4 后端回归  

## 7. 已知限制

- 窄视口（&lt;860px）会话栏改为上方折叠列表，桌面宽屏为左侧栏。
- 浏览器自动化对极快完成的短回复可能采不到中间「停止」帧；发送瞬间可见「停止生成」。
- 工具参数仅展示后端已脱敏的 `arguments_summary`；前端不做二次推断成功态。
- 同步非流式 `/turns` 未作为主路径暴露（产品以 SSE 为准）。
- 会话列表可能含开发期 probe / mount-smoke 空会话，属数据层残留，非 UI 伪造。

## 8. 阶段 8.6 前置条件（本阶段不执行）

1. 8.5 Chat UI 已验收（本文档）。  
2. DeepSeek 与 SSE 在演示环境可稳定连通。  
3. 准备 12 项对话评测集与评分口径（fixture / live 标注分离）。  
4. 评测脚本不得改写 API-Key；评测结果写入独立文档，不污染 ConversationStore 演示数据（建议隔离目录）。  
5. 人工确认后再启动 8.6。

---

**结论**：阶段 8.5 **PASS**。暂停，等待确认后再进入 8.6。

---

## 后续小优化（非 8.6）

论文检索重排与 Chat 论文卡片 / Markdown / 工具折叠：见 `docs/scholarflow-paper-search-ux.md`（对照证据 `docs/scholarflow-paper-search-ux-evidence.json`）。未改 8.0–8.5 架构与冻结题集。
