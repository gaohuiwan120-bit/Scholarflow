# ScholarFlow 项目源码与面试分析报告

> 生成依据：仓库真实代码（Skills / `scholarflow.scholar` / `scholar_mcp` / RAG / evaluation）。  
> **不编造**未实现的独立 Agent 类、Cross-Encoder、PDF OCR、自研 Supervisor 等。  
> 适用岗位：大模型应用开发（Agent + RAG + 工程）。

---

## 一、项目整体定位

### 1. ScholarFlow 解决什么问题？

面向「科研 / 技术调研」场景，把一次复杂调研拆成：

1. 可并行的文献检索与仓库分析  
2. 证据审查与结构化落盘  
3. 实验方案与对比矩阵  
4. （可选）对已沉淀证据库做可追溯追问（RAG）

避免「模型凭记忆写综述、编造论文/star 数」的不可验证输出。

### 2. 面向什么用户？

CV / ML / Agent 方向的研究者或工程师：需要文献 + 开源代码 + 实验设计的结构化调研交付物。

### 3. 用户输入是什么？

自然语言调研需求，例如：

> 使用 scientific-research-orchestration，调研 RAG 架构及相关 GitHub 实现，task id: `rag-test-001`

入口：ScholarFlow Web UI（`http://localhost:2026/workspace/chats/new`）或 Gateway API 对话。

### 4. 最终输出是什么？

契约 **9 类产物**（虚拟路径 `/mnt/user-data/outputs/<task-id>/`）：

| 文件 | 含义 |
|------|------|
| `research_plan.json` | 研究计划 |
| `paper_evidence.json` | 论文证据 |
| `paper_matrix.csv` | 论文对比矩阵 |
| `repository_evidence.json` | 仓库证据 |
| `repository_matrix.csv` | 仓库矩阵 |
| `experiment_plan.md` | 实验方案 |
| `evidence_review.json` | 证据审查 |
| `sources.json` | 来源清单 |
| `research_report.md` | 综合报告 |

定义见：`backend/packages/harness/scholarflow/scholar/paths.py` → `REQUIRED_ARTIFACTS`。

二次追问时，还可输出 RAG 检索结果（带 `evidence_id` / `source_url`）。

### 5. 为什么需要 Agent？

调研不是单次 completion：需要规划、并行委派、工具调用、交叉审查、多文件落盘。  
ScholarFlow 用 **ScholarFlow Lead Agent + Skill 工作流 + `task` Sub-Agent** 完成编排，而不是单 Prompt 硬生成。

### 6. 为什么需要 RAG？

首轮调研成本高（多次 MCP）。把 9 类产物索引进证据库后，追问可先检索再回答，降低重复外呼，并强制引用可追溯证据。

### Agent vs RAG 职责边界（必须背）

| | **Agent（编排侧）** | **RAG（检索侧）** |
|--|---------------------|-------------------|
| 职责 | 拆任务、调 MCP、写 9 产物、审查证据 | 对**已落盘产物**做混合检索与可引用回答 |
| 数据来源 | arXiv / GitHub / 上传文件（实时） | `paper_evidence.json` 等本地产物 |
| 幻觉约束 | Skill 规则 + `verification_status` + Schema | 强制绑定 `evidence_id`/`source_url`；不足则 `need_mcp_fallback` |
| 代码位置 | Skills + MCP + ScholarFlow Lead | `scholarflow/scholar/rag/` |

---

## 二、项目整体架构

### 2.1 真实架构（基于 ScholarFlow 增量扩展）

```
用户 (Browser / Chat)
    ↓
Nginx :2026
    ↓
Gateway API (FastAPI) + LangGraph 运行时
    ↓
ScholarFlow Lead Agent（LLM + Tool Calling）
    ├─ 加载 Skills（编排 / 论文 / 仓库 / 实验）
    ├─ task() → Sub-Agent（并行 ≤3）
    ├─ MCP Tools → scholar_mcp_*
    │       ├─ arXiv / GitHub / Schema / Matrix / Assemble
    │       └─ index_research_artifacts / rag_query
    ├─ write_file → Sandbox /mnt/user-data/outputs/<task-id>/
    └─ （可选）RAG：产物库 Dense+BM25+RRF → 可引用回答
```

