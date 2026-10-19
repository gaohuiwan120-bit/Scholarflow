# ScholarFlow 演示预检说明

保障 **8GB 本机** 上 ScholarFlow（Vite `:5173` + FastAPI `:8100` + DeepSeek + arXiv/GitHub MCP）演示稳定性。  
**不**启动 ScholarFlow 全栈 Docker / Dify，**不**自动跑完整 live 科研工作流，**不**修改 `.env` 或历史产物。

## 演示前怎么跑

在仓库根目录：

```powershell
cd E:\AgentProject\scholarflow_project

# 1) 如未启动，先起服务（两个终端）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_scholarflow_api.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_scholarflow_web.ps1

# 2) 默认预检（不打外部 MCP，不耗 GitHub 配额）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\preflight_scholarflow.ps1

# 3) 可选：轻量 GitHub MCP 探针（有超时；仍不跑完整 research_orchestration）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\preflight_scholarflow.ps1 -IncludeMcpProbe
```

轻量健康检查（既有脚本，可复用）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\health_scholarflow.ps1
```

停止本机 ScholarFlow 端口占用（不碰 Docker）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_scholarflow.ps1
```

## 检查项与状态含义

| 检查名 | PASS | WARN | FAIL |
| --- | --- | --- | --- |
| `startup_scripts_present` | 启动/健康脚本齐全 | — | 脚本缺失 |
| `start_script_scholar_mcp_path` | 启动脚本含 `scholar_mcp` 且目录存在 | — | 路径未配置或包缺失（live 仓库搜索会坏） |
| `api_port_8100` | 8100 在监听 | — | API 未启动 |
| `api_health` | `GET /health` → `status=ok` | — | 本地 API 不可达/超时 |
| `api_langgraph` | `langgraph_available=true` | 为 false，综合工作流可能不可用 | — |
| `web_http_5173` | 前端 HTTP 2xx | 未启动或异常（可仅演示 API） | — |
| `llm_configured` | 运行时 `llm_configured=true` | 未配置或 API 未起来 | — |
| `deepseek_key_presence` | `.env` 中 DeepSeek 密钥**已配置** | **未配置** | — |
| `github_token_presence` | GitHub Token **已配置** | **未配置**（易撞未认证限流） | — |
| `github_mcp_probe` | `-IncludeMcpProbe` 且 overview 成功 | 默认跳过，或外部限流/网络/认证问题 | 仅当请求探针但本地 8100 都没起来 |

总体：

- **READY**：无 FAIL、无 WARN  
- **READY WITH WARNINGS**：无 FAIL，有 WARN（可演示，但注意 caveats）  
- **NOT READY**：存在 FAIL（先修本地服务）

退出码：`0` = 无 FAIL；`1` = 有 FAIL。

## 密钥与安全

- 预检只报告「已配置 / 未配置」。
- **不**打印 Token / API Key 明文、长度、前缀或完整环境变量。
- 不写入、不提交 `.env`。

## 明确不会做的事

- 不杀进程、不删数据、不改 `.env`
- 不启动 ScholarFlow Docker / Dify
- 不自动创建完整 `research_orchestration` live 任务
- 不把 fixture 或历史 task 结果当成「本次预检通过」

## 预检覆盖不了的风险

1. **演示中途** arXiv 429 / GitHub 限流或网络抖动  
2. DeepSeek **额度耗尽或模型侧故障**（预检只看本地 `llm_configured`）  
3. 长任务/大产物导致 **8GB 内存压力**  
4. 规则型 Review / 相关性启发式的内容质量  
5. 浏览器缓存、代理、防火墙对 Vite 的干扰  
6. 未用正式启动脚本导致 `scholar_mcp` 未进 `PYTHONPATH`（预检可发现脚本内容，无法代替每次启动方式）

正式验收记录仍以独立报告为准（如 `docs/scholarflow-final-acceptance.md`），与本预检脚本无关。
