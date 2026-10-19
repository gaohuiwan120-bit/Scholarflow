# ScholarFlow 目标架构与阶段实施蓝图（阶段 0）

> 本文描述**目标架构**与相对现状的差距；**不**要求一次拆成十几个微服务。  
> 当前仓库仍以 ScholarFlow monorepo 为宿主；独立产品可渐进抽离到 `scholarflow/` 根包（阶段 1 再定目录名）。

---

## 1. 目标逻辑分层

```text
┌─────────────────────────────────────────────────────────┐
│  Frontend (ScholarFlow Web) — 建议 Vite+React（轻量）      │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP/SSE
┌──────────────────────────▼──────────────────────────────┐
│  API Layer — FastAPI（任务/产物/评测/健康检查）              │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│  Agent Runtime — LangGraph StateGraph + Checkpoint        │
│  Agent Layer — Orchestrator + Paper/Repo/Experiment(+Review)│
└───────┬─────────────────────────────┬───────────────────┘
        │ MCP Client                  │
┌───────▼──────────┐         ┌────────▼───────────────────┐
│ Tool Layer       │         │ Retrieval Layer              │
│ scholar_mcp      │◄────────│ Dense+BM25+RRF+Rerank        │
│ Server (stdio)   │ 补检     │ Evidence Store               │
└──────────────────┘         └────────┬───────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────┐
│ Artifact Layer — Pydantic models / 9 产物 / 溯源索引       │
│ Sandbox Layer — 受控执行（轻量容器或强约束 Local）          │
│ Evaluation Layer — 20 离线 / 10 E2E / Golden / RAG-50     │
│ Infrastructure — Docker（按阶段裁剪）、日志、配置            │
└─────────────────────────────────────────────────────────┘
```

### 1.1 模块依赖（允许方向）

- Frontend → API only  
- API → Runtime / Artifact / Evaluation  
- Runtime → MCP Client、Retrieval、Sandbox、Artifact  
- Retrieval → Artifact store；不足时 → MCP（补检）→ 再写回 Artifact/Index  
- Evaluation → Artifact + Runtime（E2E）或纯离线 scorer  
- **禁止** Frontend 直连 MCP / 直读伪造 JSON 冒充运行结果  

### 1.2 核心状态传递（目标）

建议 `ResearchState`（名称可调整）至少含：

- `task_id`、`phase`、`subtasks[]`（id/role/status/deps/error）  
- `research_plan`、`papers[]`、`repos[]`、`experiment`、`reviews[]`、`sources[]`  
- `tool_calls[]`、`rag_traces[]`、`mcp_call_count`  
- `artifacts` 路径映射、`partial_failure` 标志  

Checkpoint：本地 SQLite/JSON（8GB 优先），勿默认上重型集群。

### 1.3 API / MCP 边界

| 边界 | 职责 |
|------|------|
| FastAPI | 创建任务、订阅进度、列产物、下载、触发评测、健康检查 |
| MCP Server | arXiv/GitHub/校验/矩阵/报告/索引/RAG query — **工具语义** |
| Agent | 决定何时调哪个工具；不把业务规则只藏在前端 |

### 1.4 持久化与故障恢复

| 数据 | 策略 |
|------|------|
| 产物 9 件套 | 任务目录落盘（现有 `/mnt/user-data/outputs/<task_id>` 思路可保留） |
| RAG 索引 | 目录型 + 可选 Chroma；开发机用 JSON corpus |
| 运行状态 | LangGraph checkpoint |
| 评测报告 | `evaluation/reports/` 版本化文件名 |
| 恢复 | 从 checkpoint + 已有产物续跑；禁止 silent 假完成 |

### 1.5 并行 / 超时 / 重试 / 资源

- 默认并行度 ≤ 2（8GB）；可配置上限 3  
- 工具超时：MCP client 层（已有 resilience 可复用）  
- 子任务失败：标记 partial → Review 必须可见 → Aggregate 可降级交付  
- 同时只起**当前阶段**所需容器  

---

## 2. 现状架构（简图）

```text
ScholarFlow Next UI ──► Gateway(FastAPI) ──► LangGraph Lead
                           │                    │
                           │              task Sub-Agents
                           │                    │
                      MCP Client ──────► scholar_mcp tools
                           │                    │
                      Sandbox ─────────► write 9 artifacts
                                            │
                                      scholar.rag (CLI/MCP)
```

**差距要点：** 无独立品牌前端；无 Scholar 自有 StateGraph；RAG 无 Cross-Encoder；补检非自动闭环；评测定义多于真实全量跑通；Sandbox 属底座而非 Scholar 产品能力。

---

## 3. 各阶段：目录/文件、验收、风险、8GB 跑法

### 阶段 0 — 审计（本阶段，已完成文档）

| 交付 | 路径 |
|------|------|
| 审计报告 | `docs/scholarflow-redevelopment-audit.md` |
| 需求矩阵 | `docs/scholarflow-requirements-matrix.md` |
| 架构蓝图 | `docs/scholarflow-architecture.md`（本文件） |

**验收：** 文档与源码一致；标明简历风险项。  
**风险：** 无。  
**8GB：** 无需 Docker。

---

### 阶段 1 — 独立前端 + 最小运行闭环

| 预计改动 | 说明 |
|----------|------|
| 新建 `frontend-scholar/` 或 `apps/web/`（Vite） | 品牌、任务创建、结果展示 |
| 新建或扩展 `backend/app` 轻量路由 / 或 `services/scholar_api/` | `POST /tasks`、`GET /tasks/{id}`、产物列表 |
| 复用 `scholar` 包一次真实调用 | 例如：assemble 或 rag_answer 或单节点「plan」 |
| 文档 | `docs/scholar-flow/setup-lite.md` |

