# ScholarFlow 启用清单

## 1. 填写 API Key（必做）

编辑项目根目录 `.env`：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxx   # https://platform.deepseek.com
# 可选
GITHUB_TOKEN=ghp_xxxxxxxx
```

## 2. 确认扩展已启用

`extensions_config.json` 中 `scholar_mcp.enabled` 应为 `true`。

MCP 路径通过环境变量解析（Docker 内由 `docker-compose-dev.yaml` 注入）：

- `SCHOLAR_MCP_PYTHON` — gateway venv 中的 Python
- `SCHOLAR_PYTHONPATH` — harness + scholar_mcp 包路径

## 3. 重启 Docker

```bash
./scripts/docker.sh stop
./scripts/docker.sh start
```

## 4. 自检

```powershell
# 健康检查
curl.exe http://localhost:2026/health

# 单元测试
cd backend
uv run pytest tests/test_scholar_schemas.py -q

# MCP 测试
cd extensions/scholar_mcp
uv sync --group dev
uv run pytest -q

# 离线评测
cd backend
uv run python ..\evaluation\run_eval.py
```

或使用一键脚本（Git Bash）：

```bash
bash scripts/verify_scholarflow.sh
```

## 5. 端到端验收

在 http://localhost:2026 发送：

> 使用 scientific-research-orchestration，调研 RAG 架构及相关 GitHub 实现，task id: `rag-test-001`

检查 Sandbox 输出目录是否包含 9 个文件（见 `docs/scholar-flow/data-contracts.md`）。

## 故障排查

| 现象 | 处理 |
|------|------|
| 无法对话 / 无模型 | 检查 `config.yaml` 中 `deepseek-chat` 与 `DEEPSEEK_API_KEY` |
| MCP 工具不可用 | 重启 gateway；检查容器内 `echo $SCHOLAR_MCP_DIR` |
| arXiv 搜索失败 | 检查网络/代理；MCP 使用 export.arxiv.org |
| GitHub 限流 | 配置 `GITHUB_TOKEN` |