**重要诚实口径：** ScholarFlow **没有**自研一套独立 `AgentOrchestrator` 类；编排逻辑写在 Skill（Markdown 工作流）里，由 ScholarFlow Lead Agent 执行。

### 2.2 模块 ↔ 路径 ↔ 核心符号

| 模块 | 路径 | 核心类 / 函数 |
|------|------|----------------|
| 编排 Skill | `skills/custom/scientific-research-orchestration/SKILL.md` | 五阶段工作流（Plan→Delegate→Review→Aggregate→Deliver） |
| 论文 Skill | `skills/custom/paper-evidence-extraction/SKILL.md` | 映射 `PaperEvidence` |
| 仓库 Skill | `skills/custom/repository-analysis/SKILL.md` | 映射 `RepositoryEvidence` |
| 实验 Skill | `skills/custom/experiment-plan/SKILL.md` | 生成 `experiment_plan.md` |
| 数据契约 | `scholarflow/scholar/models.py` | `ResearchPlan`, `PaperEvidence`, `RepositoryEvidence`, `ExperimentPlan`, `ReviewFinding`, `SourceRecord` |
| 产物组装 | `scholarflow/scholar/artifacts.py` | `build_task_artifacts` |
| 矩阵 | `scholarflow/scholar/matrix.py` | `generate_paper_matrix`, `generate_repository_matrix` |
| 报告 | `scholarflow/scholar/report.py` | `build_research_report` |
| 校验 | `scholarflow/scholar/validation.py` | `validate_json_artifact` |
| MCP Server | `extensions/scholar_mcp/scholar_mcp/server.py` | FastMCP `scholar_mcp` 全部 tools |
| arXiv 客户端 | `.../clients/arxiv.py` | `search_academic_papers` |
| GitHub 客户端 | `.../clients/github.py` | `get_repository_overview` |
| 重试 | `.../clients/resilience.py` | `with_retry` |
| RAG 配置 | `scholarflow/scholar/rag/config.py` | `RagConfig` |
| RAG 切块 | `scholarflow/scholar/rag/chunking.py` | `EvidenceChunk`, `load_chunks_from_artifacts_dir` |
| RAG 存储 | `scholarflow/scholar/rag/store.py` | `embed_texts`, `upsert_chunks` |
| RAG 检索 | `scholarflow/scholar/rag/retrieve.py` | `hybrid_retrieve`, `_BM25`, `_rrf_fuse` |
| RAG 管线 | `scholarflow/scholar/rag/pipeline.py` | `index_artifacts_dir`, `rag_answer` |
| 评测 | `evaluation/` | `run_benchmark.py`, `scorer.py`, `run_rag_demo.py` |
| Lead Agent（底座） | `ScholarFlow/agents/lead_agent/agent.py` | ScholarFlow 超代理（非 ScholarFlow 自写） |

---

## 三、Agent 架构分析（重点）

### 3.1 有哪些「Agent」？——真实实现是 Skill + Sub-Agent，不是独立类

| 角色（面试可称） | 真实载体 | 有无独立 Python Agent 类？ |
|------------------|----------|---------------------------|
| 编排者 | Skill `scientific-research-orchestration` | **无** |
| 文献研究员 | Skill `paper-evidence-extraction` + Sub-Agent | **无** |
| 仓库分析员 | Skill `repository-analysis` + Sub-Agent | **无** |
| 实验设计 | Skill `experiment-plan` + Sub-Agent | **无** |
| Lead 执行器 | ScholarFlow Lead Agent | 有（框架层，`lead_agent/agent.py`） |

### 3.2 每个职责

1. **编排 Skill**：写 `ResearchPlan`；最多 3 路并行 `task`；审查；调 MCP 聚合 9 文件；交付摘要。  
2. **论文 Skill**：`scholar_mcp_search_academic_papers` → 映射字段 → Schema 校验 → 写 `paper_evidence.json`。  
3. **仓库 Skill**：`scholar_mcp_get_repository_overview` → 映射 → 写 `repository_evidence.json`。  
4. **实验 Skill**：读论文/仓库证据 → 写 `experiment_plan.md`（假设、基线、消融等）。

### 3.3 Agent 如何通信？

