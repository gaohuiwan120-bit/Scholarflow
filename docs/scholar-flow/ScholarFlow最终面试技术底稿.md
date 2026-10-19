# ScholarFlow 最终面试技术底稿

> 用途：大模型应用开发岗位面试「项目深挖」唯一底稿。  
> 依据：当前仓库源码 +  
> `ScholarFlow项目源码与面试分析报告.md` / `RAG链路面试专项.md` /  
> `ScholarFlow简历与真实源码差异核验报告.md` / `ScholarFlow评测复现方案.md`  
> **约束**：不编造未实现模块；指标只写仓库报告能支撑的数字。

---

## 一、项目背景与功能

### 1.1 解决什么问题

科研/技术调研常见失败模式：

- 模型凭参数记忆编造论文、arXiv ID、GitHub star；
- 文献、代码、实验方案割裂，难以交叉验证；
- 输出是一篇散文，无法做结构校验与回归评测。

ScholarFlow 把调研变成：**可并行的证据采集 → 结构化落盘 → 审查聚合 →（可选）产物库可追溯追问**。

### 1.2 用户与输入

- **用户**：做文献+开源调研的 ML/Agent 工程师或研究者。  
- **输入**：自然语言调研请求，例如「调研 RAG 主流架构与开源实现，task id: rag-test-001」。  
- **入口**：ScholarFlow Web（`:2026`）或 Gateway 对话 API。

### 1.3 最终输出

虚拟路径 `/mnt/user-data/outputs/<task-id>/` 下的 **9 类产物**（见第四节）。  
追问场景还可得到带 `evidence_id`/`source_url` 的 RAG 回答 JSON。

### 1.4 核心业务价值

1. **可验证**：证据来自 arXiv/GitHub MCP，而非纯生成。  
2. **可协作**：论文/仓库/实验三路 Sub-Agent 并行。  
3. **可校验**：Pydantic Schema + 评测硬门槛。  
4. **可复用**：产物索引进 Hybrid RAG，降低重复外检。

### 1.5 面试 90 秒项目介绍（可背）

> ScholarFlow 是我在 ScholarFlow 上做的科研调研扩展，不是从零重写 Agent 框架。用户提一个调研问题后，Lead Agent 加载编排 Skill，先写研究计划，再最多并行三个 Sub-Agent：分别按论文 Skill、仓库 Skill、实验 Skill 工作；论文和仓库侧通过我们自研的 scholar_mcp 调 arXiv 和 GitHub，结果落成 Pydantic 约束的结构化证据。编排侧做证据审查，再调 MCP 生成矩阵、校验 Schema、组装九类产物——包括报告、计划、论文/仓库证据与矩阵、实验方案、审查和来源清单。  
> 在此之上我做了产物库 Hybrid RAG：用 bge-small-en-v1.5 做稠密向量、BM25 做稀疏、RRF 融合、hybrid-score 重排；追问时强制带 evidence_id 和 source_url，证据不够就返回 need_mcp_fallback 提示再外检。评测上我们有 20 个离线任务定义和 10 个 E2E case，Golden 模式硬门槛 10/10 通过，真实 rag-test-001 产物也过了结构门槛。重点是可追溯、可评分，而不是再造一套 LangGraph。

---

## 二、Agent 完整架构

### 2.1 四个 Skill（准确名称与职责）

| Skill `name` | 路径 | 职责 |
|--------------|------|------|
| `scientific-research-orchestration` | `skills/custom/scientific-research-orchestration/SKILL.md` | Plan→Delegate→Review→Aggregate→Deliver |
| `paper-evidence-extraction` | `skills/custom/paper-evidence-extraction/SKILL.md` | 调 arXiv MCP，写 `paper_evidence.json` |
| `repository-analysis` | `skills/custom/repository-analysis/SKILL.md` | 调 GitHub MCP，写 `repository_evidence.json` |
| `experiment-plan` | `skills/custom/experiment-plan/SKILL.md` | 基于证据写 `experiment_plan.md` |

**没有**四个独立 Python `Agent` 类。

### 2.2 Lead / Sub-Agent / 并行 / 状态——真实机制

| 概念 | 真实机制 |
|------|----------|
| Lead Agent | ScholarFlow `ScholarFlow/agents/lead_agent/agent.py`（LangGraph 运行时） |
| Skill 加载 | Skill 激活中间件把 SKILL.md 注入上下文 |
| Sub-Agent | Lead 调用内置工具 `task(subagent_type="general-purpose", prompt=...)` |
| 并行 | 编排 Skill 要求最多 **3** 路并发 `task`；框架有 Subagent 上限 |
| 「依赖调度」 | Skill 规定阶段顺序，**无**独立 DAG 调度器类 |
| 状态传递 | 主要靠 Sandbox 文件 + tool 返回；对话状态在 ScholarFlow 线程/checkpointer |

