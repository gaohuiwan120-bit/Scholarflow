# ScholarFlow Phase 7 — 部署与演示验收（Windows 本机）

> 运行方式：**本机 Vite + FastAPI**（不启动 `scholarflow-*` / 整套 ScholarFlow Docker）。  
> 演示与冒烟默认 **`data_mode=fixture`**；**不得**把 fixture 结果写成 live 集成。  
> Sandbox 仅作受控执行演示，**不是**生产级隔离。

阶段 6 轻量核查见 [`scholarflow-phase6-audit.md`](scholarflow-phase6-audit.md)。

---

## 1. 启动 / 停止 / 健康检查

### 启动（两个终端）

```powershell
# 终端 A — API :8100
cd E:\AgentProject\scholarflow_project
powershell -NoProfile -File .\scripts\start_scholarflow_api.ps1

# 终端 B — Vite :5173（代理 /api 与 /health → 8100）
powershell -NoProfile -File .\scripts\start_scholarflow_web.ps1
```

浏览器打开：`http://127.0.0.1:5173`

### 健康检查

```powershell
powershell -NoProfile -File .\scripts\health_scholarflow.ps1
# 或
Invoke-RestMethod http://127.0.0.1:8100/health
```

期望字段：`status=ok`，`langgraph_available=true`，`runtimes` 含 `rag_v1` / `research_graph_v1`。

### 停止（仅本机 8100/5173 进程）

```powershell
powershell -NoProfile -File .\scripts\stop_scholarflow.ps1
```

**不会**执行 `docker compose down`，不碰其他容器。

### 演示冒烟（需 API 已启动）

```powershell
backend\.venv\Scripts\python.exe .\scripts\demo_scholarflow_smoke.py
```

报告：`evaluation/reports/phase7-demo-smoke.json`

---

## 2. 本机实测结果（2026-10-18）

| 项 | 结果 |
|----|------|
| API `/health` | OK；langgraph / sandbox_available / sandbox_docker 均为 true |
| Vite `:5173` | HTTP 200 |
| Demo smoke | **8/8 passed**（fixture） |

| Demo case | 实测 |
|-----------|------|
| paper_research | partial_succeeded；9 产物；list/download 200 |
| repository_analysis | partial_succeeded；9 产物 |
| research_orchestration | succeeded；9 产物；review=pass |
| rag_query_ok | succeeded；evidence>0 |
| rag_insufficient_refuse_signal | need_mcp_fallback=true |
| force_fail_review | status=failed |
| sandbox_process_jail | succeeded；backend=process_jail |
| mcp_tools | HTTP 200；工具列表非空 |

声明：以上均为 **fixture** 演示路径；MCP tools 列表成功 ≠ live arXiv/GitHub 拉数已验收。

---

## 3. 推荐演示顺序（UI）

固定问句：`Blended RAG hybrid dense sparse vs Naive RAG`；**Data mode = fixture**。

1. 打开前端，确认健康条正常。  
2. **论文调研** → 提交 → 见 papers / partial 或 succeeded、产物可下载。  
3. **仓库分析** → 提交 → 见 repos。  
4. **综合科研编排** → 提交 → 见并行子任务、9 产物、review pass。  
5. **Hybrid RAG** → 同问句 → 有 evidence 与引用。  
6. **错误路径**：无意义问句（或 enable fallback）→ `need_mcp_fallback`；勾选/触发 `force_fail_review`（API）→ failed，不伪装成功。  
7. （可选）说明 Sandbox：API `POST /api/v1/sandbox/execute` 无害 `print(2+2)`；强调非生产隔离。  
8. **不要**在简历叙事中把本演示说成「线上 live 全绿」。

---

## 4. 故障排查

| 现象 | 处理 |
|------|------|
| `/health` 连不上 | 确认 API 终端无报错；端口 8100 未被占用；`stop` 后再 `start_api` |
| 前端空白 / API 失败 | 确认 Vite 代理指向 8100；先起 API 再起 Web |
| `artifacts_dir_exists=false` | 检查 `docs/scholar-flow/samples/rag-test-001` 是否存在 |
| `langgraph_available=false` | 用 `backend\.venv`；确认 langgraph 已安装 |
| MCP tools 503 | 本机 stdio MCP 冷启动失败；演示可继续用 fixture 工作流，勿宣称 live MCP |
| Docker Sandbox | 仅需 Desktop **引擎**；勿开 scholarflow 容器；镜像异常见 phase5 DaoCloud 说明 |
| 8GB 内存 | 勿 `docker compose` 整栈；保持 Vite+API 双进程 |

---

## 5. 仍不能宣称 / 未达标（保留）

| 项 | 状态 |
|----|------|
| 忠实度原始 0.62 可核验记录 | **缺失**（phase4 审计） |
| MCP 调用量下降 77% | **未达标**（同主题 mock ≈60%） |
| Live 外网 E2E 完成率 | **未并入**阶段 6/7 完成率 |
| Sandbox 生产级隔离 | **不可宣称**（绝对路径缺口等） |
| 旧合成 golden 10/10 | **≠** Agent Bench E2E 完成率 |

---

## 6. 相关脚本

| 脚本 | 用途 |
|------|------|
| `scripts/start_scholarflow_api.ps1` | 起 API |
| `scripts/start_scholarflow_web.ps1` | 起 Vite |
| `scripts/stop_scholarflow.ps1` | 停 8100/5173 |
| `scripts/health_scholarflow.ps1` | 健康检查 |
| `scripts/demo_scholarflow_smoke.py` | 演示冒烟 |
| `evaluation/run_agent_bench.py` | 阶段 6 评测入口 |