- **无**消息总线 / 共享内存对象。  
- 通信介质：  
  1. Lead 通过 `task(prompt=...)` 把指令发给 Sub-Agent  
  2. 中间与最终结果写入 Sandbox 文件（JSON/MD/CSV）  
  3. 编排者再读文件或把 JSON 传入 MCP `assemble_task_artifacts`

### 3.4 是否存在 Planner / Executor / Supervisor？

| 概念 | 是否存在独立模块 | 实际对应 |
|------|------------------|----------|
| Planner | **无独立类** | 编排 Skill Phase 1 + Lead LLM 生成 `ResearchPlan` |
| Executor | **无独立类** | Lead / Sub-Agent 调 MCP + `write_file` |
| Supervisor | **无独立类** | 编排 Skill Phase 3 Review（LLM 按 Skill 规则交叉检查） |

面试话术：

> 我们没有手写 Planner/Supervisor 框架代码，而是用 Skill 把规划—委派—审查—聚合固化成可加载工作流，由 ScholarFlow Lead Agent 执行。

### 3.5 执行顺序与如何决定调用谁？

顺序（编排 Skill 明文规定）：

```
Plan → Delegate(论文∥仓库∥实验) → Review → Aggregate → Deliver
```

决定方式：

- Lead 根据用户话术与 Skill `description` 触发加载 `scientific-research-orchestration`  
- 委派表写死三路 Skill 名；由编排 Prompt 指示 Sub-Agent「加载某某 Skill」  
- **不是**分类器路由到不同 Agent 类

### 3.6 状态如何保存？

| 状态 | 位置 |
|------|------|
| 对话 / 线程 | ScholarFlow / LangGraph 线程状态（框架能力） |
| 调研产物 | `/mnt/user-data/outputs/<task-id>/` → 宿主机 `.scholarflow/users/.../threads/.../user-data/outputs/` |
| RAG 索引 | `evaluation/rag_index/`（`corpus.json` / `vectors.json` / 可选 Chroma） |

ScholarFlow **未**单独实现长期 Memory Store。

### 3.7 Agent 调用流程图

```
用户调研请求
    ↓
ScholarFlow Lead Agent（加载 orchestration Skill）
    ↓
Phase1: 写 research_plan.json
    ↓
Phase2: 并行 task ×≤3
    ├─ Sub-Agent + paper-evidence-extraction → paper_evidence.json
    ├─ Sub-Agent + repository-analysis → repository_evidence.json
    └─ Sub-Agent + experiment-plan → experiment_plan.md
    ↓
Phase3: evidence_review.json
    ↓
Phase4: MCP assemble / matrix / validate → 补齐 9 件套
    ↓
Phase5: 向用户摘要交付
    ↓
（可选）index_research_artifacts → rag_query 追问
```

---

## 四、RAG 知识库分析（重点）

### 4.1 数据来源

| 问题 | 答案（真实） |
|------|----------------|
| 用什么数据？ | ScholarFlow **已生成的 9 类产物目录**，不是任意网页爬虫库 |
| 格式？ | JSON / CSV / Markdown |
| 如何加载？ | `load_chunks_from_artifacts_dir(artifacts_dir)` |
| 预处理在哪？ | `chunking.py`：拼字段、裁剪长度、按窗口切 MD |

样本目录：`docs/scholar-flow/samples/rag-test-001/`。

### 4.2 文档解析

| 问题 | 真实情况 |
|------|----------|
| 解析方式 | 读文本文件 `Path.read_text`；JSON `json.loads` |
| 支持格式 | 产物侧：`.json` / `.md` / `.csv`（CSV 不直接切块入库，主要用 evidence JSON + report/plan MD） |
| 上传论文 | MCP `extract_uploaded_paper`：读文件前 4000 字符；**非 PDF 解析器** |
| 图片 | **未实现** OCR / 多模态解析 |
| 元数据 | `EvidenceChunk`：`evidence_id`, `kind`, `title`, `source_url`, `verification_status`, `task_id`, `metadata` |

### 4.3 Chunk 切分

- **位置**：`scholarflow/scholar/rag/chunking.py`  
- **策略**：  
  - 论文 / 仓库：一条证据 ≈ 一个 chunk（字段拼接后 `_clip` ≤1800）  
  - 报告 / 实验 / 计划 / 审查：按 **固定约 1200 字符窗口**滑动切分（长度切分，**非语义切分**）  
