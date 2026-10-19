# ScholarFlow 简历与真实源码差异核验报告

> 审计方式：**只读**源码 / 评测报告 / 已有分析文档；不修改代码与配置。  
> 日期：2026-10-14  
> 依据：`scholarflow/scholar/**`、`extensions/scholar_mcp/**`、`skills/custom/**`、`evaluation/**`、`docs/scholar-flow/*分析*`

**标记说明**

| 标记 | 含义 |
|------|------|
| **A** | 源码与（至少部分）测试/报告均支持 |
| **B** | 源码存在，但缺少充分测试或报告不足 |
| **C** | 与源码不符（明显夸大/错误） |
| **D** | 当前仓库证据不足（无法证实） |

---

## 一、简历事实核对表

| # | 简历表述 | 标记 | 一句话结论 |
|---|----------|------|------------|
| 1 | 多智能体科研调研平台；LangGraph、FastAPI、RAG、MCP、Pydantic、Docker、Sandbox | **B** | 技术栈基本成立，但 ScholarFlow **未自研 LangGraph 工作流图**；LangGraph/FastAPI/Sandbox 属 ScholarFlow 底座 |
| 2 | 四类科研工作流；Sub-Agent 并行；任务分解、依赖调度、结果聚合 | **B** | 4 Skill + `task` 并行属实；「依赖调度」无独立调度器，主要靠 Skill 阶段顺序 + Lead LLM |
| 3 | MCP：arXiv、GitHub、Schema 校验、报告生成 | **A** | `scholar_mcp` 均有对应 tool；另有矩阵/组装/RAG 等 |
| 4 | Pydantic 7 类模型；落盘 9 类产物 | **A/B** | 9 产物 **A**；「7 类」需口径对齐（见下文），核心实体约 6+辅助 |
| 5 | Embedding + BM25 + RRF + **Cross-Encoder** 重排 | **C** | 前三者有；重排是 **hybrid-score**，**不是** Cross-Encoder |
| 6 | evidence_id / source_url 约束；证据不足触发 MCP 补检 | **B** | 约束与 `need_mcp_fallback` 标志有；**无代码强制**「收到标志后自动补检」 |
| 7 | 50 道问答；忠实度 0.62→0.84 | **C/D** | 仓库**无** 50 题集与忠实度评测脚本/报告 |
| 8 | Hit@5 82%；引用准确率 91%；MCP 调用下降 77% | **C/D** | 仓库**无**这些指标的原始实验与复现脚本 |
| 9 | 20 离线 + 10 E2E；完成率 90%；Schema≥97% | **B/C** | 20/10 **任务定义存在**；报告显示 Golden **100%**、真实 artifacts **100%(1/1)**，与「90%/97%」**不一致** |

---

## 二、逐条核验详情

### 1）多智能体平台 + 技术栈（B）

| 项 | 内容 |
|----|------|
| 是否实现 | 作为 **ScholarFlow 扩展** 存在：Skills + MCP + Schema + RAG + evaluation |
| 证据路径 | Skills：`skills/custom/*/SKILL.md`；MCP：`extensions/scholar_mcp/`；RAG：`scholarflow/scholar/rag/`；Gateway/FastAPI/Sandbox：ScholarFlow `backend/app`、`ScholarFlow/sandbox` |
| 测试/报告 | MCP/Schema/RAG 单测有；全栈属 Docker 集成 |
| 一致性 | 「基于这些技术构建」可说；暗示「自研整套 LangGraph+FastAPI 平台」则夸大 |
| 面试解释 | ScholarFlow 是科研域扩展包；运行时复用 ScholarFlow 的 LangGraph Lead、FastAPI Gateway、Sandbox |

### 2）四类工作流 + Sub-Agent 并行 / 依赖调度（B）