### 2.3 编排阶段（Skill 明文）

```
Phase1 Plan      → research_plan.json
Phase2 Delegate  → 并行 task ×≤3（论文∥仓库∥实验）
Phase3 Review    → evidence_review.json
Phase4 Aggregate → MCP 矩阵/校验/组装 → 写齐 9 文件
Phase5 Deliver   → 用户摘要
（可选）index_research_artifacts → rag_query
```

### 2.4 源码函数调用链（调研主路径）

```
用户消息
  → Gateway / LangGraph 运行时
  → Lead Agent（lead_agent/agent.py）
  → 激活 scientific-research-orchestration Skill
  → LLM 决策 write_file → research_plan.json
  → LLM 发起 task() × N（≤3）
       → Sub-Agent + paper-evidence-extraction
            → scholar_mcp_search_academic_papers
                 → clients/arxiv.search_academic_papers
            → scholar_mcp_validate_evidence_schema
            → write_file paper_evidence.json
       → Sub-Agent + repository-analysis
            → scholar_mcp_get_repository_overview
                 → clients/github.get_repository_overview
            → write_file repository_evidence.json
       → Sub-Agent + experiment-plan
            → 读证据 → write_file experiment_plan.md
  → Lead：写 evidence_review.json
  → scholar_mcp_generate_research_matrix / validate_* / assemble_task_artifacts
       → artifacts.build_task_artifacts
            → matrix / report / aggregation
  → write_file 补齐 9 产物
  → 回复用户
```

---

## 三、MCP 完整实现

**注册文件：** `extensions/scholar_mcp/scholar_mcp/server.py`  
**框架：** FastMCP，`mcp = FastMCP("scholar_mcp")`  
**运行时名前缀：** ScholarFlow 一般为 `scholar_mcp_<tool>`  
**启用配置：** `extensions_config.json` → `mcpServers.scholar_mcp`

| 工具（逻辑名） | 注册函数 | 主要输入 | 输出结构 | 与 Agent 关系 |
|----------------|----------|----------|----------|----------------|
| `search_academic_papers` | async 同名 | `query`, `max_results`, `category?` | `{"items":[Paper…]}` JSON 字符串 | 论文 Skill 主工具 |
| `get_repository_overview` | async 同名 | `repository` (owner/name) | 仓库概览 JSON | 仓库 Skill 主工具 |
| `extract_uploaded_paper` | 同名 | `file_path`, `title?` | 含 `evidence_id`/`content_preview` | 上传文本预览（非 PDF OCR） |
| `generate_research_matrix` | 同名 | `kind`=`paper|repository`, `items_json` | CSV 字符串 | 编排聚合阶段 |
| `validate_evidence_schema` | 同名 | `filename`, `payload_json` | `{"valid":true,"payload":…}` | 写盘前校验 |
| `build_research_report` | `build_research_report_tool`（`name="build_research_report"`） | 各 JSON 字符串 | `research_report.md` 文本 | 报告生成 |
| `list_task_artifacts` | 同名 | `task_id` | 9 路径 map | 核对路径 |
| `assemble_task_artifacts` | 同名 | plan/papers/repos/experiment/review JSON | `contents` 含 9 文件 | 一站式组装 |
| `index_research_artifacts` | 同名 | `artifacts_dir`, `task_id?` | 索引统计 JSON | RAG 入库 |
| `rag_query` | 同名 | `question`, `top_k`, `verified_only` | answer/evidence/need_mcp_fallback | RAG 追问 |

**辅助：** `coerce_items` / `normalize_paper_item` / `normalize_repo_item` / `parse_*`；HTTP 重试 `clients/resilience.with_retry`。

**交互关系：** Lead/Sub-Agent 通过 LangChain MCP 适配器发起 tool call → stdio MCP Server 执行 → JSON/CSV/文本作为 ToolMessage 回到 Agent → Agent 再 `write_file` 或继续推理。

---

## 四、科研产物管理

### 4.1 九类产物

定义：`scholarflow/scholar/paths.py::REQUIRED_ARTIFACTS`