- **Metadata**：`year`/`identifier`（论文）、`language`（仓库）、`artifact`+`offset`（长文档）

### 4.4 Embedding

| 问题 | 答案 |
|------|------|
| 默认模型 | `BAAI/bge-small-en-v1.5`，维度 **384**（fastembed ONNX） |
| 代码 | `store.py` → `embed_texts` / `_load_embedder` |
| 文档向量化 | `upsert_chunks` 对 chunk 文本 `embed_texts` |
| Query 向量化 | `hybrid_retrieve` 内对 query 同样 `embed_texts` |
| 缓存 | embedder `@lru_cache`；向量落盘 `vectors.json`；**无**独立 Redis embedding cache |
| 降级 | 无 fastembed 时 `backend=lite` → `hashing-bow`（面试应说明这是降级） |

配置：`RagConfig.from_env()`（`config.py`）。

### 4.5 Vector Database

| 问题 | 答案 |
|------|------|
| 主存储 | **JSON 本地**：`corpus.json` + `vectors.json` |
| 可选 | **Chroma** `PersistentClient`，collection 名默认 `scholarflow_evidence`，空间 `cosine` |
| 入库 | `upsert_chunks` → JSON 必写；Chroma 有则双写 |
| 查询 | 主路径是内存余弦：`_cosine(q_emb, emb)`（`retrieve.py`），不是只靠 Chroma query API |
| 相似度 | 余弦（向量已 normalize 时近似内积） |

索引目录默认：`evaluation/rag_index/`。

### 4.6 Retriever

| 问题 | 答案 |
|------|------|
| 入口 | `hybrid_retrieve` / `rag_answer` / MCP `rag_query` |
| Top-K | `RagConfig.rerank_top_k` 默认 **5**；dense/sparse recall 默认各 **20** |
| 过滤 | `verified_only`：优先 `verified` / `partially_verified` |
| Hybrid | **有**：Dense + BM25 → **RRF**（`_rrf_fuse`） |
| Reranker | **有，但是 hybrid-score**（词面重叠 0.55 + dense 0.45），**不是** Cross-Encoder / bge-reranker |

BM25：`retrieve.py` 内置 `_BM25`；分词 jieba，失败则中文 bigram。

### 4.7 RAG 如何与 Agent 结合

**真实调用链：**

```
User 追问
  → Lead Agent 调 MCP scholar_mcp_rag_query(question)
      → scholarflow.scholar.rag.rag_answer
          → hybrid_retrieve
          → 返回 answer + evidence[]（可含 need_mcp_fallback）
  → 若 need_mcp_fallback=true
      → Lead 再调 scholar_mcp_search_academic_papers / get_repository_overview
      → 更新产物后 scholar_mcp_index_research_artifacts 再查
```

**注意：** `rag_answer` **不调用 LLM 生成长文**，是检索 + 拼接带引用 bullet 的确定性回答。  
「RAG Prompt 拼 Context 再喂大模型」在当前 ScholarFlow RAG 模块中 **未实现**；若 Lead 二次总结，属于 ScholarFlow Agent 侧行为，不是 `pipeline.py` 内逻辑。

首轮全量调研时，Agent **先**用 MCP 拉外网证据写产物，**再**可索引；不是「一上来只查向量库」。

---

## 五、Prompt 设计分析

### 5.1 Prompt 在哪里？

| 类型 | 位置 |
|------|------|
| ScholarFlow 工作流 Prompt | 4 个 `skills/custom/*/SKILL.md` |
| ScholarFlow 系统 Prompt | `ScholarFlow/agents/lead_agent/prompt.py`（框架层） |
| RAG「回答模板」 | `pipeline.py` 内 f-string 拼接（非 Chat Prompt 模板文件） |

### 5.2 不同 Agent 是否不同 Prompt？

是：四个 Skill 各有独立 Markdown 指令与规则（反幻觉、工具名、产出文件）。

### 5.3 RAG 如何拼接 Context？

`rag_answer`：对每个 hit 取 `text[:280]`，格式：

```text
- [kind] snippet 〔evidence_id (source_url)〕
```

### 5.4 如何限制幻觉？

1. Skill：禁止编造 DOI/arXiv/star；不确定标 `unverified`  
2. Schema：`source_url` 非空校验（`PaperEvidence`）  
3. MCP：证据来自 API，不是模型记忆  
4. RAG：无证据则 `need_mcp_fallback`，不编造  
5. Review：`supported` / `unsupported` / `conflicting` 等状态