**验收：** 浏览器操作 → API → **真实**后端逻辑 → 页面展示；无静态假 JSON。  
**风险：** 若仍绑 ScholarFlow Next Docker，8GB 易 OOM → **必须走 Vite 本机**。  
**8GB：** `uv run` API + `pnpm/vite` 前端；不开 compose 全栈。

---

### 阶段 2 — LangGraph 多 Agent 工作流

| 预计改动 | 说明 |
|----------|------|
| `scholarflow/scholar/graph/` 或 `scholarflow/runtime/graph.py` | StateGraph：plan→parallel→review→aggregate |
| 移植 Skills 为节点 Prompt/工具策略 | 保留 `skills/custom` 作规格 |
| 显式 deps、重试、partial failure | 状态机字段 |
| API 进度 SSE | 供前端真实状态 |

**验收：** 一次任务产生可追踪 subtask 状态；并行可观测；失败用例可测。  
**风险：** 与 ScholarFlow Lead 双运行时冲突 → 明确「嵌入」或「旁路」一种。  
**8GB：** 并行度 1–2；单模型。

---

### 阶段 3 — MCP 与结构化产物加固

| 预计改动 | 说明 |
|----------|------|
| 保持 `extensions/scholar_mcp` | 补客户端集成测试、超时统一 |
| 锁定 7 模型名单 + 文档 | `data-contracts` |
| 产物注册/查询 API | 基于 paths/artifacts |
| 可选轻量 MCP host 进程 | 与 API 同机 |

**验收：** Agent 仅经 MCP 名调用；9 产物 scorer 全绿（单黄金任务 + 抽检）。  
**风险：** GitHub rate limit → fixture + 真实分轨。  
**8GB：** MCP stdio 单进程。

---

### 阶段 4 — 可追溯 RAG（对齐简历或改简历）

| 预计改动 | 说明 |
|----------|------|
| Cross-Encoder 可选模块 | 如 `rag/rerank_ce.py`；默认开关，8GB 可关 |
| `evaluation/rag_qa_50.json` | 题、参考、证据标注 |
| 基线 / 完整 / 补检对照脚本 | 禁止硬编码指标 |
| 自动补检闭环 | flag→MCP→reindex→answer |

**验收：** 脚本复算出忠实度/Hit@5/引用准确率/MCP 调用量；达不到则报告真实值。  
**风险：** CE 模型内存；应用 lite 或远程。  
**8GB：** 默认 hybrid-score；CE 夜间批跑。

---

### 阶段 5 — Sandbox

| 预计改动 | 说明 |
|----------|------|
| `scholar/sandbox/` 策略封装 | 超时、目录白名单、禁网选项 |
| 测试 | 恶意路径/超时用例 |
| Compose profile `sandbox` | 默认关闭 |

**验收：** Agent 生成代码不在宿主机裸跑；限制可测。  
**风险：** 再起容器挤爆内存 → 开发期用 Local+seccomp 风格限制优先。  
**8GB：** profile 默认 off。

---

### 阶段 6 — 评测与回归

| 预计改动 | 说明 |
|----------|------|
| 充实 `evaluation/` | 真实 20/10 跑批、Golden 版本目录 |
| 报告模板 | 失败节点、口径说明 |
| CI 可选 job | 仅 schema 级，不全量 E2E |

**验收：** 完成率/Schema 率有分母定义；可重复；与简历差异透明。  
**风险：** 全量 E2E 耗 API 费用与时间。  
**8GB：** 夜间串行；fixture/mock 白天。

---

### 阶段 7 — 部署与演示

| 预计改动 | 说明 |
|----------|------|
| `docker-compose.scholar.yaml` | 仅 API+（可选）web+redis；无重型前端镜像 |
| 演示脚本 / 健康检查 | 一键 demo |
| 面试演示手册 | 真实命令与预期画面 |

**验收：** 领导演示路径 ≤3 步；RAG CLI 备用路径保留。  
**风险：** 再引入 Next 全量 Docker → 回归 OOM。  
**8GB：** 演示优先「API+Vite」或「RAG CLI + 产物目录」。

---

## 4. 简历指标治理（强制）

| 指标 | 当前仓库证据 | 阶段 0 结论 |
|------|--------------|-------------|
| Cross-Encoder | 无；hybrid-score | 实现或改简历 |
| 忠实度 0.62→0.84 | 无 50 题集/实验 | 未达标可宣称 |
| Hit@5 82% / 引用 91% / MCP↓77% | 无 | 同上 |
| E2E 90% / Schema 97% | 定义有；真实全量未达口径 | 以实测为准 |

任何报告生成器**不得**写死这些数字。

---

## 5. 阶段门禁

- 上一阶段核心验收未过 → **不**用堆功能掩盖。  
- 每阶段可回滚：独立 commit；不 `down -v`；不删 ScholarFlow。  
- 阶段 0 完成后 **等待确认** 再开阶段 1。

---

## 6. 建议的 Agent 角色数量（目标设计）

| 角色 | 职责 | 备注 |
|------|------|------|
| Orchestrator | 拆解、依赖、汇总、触发审查 | 1 |
| Paper Agent | 检索与证据结构化 | 1 |
| Repository Agent | 仓库概览与结构证据 | 1 |
| Experiment Agent | 方案与风险 | 1 |
| Reviewer（可选合并进 Orchestrator） | 证据审查 | 0 或 1 |

合计 **4–5**；禁止同逻辑多名字节点。