| 项 | 内容 |
|----|------|
| 是否实现 | **有** 4 Skill；编排 Skill 写明 Phase2 最多 3 路并行 `task` |
| 证据 | `scientific-research-orchestration/SKILL.md`（Plan→Delegate→Review→Aggregate→Deliver）；ScholarFlow `MAX_CONCURRENT_SUBAGENTS = 3`（文档/中间件） |
| 测试 | Skill 本身无单元测试；依赖框架 `task` 行为 |
| 夸大点 | 「依赖调度」若理解为 DAG 引擎/拓扑排序器 → **无**；实际是 Skill 规定阶段顺序 + LLM 按 Prompt 执行 |
| 面试解释 | 四类是 Skill 角色，不是四个 Agent 类；并行由 Lead 发多个 `task`；阶段依赖写在编排 Skill 里 |

### 3）MCP：arXiv / GitHub / Schema / 报告（A）

| 工具 | 函数 | 文件 |
|------|------|------|
| arXiv | `search_academic_papers` | `server.py` + `clients/arxiv.py` |
| GitHub | `get_repository_overview` | `server.py` + `clients/github.py` |
| Schema | `validate_evidence_schema` | `server.py` + `validation.py` |
| 报告 | `build_research_report` / `assemble_task_artifacts` | `server.py` + `report.py` / `artifacts.py` |
| 测试 | `extensions/scholar_mcp/tests/`、`backend/tests/test_scholar_schemas.py` 等 | 有 |

面试解释：还可补充矩阵、上传预览、RAG index/query；重试见 `clients/resilience.py::with_retry`。

### 4）7 类模型 + 9 类产物（A/B）

**9 类产物（A）** — `paths.py::REQUIRED_ARTIFACTS`：

1. research_report.md  
2. research_plan.json  
3. paper_evidence.json  
4. paper_matrix.csv  
5. repository_evidence.json  
6. repository_matrix.csv  
7. experiment_plan.md  
8. evidence_review.json  
9. sources.json  

组装：`artifacts.py::build_task_artifacts`。

**Pydantic「7 类」（B，需统一口径）** — `models.py` 核心实体：

| # | 模型 | 备注 |
|---|------|------|
| 1 | `ResearchPlan` | 有 |
| 2 | `PaperEvidence` | 有 |
| 3 | `RepositoryEvidence` | 有 |
| 4 | `ExperimentPlan` | 有（产物多为 MD） |
| 5 | `ReviewFinding` | 有 |
| 6 | `SourceRecord` | 有 |
| 7 | `DateRange` | 辅助嵌套模型 |

另有 Collection 包装类 4 个。`validation.py` 注册 **5** 个 JSON 文件 Schema（不含 experiment MD）。

面试解释：可说「6 个核心业务模型 + DateRange」或「面向 5 类 JSON + ExperimentPlan 结构」；避免含糊说 7 却对不上名单。

### 5）Embedding + BM25 + RRF + Cross-Encoder（C）

| 组件 | 源码 | 一致？ |
|------|------|--------|
| Embedding | `store.embed_texts`，默认 `BAAI/bge-small-en-v1.5` | 简历未写模型名则部分 OK |
| BM25 | `retrieve._BM25` | OK |
| RRF | `retrieve._rrf_fuse` | OK |
| Cross-Encoder | **不存在**；`hybrid_score_rerank`；注释写 *without CrossEncoder*；git 对 scholar 路径无 CrossEncoder 落地历史 | **不符** |

公式（真实）：

```text
score = 0.55 * lexical_overlap + 0.45 * normalized_dense_cosine
(+ paper/repo/source_url/keyword bonus)
```

文件：`store.py::hybrid_score_rerank`，`retrieve.py::hybrid_retrieve`。

**建议改简历：**「hybrid-score 重排（词面重叠 + dense）」或「二阶段打分重排」，删除 Cross-Encoder。

### 6）evidence_id / source_url + MCP 补检（B）

| 机制 | 证据 |
|------|------|
| source_url 非空 | `PaperEvidence.source_url_not_empty` |
| evidence_id 补全 | `server.normalize_paper_item` / `normalize_repo_item` |
| RAG 引用 | `rag_answer` 拼接 〔evidence_id (source_url)〕 |
| 证据不足标志 | `need_mcp_fallback: true`（`pipeline.rag_answer`） |
| 自动补检 | Skills **未**写死「见 fallback 必调 MCP」；**无**编排代码监听该字段自动执行 → 依赖 Lead LLM 是否遵从 tool 返回文案 |