| 文件名 | 格式 | 用途 |
|--------|------|------|
| `research_report.md` | Markdown | 综合研究报告 |
| `research_plan.json` | JSON | 研究计划（ResearchPlan） |
| `paper_evidence.json` | JSON | 论文证据集合 |
| `paper_matrix.csv` | CSV | 论文对比矩阵 |
| `repository_evidence.json` | JSON | 仓库证据集合 |
| `repository_matrix.csv` | CSV | 仓库对比矩阵 |
| `experiment_plan.md` | Markdown | 实验方案 |
| `evidence_review.json` | JSON | 证据审查结论 |
| `sources.json` | JSON | 来源清单 |

组装：`scholarflow/scholar/artifacts.py::build_task_artifacts`。

### 4.2 Pydantic 核心模型（`models.py`）

| 模型 | 关键字段 | 验证 |
|------|----------|------|
| `DateRange` | `start`, `end` | 可选嵌套 |
| `ResearchPlan` | `task_id`, `title`, `objective`, `research_questions`, `search_queries`, `code_search_queries`, `date_range`, `expected_outputs`, `completion_criteria` | 模型校验 |
| `PaperEvidence` | `evidence_id`, `title`, `source_url`, `authors`, `year`, `identifier`, `research_problem`, `methodology`, `key_findings`, `limitations`, `evidence_level`, `verification_status`… | **`source_url` 非空** `@field_validator` |
| `RepositoryEvidence` | `evidence_id`, `repository`, `source_url`, `description`, `architecture_summary`, `key_modules`, `verification_status`… | 模型校验 |
| `ExperimentPlan` | `objective`, `hypotheses`, `datasets`, `baselines`, `proposed_pipeline`, `evaluation_metrics`, `ablation_studies`, `risks`… | 模型校验 |
| `ReviewFinding` | `claim`, `related_evidence_ids`, `status`, `reason`, `recommended_action` | `status` 枚举 |
| `SourceRecord` | `evidence_id`, `kind`, `title`, `url`, `accessed_at`, `verification_status` | `kind` 枚举 |

**Collection：** `PaperEvidenceCollection` / `RepositoryEvidenceCollection` / `ReviewFindingCollection` / `SourceCollection`（`items` 列表）。

**JSON 校验入口：** `validation.py::_SCHEMA_MAP` 注册 5 个文件名 → `validate_json_artifact`；MCP `validate_evidence_schema` 封装。

**口径：** 面试说「6 个核心业务模型 + DateRange」或「5 类 JSON Schema + ExperimentPlan」；避免含糊「7 类」对不上名单。

---

## 五、Hybrid RAG 完整实现

### 5.1 产物索引入口

| | |
|--|--|
| 文件 | `server.py` → `index_research_artifacts`；`pipeline.py` → `index_artifacts_dir` |
| 输入 | `artifacts_dir`, 可选 `task_id` / `RagConfig` |
| 输出 | `{upserted, total, backend, embed_model, persist_dir, …}` |
| Demo | `evaluation/run_rag_demo.py` |

### 5.2 JSON/Markdown 解析

| | |
|--|--|
| 文件 | `rag/chunking.py` → `load_chunks_from_artifacts_dir` |
| 输入 | 产物目录 Path |
| 输出 | `list[EvidenceChunk]` |
| 行为 | `json.loads` 读 evidence；`read_text` 读 md/json；**无 PDF OCR** |

### 5.3 Chunk 策略

| 类型 | 策略 |
|------|------|
| paper/repo | 一条证据 ≈ 一 chunk；字段拼接后 `_clip`≤1800 |
| report/experiment/plan/review | **固定约 1200 字符窗口**；片长 clip 1500；&lt;40 丢弃 |
| 元数据 | `evidence_id`, `kind`, `source_url`, `verification_status`, `task_id`, `metadata` |

**非语义切分器。**

### 5.4 Embedding

| | |
|--|--|
| 文件 | `rag/store.py` → `embed_texts` / `_load_embedder`；`rag/config.py` → `RagConfig` |
| 默认模型 | `BAAI/bge-small-en-v1.5` |
| 维度 | **384** |
| 后端 | fastembed（优先）；无则 `lite` hashing-bow（降级） |
| Query/Doc | **同一** `embed_texts` |

### 5.5 BM25

| | |
|--|--|
| 文件 | `rag/retrieve.py` → `_BM25`, `_tokenize` |
| 原理 | Okapi 风格：`idf * (tf*(k1+1))/(tf+k1*(1-b+b*dl/avgdl))`，默认 k1=1.5, b=0.75 |
| 分词 | jieba；失败则中文 bigram + 拉丁 token |
| 语料 | `bm25_corpus.json` / `corpus.json` |

