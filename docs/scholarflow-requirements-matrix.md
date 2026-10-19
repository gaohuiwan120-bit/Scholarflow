# ScholarFlow 简历需求映射矩阵（阶段 0）

> 状态只能使用：`已实现且已验证` | `已实现但未验证` | `部分实现` | `尚未实现` | `存在风险`  
> 证据均指向本仓库真实路径；指标类「存在风险」表示简历数字当前**不可复现宣称**。

---

## A. 技术栈

| 简历项 | 目标模块 | 当前代码位置 | 状态 | 依赖 | 测试方法 | 验收标准 |
|--------|----------|--------------|------|------|----------|----------|
| Python | 全栈后端 | `backend/`、`extensions/scholar_mcp/`、`evaluation/` | 已实现且已验证 | uv/venv | pytest / CLI | 核心包可 import、单测通过 |
| LangGraph | Agent Runtime | `apps/scholarflow-api/scholarflow_api/graph/` StateGraph | 已实现且已验证（Phase 2/3） | langgraph | `tests/test_research_graph.py` | 节点可编排、并行、可查询 |
| FastAPI | API Layer | `apps/scholarflow-api` + ScholarFlow Gateway | 已实现且已验证（轻量 API） | FastAPI | `/health`、tasks API | 独立 Vite+FastAPI 可演示 |
| RAG | Retrieval Layer | `scholarflow/scholar/rag/` | 已实现且已验证（hybrid-score） | fastembed/chromadb/jieba | `run_rag_demo.py` | DEMO OK + evidence_id 绑定 |
| MCP | Tool Layer | `extensions/scholar_mcp/` + ScholarFlow MCP client | 已实现且已验证 | mcp、httpx | `extensions/scholar_mcp/tests` | 工具经 MCP 协议暴露并可被 Agent 调用 |
| Pydantic | Artifact Layer | `scholarflow/scholar/models.py` | 已实现且已验证 | pydantic | `test_scholar_schemas.py` | 非法 payload 拒绝；9 产物校验 |
| Docker | Infrastructure | `docker/docker-compose-dev.yaml` | 已实现但未验证（演示稳定性） | Docker Desktop | compose up + HTTP | 8GB 机稳定打开演示页（当前风险） |
| Sandbox | Sandbox Layer | `scholarflow/scholar/sandbox` + ScholarFlow sandbox | 已实现且已验证（Scholar process_jail+Docker 最小实测）；绝对路径读宿主机仍有缺口；ScholarFlow 宿主 bash 仍有风险 | 仅 Desktop 引擎 + 按需 alpine；勿开整栈 | API/MCP + verify 脚本 | 勿宣称生产级绝对隔离 |

---

## B. 多智能体科研工作流