面试解释：约束在 Schema/RAG 层；补检是**协议提示**，不是硬编码状态机。

### 7）50 道问答；忠实度 0.62→0.84（C/D）

- 仓库无 `50` 题 JSON、无 faithfulness 评测脚本、无 0.62/0.84 报告。  
- 仅存在于历史对话/简历叙事，**不可复现**。  
- **标记：C（若当作已测结果）/ D（若无实验文件）**。

### 8）Hit@5 82%；引用 91%；MCP↓77%（C/D）

- 无 Hit@5 / Citation Precision / MCP call 对比脚本与原始日志。  
- `evaluation/reports/*` 只有产物结构/质量指标，**无**上述三项。  
- **不可复现 → C/D**。

### 9）20 + 10 Benchmark；90% / 97%（B/C）

| 断言 | 仓库事实 |
|------|----------|
| 20 离线任务 | `evaluation/tasks.json` **20** 条 → 定义 **A** |
| 10 E2E case | `evaluation/benchmark_tasks.json` **10** 条 → 定义 **A** |
| Golden 跑分 | `golden-baseline.json`：e2e_pass_rate **1.0 (10/10)**，avg≈**0.99** |
| 真实 artifacts | `e2e-rag-test-001.json`：pass **1.0 (1/1)**，score **1.0** |
| 简历 90% / 97% | **与现有报告矛盾** → **C** |

可复现命令：

```powershell
cd backend
uv run python ../evaluation/run_benchmark.py --mode golden
uv run python ../evaluation/normalize_and_score_e2e.py   # 或 artifacts 模式
```

---

## 三、重点调查题回答

### 1. LangGraph 作用？有无独立工作流 Graph？

- ScholarFlow Lead 使用 LangGraph 运行时（框架层）。  
- ScholarFlow 目录下 **无** `StateGraph` / 自研 Graph 定义。  
- 科研工作流 = Skill Markdown 阶段，不是独立 Graph 代码。

### 2. 4 Skill 与 Sub-Agent？并行与依赖谁做？

- Skill = 提示词工作流包；Sub-Agent = ScholarFlow `task(general-purpose)` 拉起的子运行。  
- 并行：编排 Skill 要求最多 3 并发 `task`；框架有 Subagent 上限。  
- 依赖：Phase 顺序写在 Skill；无独立依赖调度服务。

### 3. Cross-Encoder 是否运行过？

- 当前代码：**否**。  
- scholar 路径 git `-S CrossEncoder`：**无命中历史实现**。  
- 仅有「可后续加 CrossEncoder」类注释。→ 简历写 Cross-Encoder **不成立**。

### 4. hybrid-score 怎么算？

见上文公式；另有 kind/source_url/关键词 bonus（`retrieve.py` 179–191 行附近）。

### 5. 九产物 / 七模型？

见第二节第 4 条完整名单。

### 6. evidence_id / source_url 如何校验？

- 生成：Pydantic + normalize 补全。  
- 引用：RAG 输出强制带 ID/URL。  
- 评测：`url_validity`、`source_traceability`、`schema_validity`（evaluation）。

### 7. need_mcp_fallback 是否自动补检？

- **只返回标志 + 提示文案**。  
- 外层是否补检 = Lead 是否再调 tool，**无保证自动执行的代码路径**。

### 8. 50 题与 20+10 是否有原始文件？

| 集合 | 文件 | 有无 |
|------|------|------|
| 50 问答 | — | **无** |
| 20 离线 | `evaluation/tasks.json` | 有 |
| 10 E2E | `evaluation/benchmark_tasks.json` | 有 |
| Golden 报告 | `evaluation/reports/golden-baseline.*` | 有 |
| 真实 1 case | `evaluation/reports/e2e-rag-test-001.*` | 有 |

### 9. 四项百分比如何算？分母？

