# ScholarFlow Phase 8.0 — LLM Client 验收记录

- **status**: PASS
- **tested_at (UTC)**: `2026-10-18T05:18:09.945100+00:00`
- **model**: `deepseek-chat`
- **base_url**: `https://api.deepseek.com`
- **invocation**: `langchain_deepseek.ChatDeepSeek.invoke`
- **ok**: `True`
- **latency_ms**: `1992.0`
- **response_preview**: `PONG`
- **error**: `None`

## 进程 / Health 核查

- 重启 ScholarFlow API（仅 :8100，未触碰 ScholarFlow Docker）。
- `GET /health` → `llm_configured=true`，`llm_model=deepseek-chat`，`llm_provider=deepseek`。
- health JSON 中无 `sk-` 前缀泄露。
- 启动路径：根目录 `.env` → 进程环境 `DEEPSEEK_API_KEY` → `load_root_env_into_process` / `get_llm_settings`。

## 测试

| 套件 | 结果 |
|------|------|
| `tests/test_llm_settings.py` + `test_health.py` | 7 passed |
| `tests/test_llm_live.py`（`SCHOLARFLOW_LIVE_LLM=1`） | 1 passed |

## 约束核对

- 使用 `langchain_deepseek.ChatDeepSeek`（未复制 ScholarFlow `config.yaml`，未改用 PatchedChatDeepSeek）。
- 密钥仅从进程环境 / 根目录 `.env` 的 `DEEPSEEK_API_KEY` 读取；本报告不含密钥明文；未修改原 Key。
- 未启动 `scholarflow-dev` / `scholarflow-front` / 整套 ScholarFlow Docker。
- 未实现 8.1+ 会话 / Agent / SSE；未改评测冻结数据。

## 修改文件（8.0）

- `apps/scholarflow-api/scholarflow_api/llm/__init__.py`
- `apps/scholarflow-api/scholarflow_api/llm/settings.py`
- `apps/scholarflow-api/scholarflow_api/llm/client.py`
- `apps/scholarflow-api/scholarflow_api/llm/guards.py`
- `apps/scholarflow-api/scholarflow_api/models.py`
- `apps/scholarflow-api/scholarflow_api/app.py`
- `apps/scholarflow-api/scholarflow_api/__main__.py`
- `apps/scholarflow-api/pyproject.toml`（optional `llm` + pytest marker）
- `apps/scholarflow-api/tests/test_llm_settings.py`
- `apps/scholarflow-api/tests/test_llm_live.py`
- `apps/scholarflow-api/tests/test_health.py`
- `scripts/start_scholarflow_api.ps1`
- `scripts/verify_scholarflow_llm.py`
- `.env.example`（补充 ScholarFlow LLM 可选变量说明）
- `docs/scholarflow-phase8-0.md`（本文件）

## 8.1 前置条件

1. 8.0 客户端稳定：`SfLlmClient` / `ping_llm` 可用。
2. `DEEPSEEK_API_KEY` 已能通过启动脚本注入 API 进程（已验证）。
3. 下一阶段实现 `ConversationStore` + REST，仍不默认拉大型本地模型。