| # | 简历要求 | 目标模块 | 代码位置 | 状态 | 依赖 | 测试方法 | 验收标准 |
|---|----------|----------|----------|------|------|----------|----------|
| B1 | 任务编排工作流 | Orchestrator Agent/Skill | `skills/custom/scientific-research-orchestration/` | 部分实现 | Lead Agent、`task` | E2E prompt | 可产出 research_plan + 分发 |
| B2 | 论文证据提取工作流 | Paper Sub-Agent | `skills/custom/paper-evidence-extraction/` + arXiv MCP | 部分实现 | MCP arXiv | 样本 paper_evidence.json | ≥N 篇带 source_url |
| B3 | 仓库分析工作流 | Repo Sub-Agent | `skills/custom/repository-analysis/` + GitHub MCP | 部分实现 | GITHUB_TOKEN | 样本 repository_evidence.json | 结构字段齐全 |
| B4 | 实验方案工作流 | Experiment Sub-Agent | `skills/custom/experiment-plan/` | 部分实现 | 上游证据 | experiment_plan.md | 含假设/基线/风险 |
| B5 | LangGraph 状态与节点调度 | Agent Runtime | `apps/scholarflow-api/.../graph/` | 已实现且已验证 | langgraph | test_research_graph | 节点状态可查询 |
| B6 | 主 Agent 拆解/分发/汇总 | Lead + aggregation | orchestrator→assemble + artifacts | 已实现且已验证 | — | 9 件套 + 落盘 | 汇总非手工粘贴 |
| B7 | 明确职责 Sub-Agent | 3–4 类角色 | paper/repo/experiment/review 节点 | 已实现且已验证 | — | 角色边界 | 禁止同逻辑换皮 |
| B8 | 真实并行 + 显式依赖 | Scheduler | paper∥repo → join → experiment | 已实现且已验证 | LangGraph | OVERLAP 测试 | 依赖边可序列化 |
| B9 | 失败/超时/重试/部分失败 | Runtime policies | force_fail + live 降级标记 + MCP 重试 + **主题感知降级拒绝** | 已实现且已验证（部分） | — | test_live_mode_guard / test_evidence_relevance | 部分失败可观测；异主题 fixture 不得伪装成功 |
| B10 | 证据审查 + 聚合 | Review + Aggregate | review_node + assemble_node（**确定性规则**；动态 claim） | 已实现且已验证 | — | evidence_review.json / test_evidence_relevance | 审查状态枚举合法；禁止固定 RAG slogan |
| B10b | 检索主题相关性门控 | Evidence gate | `graph/evidence_gate.py` + resolve_live_repository | **已实现且已验证（最小）** | paper_rank 启发式 | test_evidence_relevance + live E2E `sf-rel-e2e-*` | 异主题证据拒绝；不足则 failed；见 `docs/scholarflow-research-relevance-audit.md` |
| B11 | 任务/子任务/工具/结果可追踪 | Trace | API subtasks + mcp_calls + manifest | 已实现且已验证 | — | API/前端 | task_id↔artifact 可查 |
| B12 | 前端真实执行状态 | Frontend | `apps/scholarflow-web` | 已实现且已验证 | Vite | UI 轮询 | 禁止假进度条 |

---

## C. MCP 与结构化产物

| # | 简历要求 | 代码位置 | 状态 | 测试方法 | 验收标准 |
|---|----------|----------|------|----------|----------|
| C1 | 独立可运行 MCP 服务 | `extensions/scholar_mcp/server.py` | 已实现且已验证 | pytest + stdio | `mcp.run` |
| C2 | arXiv 检索 | `clients/arxiv.py` | 已实现且已验证 | 单测/集成 | 返回真实 abs URL |
| C3 | GitHub 仓库分析 | `clients/github.py` | 已实现且已验证 | token 集成 | overview 字段 |
| C4 | Schema 校验工具 | `validate_evidence_schema` | 已实现且已验证 | test_scholar_schemas | invalid→error |
| C5 | 报告生成 | `build_research_report` / assemble | 已实现且已验证 | 单测 | md 含引用痕迹 |
| C6 | 经 MCP Client 调用 | `scholarflow_api/mcp/client.py` stdio | 已实现且已验证 | test_mcp_protocol | 工具名出现在 mcp_calls |
| C7 | 结果回写工作流 | live/fixture → state → experiment/review | 已实现且已验证 | test_live_mode_guard / graph | 下游消费 JSON |
| C8 | 参数校验/异常/超时/日志 | MCP 重试 + resilience + 降级事件 | 已实现且已验证（部分） | test_mcp / live_guard | 超时/失败可观测 |
| C9 | 7 类有用模型 | `models.py` 核心约 6–7 + Collections | 已实现但未验证 | 文档锁定名单 | 名单与简历一致 |
| C10 | 9 类产物 + 注册/复用 | `REQUIRED_ARTIFACTS`；list/assemble；RAG index | 已实现且已验证（落盘）；复用索引部分实现 | 目录检查 + index | 缺一则 scorer 失败 |

**建议锁定的 7 类业务模型（待阶段 1 文档确认）：**  
`ResearchPlan`、`PaperEvidence`、`RepositoryEvidence`、`ExperimentPlan`、`ReviewFinding`、`SourceRecord`、`DateRange`（或把 Collection 升为第 7 类「EvidenceBundle」— 需产品确认，禁止空壳凑数）。

**9 类产物（已锁定）：**  
`research_report.md`、`research_plan.json`、`paper_evidence.json`、`paper_matrix.csv`、`repository_evidence.json`、`repository_matrix.csv`、`experiment_plan.md`、`evidence_review.json`、`sources.json`

---

## D. 可追溯 RAG