| 简历指标 | 仓库计算方法 | 分母 |
|----------|--------------|------|
| 忠实度 0.62→0.84 | **无实现** | — |
| Hit@5 82% | **无实现** | — |
| 引用准确率 91% | **无实现** | — |
| MCP↓77%（6.2→1.4） | **无实现** | — |
| （真实可谈）E2E pass | `passed_tasks / task_count` | Golden=10；artifacts=1 |
| （真实可谈）schema_validity | 通过校验的 JSON 数 / 5 | 5 个注册 Schema 文件 |

### 10. 指标能否用现有脚本复现？

| 指标 | 可复现？ |
|------|----------|
| Golden 10/10、avg≈0.99 | ✅ `run_benchmark.py --mode golden` |
| 真实 rag-test-001 结构分 1.0 | ✅ artifacts / normalize 脚本 |
| RAG Demo Top 命中 | ✅ `run_rag_demo.py`（非 50 题指标） |
| 0.62/0.84、82%、91%、77%、90%、97% | ❌ **不能** |

---

## 四、与源码冲突的表述（必须改）

1. **Cross-Encoder 重排** → 改为 hybrid-score / 二阶段打分重排。  
2. **50 题忠实度 0.62→0.84** → 删除或改为「尚未落地的评测计划」。  
3. **Hit@5 82% / 引用 91% / MCP↓77%** → 删除（无实验）。  
4. **E2E 90% / Schema 97%** → 与报告冲突；应改为：  
   - Golden：**100% (10/10)**，均分 **0.99**；  
   - 真实在线完整评分：**1/1 通过**（勿说 10 个全真人跑完）。  
5. **「独立 LangGraph 工作流」** → 改为「复用 ScholarFlow/LangGraph Lead，Skill 定义科研工作流」。  
6. **「依赖调度引擎」** → 改为「Skill 阶段编排 + 有限并行 Sub-Agent」。

---

## 五、建议修改后的简历口径（可直接替换）

**技术栈：** Python、LangGraph（ScholarFlow 运行时）、FastAPI、MCP、Pydantic、Docker、Sandbox、Hybrid RAG  

**项目简介：**  
基于 ScholarFlow 扩展的科研调研 Agent 能力：4 类 Skill 工作流、独立 `scholar_mcp`、Pydantic 契约 9 类产物，以及面向产物库的 Hybrid RAG（bge-small-en-v1.5 + BM25 + RRF + hybrid-score）。

**建议 bullet：**

1. 设计编排/论文/仓库/实验 4 类 Skill，经 Lead Agent 的 `task` 并行委派（≤3），完成计划—审查—聚合与 9 类产物落盘。  
2. 实现 `scholar_mcp`（arXiv、GitHub、Schema 校验、矩阵/报告组装、RAG 索引与查询），含超时重试与结果规范化。  
3. 以 Pydantic 约束研究计划/论文/仓库/审查/来源等结构，统一输出 JSON/CSV/Markdown；`evidence_id`/`source_url`/`verification_status` 支撑可追溯。  
4. 产物库 RAG：Dense+BM25 双路召回、RRF 融合、hybrid-score 重排；答案强制引用；证据不足返回 `need_mcp_fallback` 提示外检。  
5. 评测：`tasks.json` 20 题 + `benchmark_tasks.json` 10 题；Golden E2E pass **100%**（均分 0.99）；真实 `rag-test-001` artifacts 硬门槛通过。

---

## 六、技术实现证据速查

| 能力 | 路径 | 符号 |
|------|------|------|
| 编排 Skill | `skills/custom/scientific-research-orchestration/SKILL.md` | 五阶段 |
| MCP | `extensions/scholar_mcp/scholar_mcp/server.py` | `@mcp.tool` |
| Schema | `scholarflow/scholar/models.py` / `validation.py` | Pydantic |
| 9 产物 | `scholarflow/scholar/paths.py` / `artifacts.py` | `REQUIRED_ARTIFACTS` |
| Hybrid RAG | `scholarflow/scholar/rag/{chunking,store,retrieve,pipeline}.py` | `hybrid_retrieve` |
| 重排 | `store.hybrid_score_rerank` | 0.55/0.45 |
| Fallback 标志 | `pipeline.rag_answer` | `need_mcp_fallback` |
| Golden 报告 | `evaluation/reports/golden-baseline.json` | pass_rate=1.0 |
| 真实 E2E 报告 | `evaluation/reports/e2e-rag-test-001.json` | pass_rate=1.0 |

