# ScholarFlow 独立重构 — 阶段 0 项目审计报告

> 审计日期：2026-10-17  
> 审计范围：本地仓库 `E:\AgentProject\scholarflow_project`（ScholarFlow baseline + ScholarFlow 扩展）  
> 原则：**只读审计**；不删除 ScholarFlow；不 `git reset --hard` / `docker compose down -v`；不改业务代码。  
> 状态口径：`已实现且已验证` / `已实现但未验证` / `部分实现` / `尚未实现` / `存在风险`

---

## 1. 工作区与版本边界

### 1.1 Git

| 项 | 事实 |
|----|------|
| 分支 | `master` @ `930042d`（`baseline: initial import`） |
| ScholarFlow 相关 | **大量未提交**改动与未跟踪目录（见下） |
| 危险操作 | **禁止**：`reset --hard`、`clean -fd`、`compose down -v` |

**已修改（跟踪文件）：** `.env.example`、`.gitignore`、skill storage、`pyproject.toml`/`uv.lock`、`docker-compose-dev.yaml`（含 frontend Webpack / `.next` volume）、`extensions_config.example.json`

**未跟踪（ScholarFlow 主体）：**

- `backend/packages/harness/scholarflow/scholar/`
- `extensions/scholar_mcp/`
- `skills/custom/{scientific-research-orchestration,paper-evidence-extraction,repository-analysis,experiment-plan}/`
- `evaluation/`
- `docs/scholar-flow/`
- `backend/tests/test_scholar_*.py`、`test_evaluation_scorer.py`
- `scripts/demo_scholar_rag.ps1`、`scripts/verify_scholarflow.sh`

### 1.2 LICENSE 与复用约束

- 文件：`LICENSE` — **MIT**，Copyright Bytedance / ScholarFlow Authors。
- 含义：可复用、修改、再分发，但须保留版权声明。
- 独立 ScholarFlow 产品化时：建议 **fork 架构思路 + 选择性移植代码**，独立品牌与独立前端；若继续依赖 ScholarFlow 运行时，文档中必须标注上游来源。

### 1.3 ScholarFlow 与 ScholarFlow 边界（已证实）

| 归属 | 内容 |
|------|------|
| **ScholarFlow 底座** | LangGraph Lead Agent、FastAPI Gateway、MCP Client 加载、`task` Sub-Agent、Sandbox Provider、Next.js 前端、Docker Compose |
| **ScholarFlow 自有** | `scholarflow/scholar/*` Schema/产物/RAG；`extensions/scholar_mcp`；4 个 custom Skills；`evaluation/*`；`docs/scholar-flow/*` |
| **耦合点** | Scholar 工作流 = Skill Prompt + ScholarFlow `task` + MCP 工具名；**没有**独立的 `StateGraph` 名叫 ScholarFlow |

---

## 2. 已验证可运行能力（证据）

| 能力 | 证据 | 状态 |
|------|------|------|
| Hybrid RAG CLI | `uv run python evaluation/run_rag_demo.py` 曾打印 `=== DEMO OK ===`；索引 `evaluation/rag_index`；Top 证据含 `paper-2404.07220v2` | **已实现且已验证** |
| 9 件套产物样本 | `docs/scholar-flow/samples/rag-test-001/`、`evaluation/results/rag-survey/` | **已实现且已验证**（样本/单任务） |
| Schema / MCP 单测 | `backend/tests/test_scholar_schemas.py`、`test_scholar_rag.py`；`extensions/scholar_mcp/tests/` | **已实现且已验证**（单元） |
| E2E 产物打分 | `evaluation/reports/e2e-rag-test-001.json`：`task_count=1`，`e2e_pass_rate=1.0`，9 产物齐全 | **部分实现**（仅 1 个真实任务，非 10/10） |
| Golden 离线打分 | `evaluation/tasks.json` 20 题 + `run_benchmark.py --mode golden`；报告 `golden-baseline.*` | **已实现但未验证**（golden 多为合成/fixture 路径，非 20 次真实 Agent 跑通） |
| Docker UI 全栈演示 | `localhost:2026` 在 8GB 机上曾通首页/`chats` 307→login；前端易 `ENOMEM` | **存在风险**（资源，非业务逻辑错误） |