### 5.6 Dense 检索

| | |
|--|--|
| 文件 | `hybrid_retrieve` |
| 行为 | `q_emb` 与全库向量 `_cosine`，取 top `recall_dense`（默认 **20**） |

### 5.7 RRF 融合

| | |
|--|--|
| 文件 | `retrieve.py` → `_rrf_fuse` |
| 公式 | \( \mathrm{RRF}(d)=\sum_{r\in R}\frac{1}{k+\mathrm{rank}_r(d)} \) |
| 参数 | `k = RagConfig.rrf_k` 默认 **60**；融合 Dense 与 BM25 两路 ID 列表 |

### 5.8 hybrid-score 重排

| | |
|--|--|
| 文件 | `store.py` → `hybrid_score_rerank` |
| 公式 | `0.55 * lexical_overlap + 0.45 * normalized_dense` |
| 额外 | paper/repo +0.08；有 source_url +0.05；关键词 tip +0.03 |
| **不是** | Cross-Encoder / bge-reranker |

### 5.9 存储

| 层 | 路径/实现 |
|----|-----------|
| 必写 | `evaluation/rag_index/corpus.json`, `vectors.json`, `bm25_corpus.json`, `index_meta.json` |
| 可选 | Chroma `PersistentClient`，collection `scholarflow_evidence`，`hnsw:space=cosine` |
| 代码 | `store.upsert_chunks` |

检索主路径读 JSON 向量做余弦；Chroma 为双写。

### 5.10 evidence_id / source_url

- 生成侧：`normalize_*` 补 ID；`PaperEvidence` 强制非空 URL。  
- RAG 侧：答案 bullet：`〔evidence_id (source_url)〕`，`evidence[]` 结构化返回。

### 5.11 need_mcp_fallback

- `rag_answer` 无强证据时：`need_mcp_fallback=true` + 提示文案。  
- **无**硬编码「自动再调 arXiv」；是否补检取决于 Lead 是否再发起 tool call。

### 5.12 返回 Lead Agent

```
rag_query → json.dumps(rag_answer(...)) → MCP ToolMessage → Lead LLM
```

返回字段：`question`, `confidence`, `answer`, `evidence`, `need_mcp_fallback`, `retrieval`。

**注意：** `rag_answer` **不调用 LLM**；是 retrieve-and-cite 模板拼接。

### 5.13 RAG 调用链（索引+检索）

```
index_research_artifacts
  → index_artifacts_dir
    → load_chunks_from_artifacts_dir
    → upsert_chunks → embed_texts → 落盘/Chroma

rag_query
  → rag_answer
    → hybrid_retrieve
      → embed_texts(query)
      → _BM25.get_scores
      → _rrf_fuse
      → hybrid_score_rerank (+ bonus)
    → 拼 answer / evidence JSON
  → 返回 Lead
```

---

## 六、关键技术取舍（源码视角）

| 问题 | 源码依据的答案 |
|------|----------------|
| 为何 Skill 协作？ | 工作流写在 SKILL.md，热更新、不改 Lead；角色边界清晰 |
| 为何 MCP？ | 外检与确定性逻辑（矩阵/校验/组装/RAG）进程隔离、可单测；`scholar_mcp` 独立包 |
| 为何 Pydantic？ | 统一证据形状；`validate_json_artifact` 阻断脏 JSON |
| 为何产物要 RAG？ | 调研成本高；产物已结构化，适合二次问答与降外检 |
| 为何 Dense+BM25？ | 语义（Blended/hybrid）+ 精确（arxiv id、仓库名）互补 |
| 为何 RRF？ | 无需分数对齐即可融合排序列表；实现简单（`_rrf_fuse`） |
| 为何 hybrid-score 而非 Cross-Encoder？ | 当前依赖轻、可离线；代码注释写明 without CrossEncoder；简历勿写 CE |
| 为何 rag_answer 不调 LLM？ | 保证每条结论可挂证据，评测引用更可控；润色留给 Lead |
| 为何保留 evidence_id/URL？ | 防幻觉、可追溯、矩阵/审查/RAG 全链路对齐 |

---

## 七、评测与性能

### 7.1 当前真实报告（可讲）

| 来源 | 结果 |
|------|------|
| `evaluation/reports/golden-baseline.json` | mode=golden，**10** tasks，`e2e_pass_rate=1.0`，`average_score≈0.993` |
| `evaluation/reports/e2e-rag-test-001.json` | mode=artifacts，**1** task，`e2e_pass_rate=1.0`，`score=1.0` |
| 任务定义 | `tasks.json` **20** 条；`benchmark_tasks.json` **10** 条 |