---

## 七、面试官最可能追问的 30 个问题（附真实答法方向）

1. ScholarFlow 和 ScholarFlow 什么关系？→ 扩展，不改 LangGraph 核心。  
2. 有几个 Agent 类？→ 无自研类；4 Skill + Lead + Sub-Agent。  
3. LangGraph Graph 在哪？→ 框架 Lead；Scholar 无自研 Graph。  
4. 并行如何限制？→ Skill≤3 + 框架 SubagentLimit。  
5. 依赖调度代码在哪？→ Skill 阶段，无 DAG 引擎。  
6. MCP 有哪些 tool？→ 列 arXiv/GitHub/校验/矩阵/组装/RAG…  
7. GitHub 403 怎么办？→ token + `PermissionError` 提示。  
8. 7 个模型具体是谁？→ 按 models.py 点名。  
9. 9 个文件清单？→ 背 REQUIRED_ARTIFACTS。  
10. Embedding 模型与维度？→ bge-small-en-v1.5，384。  
11. 为什么不是 bge-m3？→ 当前默认可跑小模型；可配置。  
12. Cross-Encoder 在哪？→ **没有**；是 hybrid-score。  
13. hybrid-score 公式？→ 0.55 overlap + 0.45 dense。  
14. RRF 的 k？→ 默认 60（`RagConfig.rrf_k`）。  
15. 向量库存哪？→ JSON 为主，可选 Chroma。  
16. 检索入口？→ `rag_query` → `rag_answer` → `hybrid_retrieve`。  
17. RAG 调不调 LLM？→ 模块内不调。  
18. Context 怎么拼？→ bullet 模板 + 引用。  
19. need_mcp_fallback 谁消费？→ Lead 可能再调 tool，非硬编码。  
20. evidence_id 谁生成？→ MCP/normalize 或证据映射。  
21. source_url 校验？→ Pydantic validator。  
22. 50 题在哪？→ **没有**（勿硬撑）。  
23. 0.62→0.84 怎么测？→ **无实验**（改口用 Golden/artifacts）。  
24. 90% 怎么来的？→ 与报告不符；改口 100% Golden + 1 真实 case。  
25. Golden 和真实 E2E 区别？→ Golden 合成产物；真实是沙箱 artifacts。  
26. 如何现场演示 RAG？→ `uv run python ../evaluation/run_rag_demo.py`。  
27. 如何防幻觉？→ MCP 实拉 + Schema + verification + 引用。  
28. Sandbox 路径？→ `/mnt/user-data/outputs/<task-id>/`。  
29. Docker 怎么挂 MCP？→ `extensions_config` + SCHOLAR_PYTHONPATH。  
30. 最大技术债？→ RAG 无 LLM 生成式回答；无 Cross-Encoder；缺大规模 QA 评测；补检非自动状态机。

---

## 八、审计结论（给自己）

- **能站得住：** Skill 编排、MCP、Pydantic/9 产物、Hybrid 检索（Dense+BM25+RRF+hybrid-score）、引用约束、Golden/真实结构评测、Docker 扩展部署。  
- **必须删改：** Cross-Encoder；50 题忠实度与 82%/91%/77%；与报告冲突的 90%/97%。  
- **必须说清边界：** LangGraph/FastAPI/Sandbox 是 ScholarFlow；ScholarFlow 是域扩展；`need_mcp_fallback` 非自动闭环。

**原则：宁可少写数字，也不写无法用仓库脚本复现的数字。**

---

*本报告为面试前审计，不构成对代码的修改建议执行记录。*