---

## 3. 模块级审计摘要

### 3.1 多智能体工作流

| 点 | 事实 | 状态 |
|----|------|------|
| 4 类科研工作流 | 4 个 Skill：编排 / 论文证据 / 仓库分析 / 实验方案 | **部分实现**（Skill 编排，非独立 LangGraph 子图） |
| 并行 Sub-Agent | 编排 Skill 写明 Phase2 最多 3 路 `task`；依赖 ScholarFlow `MAX_CONCURRENT_SUBAGENTS` | **部分实现** |
| 显式依赖 DAG / 拓扑调度器 | **无**独立调度器；阶段顺序写在 SKILL.md | **尚未实现**（相对简历「依赖调度」） |
| 失败/超时/重试（工作流级） | ScholarFlow subagent 有失败状态；Scholar **无**专用失败聚合策略代码 | **部分实现** / **存在风险** |
| 前端真实执行状态 | ScholarFlow 聊天流式；**无** Scholar 任务看板/子任务树 | **尚未实现**（独立产品视角） |

### 3.2 MCP + 结构化产物

| 点 | 事实 | 状态 |
|----|------|------|
| 独立 MCP Server | `extensions/scholar_mcp`，stdio，`@mcp.tool` | **已实现且已验证**（单测 + 曾在 Docker 调用） |
| arXiv / GitHub | `search_academic_papers`、`get_repository_overview` + resilience | **已实现且已验证** |
| Schema / 报告 / 矩阵 / 组装 | `validate_evidence_schema`、`build_research_report`、`generate_research_matrix`、`assemble_task_artifacts` | **已实现且已验证** |
| Agent 经 MCP Client 调用 | 依赖 ScholarFlow MCP 加载 + `extensions_config`；非 Scholar 自研 Client | **部分实现**（能力在底座） |
| 7 类 Pydantic | 核心实体：`ResearchPlan`、`PaperEvidence`、`RepositoryEvidence`、`ExperimentPlan`、`ReviewFinding`、`SourceRecord` + `DateRange`；另有 Collection 包装 | **已实现但未验证**（「7」需口径固定） |
| 9 类产物 | `paths.REQUIRED_ARTIFACTS` 明确 9 文件名 | **已实现且已验证** |

### 3.3 可追溯 RAG

| 点 | 事实 | 状态 |
|----|------|------|
| 索引 / chunk / 元数据 | `rag/{chunking,store,pipeline,retrieve,config}.py` | **已实现且已验证**（CLI） |
| Dense + BM25 + RRF | 代码与 demo 配置一致（bge-small + BM25+jieba + RRF） | **已实现且已验证** |
| Cross-Encoder 重排 | **未实现**；实际为 `hybrid-score`；`store.py` 注释写明可后补 | **尚未实现**（相对简历）→ **存在风险**（简历不符） |
| evidence_id / source_url | 答案绑定；模型强制校验 `source_url` | **已实现且已验证** |
| 证据不足 → MCP 补检 | 仅返回 `need_mcp_fallback`；**无**自动补检闭环 | **部分实现** |
| 50 题 QA + 忠实度 0.62→0.84 等 | **仓库无**固定 50 题集、无对应实验报告脚本产出这些数 | **尚未实现** / **存在风险**（不可写进报告为已达） |

### 3.4 评测与回归

| 点 | 事实 | 状态 |
|----|------|------|
| 20 离线任务定义 | `evaluation/tasks.json` → 20 | **已实现但未验证**（真实 Agent 全量未跑） |
| 10 E2E 定义 | `benchmark_tasks.json` → 10 | **已实现但未验证** |
| Schema / 完整性 / 溯源检查 | `scorer.py` / `metrics.py` 等 | **部分实现**（有自动化；口径需固化） |
| Golden Answer 版本回归 | `run_benchmark.py --mode golden` + `compare_runs.py` | **部分实现** |
| 端到端完成率 90% / Schema 97% | 现有报告：golden 合成高分；真实 artifacts **1/1=100%** — **不能等同简历数字** | **存在风险** |

### 3.5 Sandbox