### 7.2 原始计算公式（现有代码）

```text
artifact_completeness = |present artifacts| / 9

schema_validity = |JSON files passing Pydantic| / 5
  # research_plan, paper_evidence, repository_evidence, evidence_review, sources

e2e_pass_gate = 1 iff
  completeness==1 AND schema==1 AND url_validity>=0.8 AND topic_relevance>=0.5

e2e_pass_rate = |{task | e2e_pass}| / N
```

实现：`evaluation/metrics.py`, `quality_metrics.py`, `scorer.py`。

### 7.3 历史待核实指标（单列，勿当已测）

| 指标 | 状态 |
|------|------|
| 忠实度 0.62→0.84 | 无题集/无报告 |
| Hit@5 82% | 无 gold 标注评测 |
| 引用准确率 91% | 无审计脚本结果 |
| MCP 调用↓77% | 无 A/B tool 日志统计 |
| E2E 完成率 90% | 与现报告 100% 冲突 |
| Schema 97% | 与现报告 100% 冲突 |

方案见 `ScholarFlow评测复现方案.md`；**未完成前面试不要声称已达到这些数。**

---

## 八、面试高危问题（50 题）

每题格式：**问题 → 60 秒口述 → 源码 → 追问**。

---

**1. ScholarFlow 和 ScholarFlow 什么关系？**  
口述：扩展包，Skill+MCP+Schema+RAG+评测；复用 Lead/LangGraph/Sandbox，不改核心。  
源码：`skills/custom/*`，`extensions/scholar_mcp`，`scholarflow/scholar`  
追问：改没改 LangGraph？→ 没有自研 Scholar Graph。

**2. 有几个 Agent 类？**  
口述：无四个 Agent 类；四个 Skill 角色 + Lead + task Sub-Agent。  
源码：四个 `SKILL.md`；`lead_agent/agent.py`  
追问：Sub-Agent 类型？→ `general-purpose` + 提示加载 Skill。

**3. 并行怎么做？上限？**  
口述：编排 Phase2 最多 3 个并发 `task`；框架也有 Subagent 上限。  
源码：orchestration `SKILL.md` Phase2  
追问：谁保证不超 3？→ Skill 约束 + 框架中间件。

**4. 依赖调度在哪？**  
口述：Skill 阶段顺序，不是 DAG 引擎。  
源码：orchestration 五阶段  
追问：实验是否等论文？→ Prompt 要求读 evidence 文件，无代码屏障。

**5. LangGraph 图在哪？**  
口述：在 ScholarFlow Lead 运行时；scholar 目录无 StateGraph。  
源码：无 `scholarflow/scholar` 下 Graph  
追问：为何还写 LangGraph？→ 运行时技术栈。

**6. MCP 如何注册？**  
口述：FastMCP server，extensions_config 启用 stdio。  
源码：`server.py`，`extensions_config.example.json`  
追问：Docker 怎么指 Python？→ `SCHOLAR_MCP_PYTHON` + `PYTHONPATH`。

**7. arXiv 工具输入输出？**  
口述：`search_academic_papers(query,max_results,category)` → `items` JSON。  
源码：`server.py`，`clients/arxiv.py`  
追问：失败重试？→ `with_retry`。

**8. GitHub 403？**  
口述：需有效 `GITHUB_TOKEN`；客户端抛明确错误。  
源码：`clients/github.py`  
追问：无 token 能否继续？→ 仓库路降级，不应伪造 star。

**9. 九产物名单？**  
口述：背 `REQUIRED_ARTIFACTS` 九项。  
源码：`paths.py`  
追问：谁组装？→ `build_task_artifacts`。

**10. PaperEvidence 强制什么？**  
口述：`source_url` 非空 validator；要有 `evidence_id`。  
源码：`models.py`  
追问：缺 ID？→ `normalize_paper_item` 补。

**11. Schema 校验几个 JSON？**  
口述：validation 注册 5 个文件名。  
源码：`validation.py::_SCHEMA_MAP`  
追问：experiment 呢？→ 主要是 MD + ExperimentPlan 模型。

**12. Embedding 模型与维度？**  
口述：默认 bge-small-en-v1.5，384 维，fastembed。  
源码：`rag/config.py`，`store.embed_texts`  
追问：bge-m3？→ 非当前默认；可配置，勿谎称在跑。

**13. Chunk 怎么切？**  
口述：证据级一块；长文 1200 窗口；非语义切分。  
源码：`chunking.py`  
追问：overlap？→ 当前步进窗口，非重叠语义 chunker。

