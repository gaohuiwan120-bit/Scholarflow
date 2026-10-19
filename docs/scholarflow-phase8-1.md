# ScholarFlow Phase 8.1 — ConversationStore + 会话 REST 验收记录

- **status**: PASS
- **scope**: 会话管理与 JSON/JSONL 持久化；**不含** Tool-calling Agent、SSE、Chat UI

## 相对设计稿的接口调整

沿用 [`docs/scholarflow-phase8-design.md`](scholarflow-phase8-design.md) 路径，并做如下明确：

| 调整 | 原因 |
|------|------|
| 新增 `GET /api/v1/conversations/{id}` | 用户验收要求「获取会话详情」 |
| `POST .../messages` 仅持久化 | 8.1 不做 LLM/SSE；8.2/8.3 再接 Agent 与流式 |
| 暂不实现 `POST .../stop` | 依赖生成中状态（8.3） |

## 存储布局

```
apps/scholarflow-api/data/conversations/{conversation_id}/
  meta.json
  messages.jsonl
```

- 根目录：`SCHOLARFLOW_CONVERSATIONS_DIR`，否则若设了 `SCHOLARFLOW_TASKS_DIR` 则用其兄弟 `../conversations`，默认 `apps/scholarflow-api/data/conversations`（已在 `.gitignore`）。
- **不**写入 `task_state.json` / artifacts；与 TaskStore、RAG 索引分离。

## Schema 要点

- `conversation_id`：`cv-` + 12 hex  
- `message_id`：`msg-` + 12 hex  
- 角色 / content / `created_at`  
- 预留：`tool_call_trace[]`、`related_task_id`、`evidence_refs[]`（默认空，不伪造）

## REST

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/conversations` | 创建 |
| GET | `/api/v1/conversations` | 列表（按 updated_at 降序） |
| GET | `/api/v1/conversations/{id}` | 详情 |
| GET | `/api/v1/conversations/{id}/messages` | 历史（按时间+message_id） |
| POST | `/api/v1/conversations/{id}/messages` | 追加消息（无 LLM） |
| GET | `/api/v1/conversations/{id}/tasks` | 从消息收集 `related_task_id` |

错误：非法 ID → 400；不存在 → 404；损坏 meta/jsonl → 409。

## 测试结果

| 套件 | 结果 |
|------|------|
| `tests/test_chat_store.py` | 通过（创建/顺序/重启实例/隔离/非法 ID/损坏/并发 40 写） |
| `tests/test_chat_api.py` | 通过（REST + 重启恢复 + 409） |
| `tests/`（`-m "not live_llm"`） | **53 passed**, 1 skipped, 1 deselected |

## 修改文件

- `apps/scholarflow-api/scholarflow_api/chat/{__init__,schemas,store,router}.py`
- `apps/scholarflow-api/scholarflow_api/app.py`（挂载 router）
- `apps/scholarflow-api/tests/test_chat_store.py`
- `apps/scholarflow-api/tests/test_chat_api.py`
- `apps/scholarflow-api/scholarflow_api/llm/settings.py`（允许加载 CONVERSATIONS/TASKS 路径 env）
- `scripts/start_scholarflow_api.ps1`
- `.env.example`
- `docs/scholarflow-phase8-1.md`
- `docs/scholarflow-requirements-matrix.md`（§J）

未修改：DeepSeek Key、评测冻结数据、ScholarFlow Docker。

## 已知限制

1. 进程内按会话锁；跨多进程写同一会话未加 OS 文件锁（单机单 API 进程场景足够）。  
2. `POST /messages` 不会调用 LLM；多轮「对话」需客户端自行写入 assistant，或等 8.2。  
3. `list` 跳过损坏会话目录并打日志；单会话读损坏仍返回 409。  
4. 未实现 stop / SSE。

## 8.2 前置条件

1. 会话 CRUD + 消息历史可读写（已满足）。  
2. 8.0 `SfLlmClient` 可用（已满足）。  
3. 下一阶段：`bind_tools` Agent 读会话历史、写 assistant + `tool_call_trace`；仍不实现完整 Chat UI（8.5）。