| 点 | 事实 | 状态 |
|----|------|------|
| ScholarFlow Sandbox | `LocalSandbox` / `AioSandbox` 等，线程级路径映射 | **已实现且已验证**（底座） |
| Scholar 专用沙箱策略 | 无独立「实验脚本可控执行」产品层；产物写在 `/mnt/user-data/outputs` | **部分实现** / 相对简历 **尚未实现** 独立能力叙事 |

### 3.6 前端

| 点 | 事实 | 状态 |
|----|------|------|
| ScholarFlow Next.js UI | 可聊天；8GB 下 Docker 前端易 OOM | **存在风险** |
| 独立 ScholarFlow 品牌前端 | **无** | **尚未实现** |

---

## 4. 可直接复用 vs 必须重做

### 4.1 优先复用（移植或抽包）

1. `scholarflow/scholar/models.py` + `validation.py` + `paths.py` + `artifacts.py` + `matrix.py` + `report.py` + `aggregation.py`
2. `scholarflow/scholar/rag/**`（明确标注重排为 hybrid-score；Cross-Encoder 作为阶段 4 增量）
3. `extensions/scholar_mcp/**`（含 arxiv/github/resilience）
4. `skills/custom/**`（作为工作流规格/Prompt 基准，可演进为 LangGraph 节点提示）
5. `evaluation/scorer.py`、`metrics.py`、任务 JSON 骨架、`run_rag_demo.py`
6. 样本产物与 data-contracts 文档

### 4.2 必须新开发 / 大幅改造

1. **独立 ScholarFlow 前端**（品牌 + 任务/子任务/证据/产物视图）— 不建议只改 ScholarFlow 文案
2. **独立 LangGraph 科研 StateGraph**（编排节点、显式依赖、并行、失败策略）— 不能仅靠 Skill Prompt 冒充
3. **Cross-Encoder 重排 + 50 题评测集 + 基线/完整/补检对照实验**
4. **MCP 补检自动闭环**（`need_mcp_fallback` → 调工具 → 再入索引/生成）
5. **Sandbox 产品能力**（受控脚本执行边界，轻量方案适配 8GB）
6. **轻量 FastAPI 应用壳**（可嵌 ScholarFlow 运行时或渐进替换；阶段 1 最小闭环）
7. **真实 20+10 跑通与版本化 Golden**（禁止硬编码简历指标）

### 4.3 架构差距（一句话）

当前 = **ScholarFlow 通用 Agent 平台 + Scholar 域扩展（Skill/MCP/Schema/RAG/评测脚手架）**  
目标 = **独立品牌的科研多智能体产品**，简历每项均有 **自有调用链 + 可复现评测**。

---

## 5. 8GB 内存分阶段运行建议（审计结论）

| 阶段 | 建议进程 | 禁止同时开 |
|------|----------|------------|
| RAG/评测脚本 | 宿主机 `uv` + 可选 lite/fastembed | Docker 全栈 + Dify |
| 阶段 1 最小闭环 | FastAPI + 单图 + Vite 前端（本机） | Next.js Docker Turbopack/重 Webpack 全量 |
| 全栈演示 | 仅 `scholarflow-dev` 四容器；Docker 内存 ≥5–6GB WSL | 同机其他 compose |
| 多模型 / 多沙箱容器 | 默认不做 | — |

已证实：Docker Total Memory ≈ **4.8GiB**（`.wslconfig memory=5GB`）时，frontend 编译峰值可达 **~3.2GiB**，仍紧；独立前端应优先 **Vite 轻量方案**。

---

## 6. 阶段 0 结论

1. ScholarFlow **已有可复用核心**（MCP、Schema、9 产物、Hybrid RAG CLI、评测脚手架、4 Skills）。  
2. 与简历差距最大处：**Cross-Encoder、50 题指标、独立多 Agent 图、独立前端、Sandbox 叙事、真实 20/10 全量验证**。  
3. **不得**把 golden 合成分数或 hybrid-score 写成 Cross-Encoder / 0.84 忠实度。  
4. 阶段 1 起再动大规模代码；本阶段仅产出审计与矩阵（本文件 + 另两份）。