| # | 简历要求 | 代码位置 | 状态 | 测试方法 | 验收标准 |
|---|----------|----------|------|----------|----------|
| D1 | 解析/切分/索引 | `rag/chunking.py` `store.py` | 已实现且已验证 | run_rag_demo | chunk_count>0 |
| D2 | 向量 + BM25 | `retrieve.py` | 已实现且已验证 | 同左 | 双路命中日志 |
| D3 | RRF 融合 | `retrieve.py` / config | 已实现且已验证 | 同左 | fusion=RRF |
| D4 | Cross-Encoder 重排 | ONNX MiniLM CE + hybrid-score 基线 | 已实现且已验证 | test_scholar_rag_phase4 + 50 题对照 | CE 非 hybrid-score 伪装 |
| D5 | 统一证据对象 | rag 返回 evidence 字段 | 已实现且已验证 | JSON 检查 | evidence_id+source_url |
| D6 | 生成绑定证据 | `citation.assemble_cited_answer` | 已实现且已验证 | citation 测试 | 无空引用 |
| D7 | 证据不足判断 | topical overlap + min_evidence | 已实现且已验证 | fallback 测试 | flag 正确 |
| D8 | 补检再入链路 | `retrieve_with_mcp_fallback` | 已实现且已验证 | phase4 测试 + live eval | 补检后索引更新再答 |
| D9 | 记录检索/引用/MCP 次数 | diagnostics + mcp_rounds + eval | 已实现且已验证 | run_rag_qa_eval | 可复算调用量 |
| D10 | 历史产物复用 | index + cold vs indexed MCP | 已实现但未达标（↓60%≠77%） | mcp_reduction_measured.json | 同主题少调 MCP |
| D11 | 50 题集 + 指标 | `evaluation/rag_qa/v1` | 已实现且已验证（指标真实计算） | run_rag_qa_eval | 禁硬编码目标值 |

---

## E. 评测与版本回归

| # | 简历要求 | 代码位置 | 状态 | 测试方法 | 验收标准 |
|---|----------|----------|------|----------|----------|
| E1 | 20 离线任务 | `evaluation/agent_bench/v1/offline_tasks.json` + `run_agent_bench.py` | **已实现且已验证**（20/20 fixture） | `--suite offline` | 经 FastAPI/公开 RAG 入口；旧 `tasks.json` 仅兼容 |
| E2 | 10 E2E | `evaluation/agent_bench/v1/e2e_tasks.json` | **已实现且已验证**（完成率 90%） | `--suite e2e` | FastAPI TestClient；旧 Gateway `e2e_runner` 不计入 |
| E3 | Schema 合法性 | `METRICS.md` + `validate_json_artifact` 事件 | **已实现且已验证**（100%） | 报告 `schema_pass_rate` | 按校验事件；非仅字段存在 |
| E4 | 产物完整性 | assertions + metrics | **已实现且已验证** | nine / research_pack 断言 | 缺文件失败；失败任务不伪装九件套 |
| E5 | evidence 溯源 | `source_traceability` 断言 | **已实现且已验证** | off-12 | id/url 可追溯 |
| E6 | 工作流完成检查 | outcomes 枚举 | **已实现且已验证** | e2e_completion_rate | partial/refuse ≠ 完成 |
| E7 | Golden 版本回归 | `agent_bench/v1/golden/snapshot.json` | **已实现且已验证** | `--update-golden` / compare | 字段级 diff；≠ 旧合成 golden |
| E8 | JSON/MD 报告 | `evaluation/reports/agent-bench-latest.*` | **已实现且已验证** | 打开报告 | 含每任务断言与失败原因 |
| E9 | 失败任务日志 | 报告 failures 段 + assertion detail | **已实现且已验证** | force_fail_* 任务 | 可定位断言 |
| E10 | 同版本可重复 | fixture + 固定规格 | **已实现且已验证**（fixture） | 重跑 CLI | live 不并入完成率 |
| E11 | 完成率 90% / Schema 97% | `agent-bench-latest.json` rates | **已实现且已验证（本机 fixture）** | 实测 90% / 100% | 换环境重跑；勿改口径凑数 |

---

## F. Sandbox / 前端 / 独立产品