### 5.5 输出格式如何控制？

- Pydantic 模型 + `validate_evidence_schema`  
- `assemble_task_artifacts` 统一生成 9 文件  
- Skill 明文列出文件名清单

---

## 六、Tool Calling 分析

### 6.1 scholar_mcp 工具清单（`server.py`）

| MCP 工具名（运行时前缀 `scholar_mcp_`） | 作用 |
|----------------------------------------|------|
| `search_academic_papers` | arXiv 检索 |
| `get_repository_overview` | GitHub 仓库概览 + README |
| `extract_uploaded_paper` | 沙箱内上传文本预览 |
| `generate_research_matrix` | 生成 CSV 矩阵 |
| `validate_evidence_schema` | Pydantic 校验 |
| `build_research_report` | 生成报告 MD |
| `list_task_artifacts` | 列出 9 路径 |
| `assemble_task_artifacts` | 一次组装 9 产物 |
| `index_research_artifacts` | 索引产物到 RAG |
| `rag_query` | 混合检索问答 |

另有 ScholarFlow 内置：`write_file`、`task`、`bash`、`web_search` 等（框架工具，非 ScholarFlow 自研）。

### 6.2 注册位置

- 实现：`extensions/scholar_mcp/scholar_mcp/server.py`（FastMCP）  
- 启用：`extensions_config.json` → `mcpServers.scholar_mcp`（示例见 `extensions_config.example.json`）

### 6.3 Agent 如何调用 / 返回如何处理？

Lead / Sub-Agent 通过 LangChain MCP 适配器以 tool call 调用；返回多为 JSON 字符串，由 LLM 再 `write_file` 或传入下一个 MCP。  
Python 层容错：`coerce_items` / `normalize_*` 补 `evidence_id`；HTTP 层 `with_retry` 指数退避。

---

## 七、Memory 和上下文管理

| 问题 | 真实情况 |
|------|----------|
| ScholarFlow 自研 Memory？ | **无** |
| 多轮对话？ | 依赖 ScholarFlow 线程 / LangGraph checkpointer（框架） |
| 调研「记忆」？ | 文件系统产物 + RAG 索引，相当于 **artifact memory** |
| 保存内容 | 9 文件 + `evaluation/rag_index/*` |

---

## 八、完整请求调用链（两场景）

### 场景 A：首轮调研（主路径）

| 步骤 | 文件 | 函数 / 载体 | 作用 |
|------|------|-------------|------|
| 1 用户输入 | Web UI / Gateway | 对话 API | 进入线程 |
| 2 Lead 启动 | `lead_agent/agent.py` | ScholarFlow Lead | LLM + tools |
| 3 加载编排 Skill | `scientific-research-orchestration/SKILL.md` | Skill 激活中间件 | 注入工作流 |
| 4 规划 | Agent + `write_file` | — | `research_plan.json` |
| 5 并行委派 | `task` tool | Sub-Agent | 三路 Skill |
| 6 论文检索 | `clients/arxiv.py` | `search_academic_papers` | 拉 arXiv |
| 7 仓库分析 | `clients/github.py` | `get_repository_overview` | 拉 GitHub |
| 8 审查 / 实验 | Skills | — | review + experiment |
| 9 聚合 | `artifacts.py` | `build_task_artifacts` | 9 文件内容 |
| 10 落盘 | Sandbox | `write_file` | outputs 目录 |
| 11 交付 | Lead | — | 用户可见摘要 |

### 场景 B：追问（RAG 路径）

| 步骤 | 文件 | 函数 | 作用 |
|------|------|------|------|
| 1 索引 | `pipeline.py` | `index_artifacts_dir` | 切块+向量化+入库 |
| 2 提问 | `server.py` | `rag_query` | MCP 入口 |
| 3 检索 | `retrieve.py` | `hybrid_retrieve` | Dense+BM25+RRF+rerank |
| 4 回答 | `pipeline.py` | `rag_answer` | 带引用 bullet；不足则 fallback |

---

## 九、工程实现