**14. BM25 参数？**  
口述：内置 _BM25，k1=1.5，b=0.75；jieba 分词。  
源码：`retrieve.py`  
追问：库？→ 自实现 Okapi 风格，非必须 rank_bm25 包。

**15. Dense 召回多少？**  
口述：`recall_dense` 默认 20。  
源码：`RagConfig`  
追问：相似度？→ 余弦 `_cosine`。

**16. RRF 公式与 k？**  
口述：1/(k+rank) 求和，k 默认 60。  
源码：`_rrf_fuse`  
追问：为何不用加权分？→ 免分数校准。

**17. 重排是 Cross-Encoder 吗？**  
口述：**不是**；hybrid-score 0.55 词面 + 0.45 dense。  
源码：`hybrid_score_rerank`  
追问：为何？→ 轻量可复现；CE 未落地。

**18. Top-K 默认？**  
口述：`rerank_top_k=5`。  
源码：`RagConfig`  
追问：verified_only？→ 可滤 verification_status。

**19. 向量库存哪？**  
口述：JSON 主存；可选 Chroma 双写。  
源码：`upsert_chunks`  
追问：查询是否必须 Chroma？→ 否，主路径 JSON 向量。

**20. rag_answer 调 LLM 吗？**  
口述：不调；拼接带引用 bullet。  
源码：`pipeline.rag_answer` docstring  
追问：那谁生成自然语言？→ Lead 可再润色 tool 结果。

**21. need_mcp_fallback 自动补检吗？**  
口述：只返回标志；Lead 是否再调 tool 不保证。  
源码：`rag_answer` 返回字段；Skills 无自动状态机  
追问：如何设计成自动？→ 外层策略/图节点（未实现）。

**22. 索引入口？**  
口述：MCP `index_research_artifacts` → `index_artifacts_dir`。  
源码：`server.py`，`pipeline.py`  
追问：索引什么？→ 已落盘 9 产物目录。

**23. 上传 PDF？**  
口述：`extract_uploaded_paper` 读文本前 4000 字；非 PDF 解析器。  
源码：`server.extract_uploaded_paper`  
追问：图片？→ 未做 OCR。

**24. 防幻觉三板斧？**  
口述：MCP 实拉；Schema+verification_status；RAG 强制引用/fallback。  
源码：Skills 规则 + models + rag_answer  
追问：审查？→ evidence_review status 枚举。

**25. assemble 做什么？**  
口述：去重、矩阵、报告、sources，一次出 9 文件 map。  
源码：`artifacts.build_task_artifacts`  
追问：去重？→ `aggregation.dedupe_*`。

**26. 矩阵列从哪来？**  
口述：`matrix.py` 固定列，由 PaperEvidence/Repo 填。  
源码：`scholarflow/scholar/matrix.py`  
追问：和 JSON 行数？→ 评测 `matrix_row_consistency`。

**27. Golden 和真实 E2E 区别？**  
口述：Golden 用合成产物打分；真实是沙箱 artifacts。  
源码：`run_benchmark.py` modes；报告 json  
追问：10 个都真人跑了？→ **没有**；真实完整评分约 1 个。

**28. e2e_pass_gate 条件？**  
口述：完整=1、schema=1、url≥0.8、topic≥0.5。  
源码：`quality_metrics.e2e_pass_gate`  
追问：pass rate？→ Golden 10/10；artifacts 1/1。

**29. Schema 通过率怎么算？**  
口述：每任务 5 个 JSON 校验通过数/5。  
源码：`scorer._schema_validity_score`  
追问：97%？→ 现报告是 100%；97% 无依据。

**30. 50 题忠实度？**  
口述：仓库无该评测；属待建（见复现方案）。  
源码：无  
追问：为何简历有？→ 应删；只讲硬门槛结果。

**31. Hit@5 82%？**  
口述：无 gold 题集评测结果；链路可测但数未建。  
源码：可调 `hybrid_retrieve`，无 eval 报告  
追问：怎么补？→ 标注 gold_evidence_id 后跑 Hit@5。

**32. MCP↓77%？**  
口述：无 A/B tool 日志统计；不能靠 fallback 推断。  
源码：无 eval_mcp_ab  
追问：怎么测才算？→ 计真实 tool 执行次数。

**33. FastAPI 你写了哪些路由？**  
口述：ScholarFlow 无独立 REST；走 Gateway 对话+MCP。  
源码：扩展在 skills/mcp/scholar  
追问：如何演示？→ UI 对话或 `run_rag_demo.py`。