| 简历/目标项 | 状态 | 说明 |
|-------------|------|------|
| 受控脚本执行、超时、网络/文件限制 | 已实现且已验证（process_jail + Docker 最小实测；绝对路径缺口已记录；非绝对安全） | 阶段 5；阶段 7 演示冒烟含 process_jail |
| 独立 ScholarFlow 前端品牌与任务 UI | **已实现且已验证**（Vite 本机） | `apps/scholarflow-web`；阶段 7 启动验收 |
| 工具调用与证据展示 UI | **部分实现** | 前端展示 evidence/subtasks；非完整工具轨迹产品化 |
| 产物下载与历史工作区 | **部分实现** | API list/download + 前端链接；无多任务历史产品库 UI |

---

## G. 差距优先级（阶段规划输入）

| 优先级 | 项 | 原因 |
|--------|-----|------|
| P0 | 独立最小前端+API 闭环 | 演示与产品边界 |
| P0 | Cross-Encoder 或 **改简历** | 当前表述与源码冲突 |
| P0 | 禁止伪造 0.62/0.84/82%/91%/77% | 无数据集 |
| P1 | LangGraph 自有编排图 | 支撑「多智能体工作流」叙事 |
| P1 | MCP 补检闭环 | 简历机制完整 |
| P1 | 真实 10 E2E / 20 离线跑通 | **阶段 6 已完成（fixture）** |
| P2 | Sandbox 产品化 | **阶段 5 已完成（有风险声明）** |
| P2 | 50 题 RAG 评测集 | 阶段 4 已有；可选 `--with-rag` |

---

## H. 阶段 2 完成后状态更新（2026-10-17）

| 项 | 新状态 | 证据 |
|----|--------|------|
| 独立 Vite 前端 + FastAPI | **已实现且已验证** | `apps/scholarflow-*`，Phase1 E2E |
| 自有 LangGraph StateGraph | **已实现且已验证** | `graph/workflow.py` + 13 pytest |
| 四类工作流入口 | **已实现且已验证** | kind 枚举 + 单测 |
| 论文∥仓库真实并行 | **已实现且已验证** | `test_paper_and_repo_parallel_overlap` |
| 实验依赖上游输出 | **已实现且已验证** | `upstream_*_ids` |
| Review 通过/失败 | **已实现且已验证** | `force_fail_review` API/图测 |
| 失败不伪装成功 | **已实现且已验证** | assemble skipped + status=failed |
| 9 产物聚合 | **已实现且已验证** | `build_task_artifacts` |
| 前端真实子任务状态 | **已实现且已验证** | 轮询 `subtasks`（需手测 UI；API 已测） |
| Cross-Encoder / 50 题 / 补检 / Sandbox 轻量版 | **阶段 4–5 已落地；指标部分未达简历目标** | 见 phase4 审计 + phase5 |
| Live MCP 默认路径 | **部分实现** | live 可选，默认 fixture |
| Agent Bench 20+10 / Golden / 90%·97% | **阶段 6 已落地；本机 fixture 实测达标** | 见 `docs/scholarflow-phase6.md` + audit |
| 本机 Vite+API 稳定演示 | **阶段 7 已落地；fixture 冒烟 8/8** | 见 `docs/scholarflow-phase7.md` |

---

## I. 简历要求最终验收总表（阶段 7 + 精细化收尾）

状态枚举：`已实现且已验证` | `部分实现` | `未达标` | `存在风险` | `不可宣称`

详见 [`docs/scholarflow-final-polish.md`](scholarflow-final-polish.md)。