| 维度 | 真实情况 |
|------|----------|
| Python | ≥3.12；harness `ScholarFlow-harness`；MCP `scholar-mcp` |
| 框架 | ScholarFlow = LangGraph + LangChain；Gateway FastAPI |
| API | 统一 Nginx → Gateway；ScholarFlow **无**独立对外 REST（能力在 MCP/对话内） |
| 配置 | 根目录 `config.yaml`、`extensions_config.json`、`.env`；RAG 用 `SCHOLAR_RAG_*` 环境变量 |
| 日志 | MCP 客户端 `logging`；重试 `logger.warning` |
| 异常 | `ScholarValidationError`；GitHub 403/`PermissionError`；RAG 空结果 `need_mcp_fallback` |
| Docker | `docker/docker-compose-dev.yaml`；注入 `SCHOLAR_MCP_PYTHON` / `SCHOLAR_PYTHONPATH` |
| 数据存储 | 线程 user-data 目录；RAG `evaluation/rag_index/`；评测 `evaluation/reports/` |
| 评测 | `evaluation/run_benchmark.py`、`scorer.py`、结构+质量+硬门槛 |

---

## 十、面试重点总结

### 10.1 最适合包装的技术亮点

1. **增量扩展而非造轮子**：Skill 工作流 + 独立 MCP + Pydantic 契约，复用 ScholarFlow Lead/Sandbox。  
2. **结构化 9 产物 + Schema 校验**：降低自由文本幻觉。  
3. **证据链**：`evidence_id` / `source_url` / `verification_status` / 矩阵一致性。  
4. **产物库 Hybrid RAG**：Dense（bge-small-en-v1.5）+ BM25 + RRF + hybrid-score，强制引用。  
5. **可跑评测**：产物完整性、Schema、URL、主题相关性硬门槛。

### 10.2 简历应突出什么

- 4 Skill 编排 + MCP 工具链 + 9 类契约产物  
- Hybrid RAG 在**科研证据库**上的可追溯问答  
- Docker 可部署、自动化评分  

### 10.3 面试官最可能问什么（附真实答案要点）

| 问题 | 要点 |
|------|------|
| 你们有几个 Agent？ | 4 个 Skill 角色 + ScholarFlow Lead；无自研 Agent 类 |
| Planner 在哪？ | Skill Phase1，不是独立 Planner 服务 |
| Embedding 模型？ | 默认 `BAAI/bge-small-en-v1.5`，384 维，fastembed |
| 有没有 Cross-Encoder？ | **没有**；rerank 是 hybrid-score |
| 向量库？ | JSON 为主，可选 Chroma 双写 |
| RAG 会调 LLM 吗？ | `rag_answer` 本身不调；可再被 Lead 总结 |
| 如何防幻觉？ | MCP 实拉 + Schema + verification_status + 引用绑定 |
| 和 ScholarFlow 关系？ | 扩展包，不改 LangGraph 核心 |

### 10.4 源码必须掌握（打开顺序）

1. `skills/custom/scientific-research-orchestration/SKILL.md`  
2. `extensions/scholar_mcp/scholar_mcp/server.py`  
3. `scholarflow/scholar/models.py` + `artifacts.py`  
4. `scholarflow/scholar/rag/{chunking,store,retrieve,pipeline,config}.py`  
5. `evaluation/run_rag_demo.py`（现场演示）  
6. `docs/scholar-flow/rag.md` + `e2e-prompt.md`

### 10.5 明确「没有做」的清单（防穿帮）

- 无独立多 Agent 图（无自研 StateGraph ScholarFlow）  
- 无 Supervisor/Planner Python 类  
- 无 PDF/图片多模态解析  
- 无 Cross-Encoder / bge-reranker-v2-m3 运行时（勿再背）  
- 无 ScholarFlow 自研长期 Memory  
- RAG 默认不是「Context 拼进 ChatPrompt 再调 LLM」的经典模板（是检索+引用拼装）

---

## 附录：现场演示命令

```powershell
cd E:\AgentProject\scholarflow_project\backend
uv pip install fastembed chromadb rank-bm25 jieba
uv run python ../evaluation/run_rag_demo.py
```

成功标志：打印 `=== DEMO OK ===`，Top 证据含真实 `source_url`（如 arXiv）。

---

*本报告仅描述仓库现状；若后续补 Cross-Encoder / LLM 生成式 RAG / PDF 解析，请同步改本节「未实现」列表。*