**34. Docker 怎么跑 MCP？**  
口述：compose 注入容器内 python 与 PYTHONPATH，Windows venv 不能直接用。  
源码：`docker-compose-dev.yaml` 环境变量（项目内）  
追问：改 MCP 要？→ recreate gateway。

**35. 输出目录宿主机在哪？**  
口述：`.scholarflow/users/<uid>/threads/<tid>/user-data/outputs/<task-id>/`  
源码：ScholarFlow paths + scholar `OUTPUTS_ROOT`  
追问：虚拟路径？→ `/mnt/user-data/outputs/...`。

**36. 重试策略？**  
口述：`with_retry` 指数退避，默认 3 次，捕获 HTTPError/Timeout。  
源码：`clients/resilience.py`  
追问：403 重试吗？→ GitHub 显式错误，不宜盲目重试。

**37. coerce_items 为何存在？**  
口述：Agent 常传 list 或单对象；统一成 items 再校验。  
源码：`server.coerce_items`  
追问：和幻觉？→ 降工具调用失败率。

**38. ReviewFinding status？**  
口述：supported/partially_supported/unsupported/conflicting/unverified。  
源码：`models.ReviewStatus`  
追问：谁写？→ 编排 Phase3 LLM 按 Skill。

**39. lite backend 是什么？**  
口述：无 fastembed 时 hashing-bow 降级；面试演示应开 fastembed。  
源码：`store._hash_embed`，`config._detect_backend`  
追问：和简历模型？→ 说清 runtime。

**40. Chroma collection 名？**  
口述：默认 `scholarflow_evidence`，cosine。  
源码：`RagConfig.collection_name`，`upsert_chunks`  
追问：必须装 chromadb？→ 否。

**41. 关键词 bonus 有哪些 tip？**  
口述：blended/naive/hybrid/langchain/modular。  
源码：`hybrid_retrieve` 循环 tip  
追问：会不会过拟合 demo？→ 承认是启发式，可讲改进。

**42. 评测硬门槛和平均分区别？**  
口述：gate 是 0/1；average_score 是多指标均值。  
源码：`scorer.score_artifacts`  
追问：gate 不过平均分高？→ 仍 e2e_pass=false。

**43. compare_runs 做什么？**  
口述：对比两次 benchmark JSON 的 pass rate/分数。  
源码：`evaluation/compare_runs.py`  
追问：有没有优化前后数据？→ 框架有，专项 RAG 指标未建。

**44. 为何不用 web_search 当主证据？**  
口述：Skill 要求优先 scholar_mcp；防编造与不可解析结构。  
源码：orchestration/paper SKILL 规则  
追问：MCP 挂了？→ 应报错重试，不应用知识库伪造流水线。

**45. ExperimentPlan 如何变 MD？**  
口述：`experiment_plan.render_experiment_plan_md` / Skill 直接写 MD。  
源码：`experiment_plan.py`，experiment Skill  
追问：是否 JSON 落盘？→ 契约主文件是 MD。

**46. sources.json 怎么来？**  
口述：`aggregation.merge_sources(papers, repos)`。  
源码：`aggregation.py`，`artifacts.py`  
追问：和 evidence 不一致？→ `source_traceability` 指标会抓。

**47. 现场如何演示 RAG？**  
口述：`cd backend; uv run python ../evaluation/run_rag_demo.py`，看 DEMO OK 与 Top 证据 URL。  
源码：`run_rag_demo.py`  
追问：失败？→ 检查 fastembed 安装与样本目录。

**48. 最大技术债？**  
口述：RAG 无生成式 LLM；无 CE；补检非自动；缺 Hit@5/忠实度正式集；真实多任务 E2E 样本少。  
源码：评测复现方案 + pipeline  
追问：下一步？→ P0 Hit@5 标注与零付费脚本。

**49. 如何向面试官打开代码？**  
口述：顺序 orchestration SKILL → server.py → models/artifacts → rag/{chunking,store,retrieve,pipeline} → run_rag_demo。  
源码：同上  
追问：测在哪？→ `backend/tests/test_scholar_*.py`，`extensions/scholar_mcp/tests`。

**50. 若被要求「画出 Agent 图」？**  
口述：画 Lead→Skill 阶段→task 三路→MCP→Sandbox 文件→可选 RAG；标明无自研 StateGraph。  
源码：第二节调用链  
追问：和 LangGraph 节点对应？→ 对应框架 Lead 图，非 Scholar 自定义节点名。