| 简历/目标项 | 最终状态 | 证据 / 备注 |
|-------------|----------|-------------|
| 独立 FastAPI + Vite | 已实现且已验证 | phase7 启动；`/health` + `:5173` |
| LangGraph 科研工作流 | 已实现且已验证 | 四类工作流；并行时间窗；Review fail；**节点多为确定性+fixture，非每节点 LLM** |
| MCP 工具层 | 已实现且已验证（协议）；live 拉数部分实现 | fixture 默认；live 可选 |
| 9 类产物 + Schema | 已实现且已验证 | 落盘 + Pydantic；Bench schema 事件 10/10 |
| Hybrid RAG + 引用约束 | 已实现且已验证 | 检索拼装+引用；收尾后拒答 5/5 |
| Cross-Encoder | 部分实现 / 已验证路径 | ONNX MiniLM 可加载；勿把 stub 当生产 CE |
| MCP 自动补检 | 部分实现 | 机制有；↓77% **未达标**（本轮全量 56%、同主题 40%） |
| 忠实度 0.62→0.84 | 未达标 / 存在风险 | **0.62 无原始记录**；收尾 baseline faith **0.58**（拒答收紧权衡） |
| Top-5 / 引用简历数 | 部分支持 / 存在风险 | 收尾 baseline Top-5 **0.68**；引用结构 ~0.98≠强语义 91% |
| 拒答（q43–q47） | 已实现且已验证（收尾后） | refuse_accuracy **1.0**；历史失败已对照 |
| 20 离线 + 10 E2E | 已实现且已验证（fixture） | 完成率 90%；正确率 100% |
| Schema ≥97% | 已实现且已验证（事件口径） | 100%（10/10） |
| Golden 版本回归 | 已实现且已验证 | snapshot + compare |
| 任务状态持久化 | 已实现且已验证（轻量） | `task_state.json`；非 Redis |
| Sandbox | 已实现且已验证（原型） | Docker 含 no-new-privileges；**不可宣称**生产隔离 |
| 本机演示可复现 | 已实现且已验证（fixture） | phase7 smoke 8/8；**≠ live** |

---

## J. 阶段 8 对话式 Agent（8.0–8.6 已验收）

| 子阶段 | 目标 | 状态 | 证据 |
|--------|------|------|------|
| 8.0 | 独立 DeepSeek ChatDeepSeek Client + 真实 ping | **已实现且已验证** | `docs/scholarflow-phase8-0.md`；`scholarflow_api/llm/` |
| 8.1 | ConversationStore + 会话 REST 持久化 | **已实现且已验证** | `docs/scholarflow-phase8-1.md`；`scholarflow_api/chat/` |
| 8.2 | Tool-calling Agent（bind_tools 闭环） | **已实现且已验证** | `docs/scholarflow-phase8-2.md`；`chat/agent.py` + Live |
| 8.3 | 真 SSE 流式（token/tool 事件） | **已实现且已验证** | `docs/scholarflow-phase8-3.md`；`/turns/stream` Live |
| 8.4 | Agent 委托科研工作流（TaskStore） | **已实现且已验证** | `docs/scholarflow-phase8-4.md`；fixture 工作流 Live |
| 8.5 | Chat UI（默认 Chat + 工作台保留 + 真实 REST/SSE） | **已实现且已验证** | `docs/scholarflow-phase8-5.md`；`apps/scholarflow-web`；浏览器 + API E2E |
| 8.6 | 最终系统评测与发布验收（12 项映射 + Mock/Live/RAG/浏览器分报） | **已实现且已验证（有条件）** | `docs/scholarflow-phase8-6.md`；Live 8/8；RAG baseline 独立目录；**≠** 0.62/77% 达标 |
| 8.6b | 科研工作流主题相关性（压缩感知错配修复） | **已实现且已验证（最小）** | `docs/scholarflow-research-relevance-audit.md` §1–7；`sf-5787ead265f0` 保留；`sf-rel-e2e-1792380524` 诚实 failed |
| 8.6c | 修复后定向复验（清洗 / 429 / 成功·失败分报） | **适配器 live 已验证** | audit §8；`last_relevance_live_probe.json`；429 Retry-After + 外层停重试 |
| 8.6d | 完整 live 科研工作流 E2E | **系统 succeeded；严格主题纯度曾条件通过** | `docs/scholarflow-research-e2e-validation.md`；`sf-12fa1e2791cb`（历史快照保留） |
| 8.6e | 论文相关性三级分级 + 下游约束 | **已实现且已验证（单测/回归）** | `docs/scholarflow-relevance-final-polish.md`；`evidence_gate.classify_paper_relevance` |
| 8.6f | fcb379 定点修复（旧进程+查询/实验/Review） | **代码已修；完整 live 九产物因 GitHub 网络未达标** | `docs/scholarflow-fcb379-hotfix.md`；`sf-fcb37987da7b` 保留；论文 live+分级通过；仓库 API 连接失败 |

**三分离（8.1）：** 会话消息（`data/conversations/`）≠ 科研任务（`data/tasks/`）≠ RAG 产物/索引。