---

## 九、技术边界

| 类别 | 内容 |
|------|------|
| **运行时提供（ScholarFlow）** | LangGraph Lead、`task` Sub-Agent、FastAPI Gateway、Sandbox、`write_file`、线程/checkpoint、Skill 加载中间件、MCP 适配 |
| **ScholarFlow 实现** | 4 Skill；`scholar_mcp` 工具与客户端；`scholarflow.scholar` 模型/矩阵/报告/组装/校验；Hybrid RAG；evaluation 结构评测与 demo |
| **不存在** | 自研 Scholar StateGraph；Planner/Supervisor 类；Cross-Encoder 运行时；PDF/图片 OCR；自动 MCP 补检状态机；50 题忠实度/Hit@5/引用/MCP↓ 的已归档报告；「10 个真实在线 E2E 全绿」 |

---

## 十、源码索引

| 文件 | 类/函数 | 面试作用 |
|------|---------|----------|
| `skills/custom/scientific-research-orchestration/SKILL.md` | 五阶段工作流 | 编排叙事 |
| `skills/custom/paper-evidence-extraction/SKILL.md` | 论文流程 | 文献 Agent 职责 |
| `skills/custom/repository-analysis/SKILL.md` | 仓库流程 | 代码 Agent 职责 |
| `skills/custom/experiment-plan/SKILL.md` | 实验流程 | 实验 Agent 职责 |
| `extensions/scholar_mcp/scholar_mcp/server.py` | 全部 `@mcp.tool` | MCP 清单 |
| `.../clients/arxiv.py` | `search_academic_papers` | 外检论文 |
| `.../clients/github.py` | `get_repository_overview` | 外检仓库 |
| `.../clients/resilience.py` | `with_retry` | 容错 |
| `scholarflow/scholar/models.py` | Pydantic 模型 | 契约 |
| `scholarflow/scholar/validation.py` | `validate_json_artifact` | Schema |
| `scholarflow/scholar/paths.py` | `REQUIRED_ARTIFACTS` | 九产物 |
| `scholarflow/scholar/artifacts.py` | `build_task_artifacts` | 组装 |
| `scholarflow/scholar/matrix.py` | `generate_*_matrix` | CSV |
| `scholarflow/scholar/report.py` | `build_research_report` | 报告 |
| `scholarflow/scholar/aggregation.py` | `dedupe_*`, `merge_sources` | 去重/来源 |
| `scholarflow/scholar/rag/config.py` | `RagConfig` | RAG 配置 |
| `scholarflow/scholar/rag/chunking.py` | `EvidenceChunk`, `load_chunks_*` | 切块 |
| `scholarflow/scholar/rag/store.py` | `embed_texts`, `upsert_chunks`, `hybrid_score_rerank` | 向量与重排 |
| `scholarflow/scholar/rag/retrieve.py` | `hybrid_retrieve`, `_BM25`, `_rrf_fuse` | 检索 |
| `scholarflow/scholar/rag/pipeline.py` | `index_artifacts_dir`, `rag_answer` | RAG 管线 |
| `evaluation/run_benchmark.py` | golden/artifacts | 评测入口 |
| `evaluation/scorer.py` | `score_artifacts` | 打分 |
| `evaluation/quality_metrics.py` | `e2e_pass_gate` | 硬门槛 |
| `evaluation/run_rag_demo.py` | `main` | 现场 Demo |
| `evaluation/reports/golden-baseline.json` | — | 10/10 证据 |
| `evaluation/reports/e2e-rag-test-001.json` | — | 真实 1 case 证据 |
| `ScholarFlow/agents/lead_agent/agent.py` | Lead（框架） | 说明边界 |

---

## 附录：现场命令（面试备用）

```powershell
# RAG Demo（需已装 fastembed 等）
cd E:\AgentProject\scholarflow_project\backend
uv run python ../evaluation/run_rag_demo.py

# Golden 结构评测（本地、通常无需付费 LLM）
uv run python ../evaluation/run_benchmark.py --mode golden
```

---

## 附录：简历安全口径（一句话）

> 可讲：4 Skill、MCP、Pydantic 九产物、bge-small+BM25+RRF+hybrid-score、引用约束、Golden 10/10 与真实 rag-test-001 硬门槛。  
> 不可讲：Cross-Encoder、50 题忠实度 0.62→0.84、Hit@5=82%、引用 91%、MCP↓77%、E2E 90%/Schema 97% 为「已证实线上结果」。

---

*完。与本底稿冲突的其他口头稿，以本文件与源码为准。*
