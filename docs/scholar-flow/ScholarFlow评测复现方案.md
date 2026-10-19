# ScholarFlow 评测复现方案

> 状态：**方案阶段**（待你确认后再实施）  
> 约束：不执行付费模型调用；不修改生产业务代码；不预设必须打到简历数字。  
> 简历中的 0.62→0.84 / 82% / 91% / 77% / 90% / 97% 一律视为**历史待核实目标**，非已证实结果。

---

## 0. 结论先行

| 简历指标 | 现有测量能力 | 能否「复现历史值」 | 建议 |
|----------|--------------|-------------------|------|
| 忠实度 0.62→0.84 | **无** | 否（需新建实验） | 重建评测后报告**实测均值** |
| Hit@5 82% | **无**（仅有检索链路） | 否（缺 gold 标注集） | 新建带 `gold_evidence_id` 的题集 |
| 引用准确率 91% | **无** | 否 | 新建引用审计脚本 |
| MCP↓77% | **无**真实 tool 计数器 | 否 | A/B 跑 Agent 并解析 tool 日志 |
| E2E 完成率 90% | **有**（硬门槛 pass rate） | 部分：可复现**当前** Golden/artifacts，但现报告是 **100%** 不是 90% | 用现成脚本重跑并改口径 |
| Schema 通过率 97% | **有**（`schema_validity`） | 部分：现报告 **100%**（5/5 JSON），非 97% | 用现成脚本；区分首次/最终 |

**一句话：** 5、6 可马上用现有脚本得到「当前值」；1–4 必须新建数据与脚本，且结果可能达不到历史目标值。

---

## 一、评测基础设施审计

### 1.1 已有目录与能力

| 资产 | 路径 | 能测什么 |
|------|------|----------|
| 离线任务定义 | `evaluation/tasks.json`（20） | 任务 ID/prompt，**不含** QA/gold |
| E2E 任务定义 | `evaluation/benchmark_tasks.json`（10） | keywords/min_papers，**无**在线必跑日志 |
| 结构+质量评分 | `evaluation/metrics.py`, `quality_metrics.py`, `scorer.py` | 产物完整、Schema、URL、主题相关、硬门槛 |
| Benchmark 跑手 | `evaluation/run_benchmark.py` | golden / fixture / artifacts |
| 真实产物评分 | `evaluation/normalize_and_score_e2e.py` | 单 case artifacts |
| Gateway 跑手 | `evaluation/e2e_runner.py` | dry-run 导出 prompt；真跑需 Gateway+LLM（付费） |
| RAG Demo | `evaluation/run_rag_demo.py` | 索引+检索冒烟，**不计 Hit@5** |
| Golden 报告 | `evaluation/reports/golden-baseline.json` | pass_rate=1.0, avg≈0.99 |
| 真实报告 | `evaluation/reports/e2e-rag-test-001.json` | pass_rate=1.0 (1 task) |
| 样本产物库 | `docs/scholar-flow/samples/rag-test-001/`、`evaluation/results/rag-survey/` | 可作索引语料 |
| Schema 单测 | `backend/tests/test_scholar_schemas.py` 等 | 模型合法性 |
| RAG 单测 | `backend/tests/test_scholar_rag.py` | 检索冒烟 |
| MCP 单测 | `extensions/scholar_mcp/tests/` | 工具行为 |

### 1.2 明确缺失

| 缺失项 | 影响指标 |
|--------|----------|
| 固定 QA 集（问题+gold 证据+可核验陈述） | 忠实度、Hit@5、引用 |
| Faithfulness / LLM-as-Judge 或人工标注流水线 | 忠实度 |
| Hit@5 评测脚本调用 `hybrid_retrieve` | Hit@5 |
| 引用抽取与 support 判定脚本 | 引用准确率 |
| Agent 运行 tool-call 原始日志采集（按 run 落盘） | MCP 调用量 |
| 「禁用产物 RAG」开关的标准化 A/B harness | MCP↓ |
| 首次 Schema vs 修复后 Schema 分开统计 | Schema 97% 叙事 |
| 多任务真实在线 E2E 产物集（目前完整评分约 1 个） | E2E 90% 叙事 |

### 1.3 Agent 日志 / MCP 记录现状

- ScholarFlow 具备 Run/事件持久化能力（框架层），但 ScholarFlow **evaluation 未封装**「按 task 导出 `scholar_mcp_*` 调用次数」的标准脚本。  
- `need_mcp_fallback` **不能**代替真实 MCP 计数。  
- 要测实验 4，必须在 A/B 跑批时落盘 tool 轨迹（从 Gateway/RunEvent 或 Agent 回调导出）。

---

## 二、六组实验：可行性与设计

### 实验 1：答案忠实度（Faithfulness）

**目标对比：** 0.62（无产物 RAG）→ 0.84（有产物 RAG）— *待核实，非承诺*

| 项 | 内容 |
|----|------|
| 可行性 | **中低**：链路可建，但依赖标注或 Judge 成本；测的是**外层 Agent 最终答案**，不是 `rag_answer` 模板 |
| 现有能力 | 无 |
| 需新增 | ① QA 集 JSON；② 跑批 harness（禁用/启用 index+rag_query）；③ 陈述抽取；④ 支持判定（人工或 Judge）；⑤ 汇总脚本 |
| 对照 | **A**：禁止 `index/rag_query`，追问仅靠模型记忆或强制外检；**B**：先 index 样本/任务产物再追问 |
| 公式 | 题级：`supported_claims / total_claims`；总体：各题均值；分别报 A/B |
| 数据需求 | ≥30 题建议（简历写 50 则需凑满 50）；每题：question、可选 gold、最终答案、claim 列表 |
| 成本 | 若 Judge：约 50×2 条件 × 1–2 次 LLM 调用；若人工：0 API，约 4–8 人时 |
| 分类 | **必须重新建立评测** |

**输出文件（拟定）：**

- `evaluation/datasets/faithfulness_qa.jsonl`  
- `evaluation/reports/faithfulness_raw.json`  
- `evaluation/reports/faithfulness_summary.md`

---

### 实验 2：Hit@5

**目标对比：** 82% — *待核实*

| 项 | 内容 |
|----|------|
| 可行性 | **高（检索侧）**：可直接调 `hybrid_retrieve`，**零付费** |
| 现有能力 | `scholarflow.scholar.rag.retrieve.hybrid_retrieve` |
| 需新增 | 带 `gold_evidence_id`（可多标）的题集 + `eval_hit_at_k.py` |
| 公式 | `Hit@5 = (1/N) * Σ 1[gold ∩ Top5 ≠ ∅]`；另可报 MRR |
| 数据需求 | 基于已索引语料（如 rag-test-001）人工标 30–50 题；gold 必须存在于 corpus |
| 成本 | 标注 2–4 人时；运行 &lt;1 分钟（本地 embedding） |
| 分类 | **必须新建题集+脚本**；可最快出客观数 |

**注意：** 不得为凑 82% 只选易命中题；应先定题再跑。

---

### 实验 3：引用准确率（拆两项）

**目标对比：** 91% — *待核实；且原简历未拆分*

| 指标 | 定义（本方案强制拆开） |
|------|------------------------|
| **引用 ID 合法率** | 答案中出现的 `evidence_id` ∈ 当次检索/产物集合 的比例 |
| **引用内容支持率** | 带引用的事实陈述中，被引用 chunk **确实支持**该陈述的比例 |

| 项 | 内容 |
|----|------|
| 可行性 | ID 合法率 **高**（规则）；内容支持率 **中**（需人工/Judge） |
| 现有能力 | RAG 输出带 `evidence` 列表；Agent 最终答案格式不保证统一 |
| 需新增 | 引用正则抽取；与 evidence 文本对齐；support 标注协议 |
| 公式 | `ID合法率 = valid_cites / all_cites`；`支持率 = supported_cited_claims / cited_claims` |
| 成本 | 规则部分免费；支持判定同实验 1 |
| 分类 | **必须重新建立** |

---

### 实验 4：MCP 调用量下降

**目标对比：** 77%（叙事曾用 6.2→1.4）— *待核实*

| 项 | 内容 |
|----|------|
| 可行性 | **中**：需真跑 Agent + 可靠 tool 日志；**付费/耗时** |
| 现有能力 | 无标准 MCP 计数脚本；`need_mcp_fallback` **禁用**作计数依据 |
| 需新增 | ① A/B 协议；② 从 Run 日志统计 `scholar_mcp_*` 实际调用；③ 同题集二次问答场景 |
| 条件 A | 清空/禁用产物索引；禁止 `rag_query`；追问只允许外检 MCP |
| 条件 B | 预索引历史产物；允许 `rag_query`；仍允许不足时外检 |
| 公式 | `reduction = (mean_calls_A - mean_calls_B) / mean_calls_A` |
| 统计对象 | **仅**真实 tool 执行（名称+次数）；分 `search_academic_papers` / `get_repository_overview` / `rag_query` / 其他 |
| 成本 | 每题多轮 × N 题 × 2 条件；视模型定价，建议先 **N=10** 试点 |
| 分类 | **必须新建 harness + 日志导出** |

---

### 实验 5：E2E 完成率

**目标对比：** 90% — *与现有报告冲突*

| 项 | 内容 |
|----|------|
| 可行性 | **高（Golden）**；**中（真实 Agent）** |
| 现有能力 | `run_benchmark.py --mode golden`；artifacts 评分；`e2e_pass_gate` |
| 当前已知结果 | Golden：**100% (10/10)**；真实 artifacts：**100% (1/1)** |
| 公式（沿用现有） | `e2e_pass_rate = (# tasks with e2e_pass_gate=1) / N` |
| 成功条件（现有硬门槛） | completeness=1 ∧ schema=1 ∧ url≥0.8 ∧ topic≥0.5 |
| 需增强 | 真实模式：对 10 个 benchmark 全量在线跑并拷贝产物（付费）；失败原因结构化字段 |
| 分类 | **可立即复现当前 Golden**；真实 10 连跑属**重建/扩样** |

**口径要求：**  
- Golden ≠ 真实 Agent E2E  
- 不得把 Golden 100% 写成「线上 10 任务完成率」  
- 若真实多任务失败，**保留失败样本**并报真实 pass rate（可能 &lt;90% 或 &gt;90%）

---

### 实验 6：Schema 通过率

**目标对比：** 97% — *与现有报告冲突*

| 项 | 内容 |
|----|------|
| 可行性 | **高** |
| 现有能力 | `validation.validate_json_artifact`；scorer `_schema_validity_score`（5 个 JSON） |
| 当前已知 | 报告中 schema_validity=**1.0**（5/5） |
| 公式 | `schema_pass = valid_files / 5`（每任务）；总体可报宏平均或「所有任务所有文件」微平均 |
| 需增强 | 区分 **首次落盘** vs **normalize/修复后**；记录失败类型（ValidationError 字段） |
| 成本 | 本地秒级 |
| 分类 | **可立即复现当前最终通过率**；「首次 97%」需另采首次快照（目前缺） |

---

## 三、测量公式汇总（实施时写入代码 docstring）

```text
Faithfulness_q = |claims supported by evidence| / |claims|
Faithfulness   = mean_q Faithfulness_q

Hit@5 = mean_q 1[gold_q ∩ Top5_q ≠ ∅]

CiteID_Precision = |cites with id ∈ evidence_set| / |cites|
CiteSupport      = |cited claims supported by cited chunk| / |cited claims|

MCP_Reduction = (MCP_A - MCP_B) / MCP_A
  where MCP_* = mean over tasks of count(real scholar_mcp_* tool executions)

E2E_PassRate = |{task | gate(task)=pass}| / |tasks|

Schema_Pass  = valid_json_artifacts / 5
  (per task; report micro/macro separately)
  ALSO report first_pass vs post_normalize if both snapshots exist
```

---

## 四、建议新增测试脚本（确认后再写，本阶段不创建）

| 脚本（拟定路径） | 实验 | 付费？ |
|------------------|------|--------|
| `evaluation/datasets/hit5_qa.jsonl` | 2 | 否（数据） |
| `evaluation/datasets/faithfulness_qa.jsonl` | 1,3 | 否（数据） |
| `evaluation/eval_hit_at_k.py` | 2 | 否 |
| `evaluation/eval_schema_audit.py` | 6 | 否 |
| `evaluation/eval_faithfulness.py` | 1 | Judge 可选 |
| `evaluation/eval_citation.py` | 3 | Judge 可选 |
| `evaluation/eval_mcp_ab.py` + 日志解析 | 4 | **是**（Agent） |
| `evaluation/run_e2e_live.py`（增强 e2e_runner） | 5 | **是** |

生产代码（`scholarflow/scholar/**`、MCP server）**默认不改**；若必须挂钩子导出 tool 日志，单独开「观测-only」PR，经你确认。

---

## 五、预计运行成本（粗估）

| 阶段 | 成本 |
|------|------|
| 仅本地：Hit@5 + Schema + Golden E2E | ≈ 0 元；0.5–1 人日（含标注 Hit@5） |
| + 人工忠实度/引用（无 Judge） | +1–2 人日 |
| + Judge 忠实度/引用（50×2） | 约数十～数百次 LLM 调用（视模型） |
| + MCP A/B（10 题×2） | 约 20 次多步 Agent 跑；成本最高 |
| + 真实 10 任务全量 E2E | 约 10 次完整调研；成本与耗时最高 |

**推荐实施顺序（确认后）：**  
`Schema复现 → Golden E2E复现 → Hit@5（零付费） → 引用ID合法率 → （可选）Faithfulness/引用支持 → （可选）MCP A/B → （可选）Live E2E扩样`

---

## 六、需要的真实数据清单

1. **索引语料**：至少 `docs/scholar-flow/samples/rag-test-001/`（已有）  
2. **Hit@5 标注**：query → `gold_evidence_id[]`（新建）  
3. **忠实度/引用题**：query + 期望考察点（新建）  
4. **A/B 跑批日志**：每 run 的 tool name 序列（新建采集）  
5. **Schema 首次快照**（若要讲首次通过率）：Agent 原始 outputs（当前多已被 normalize）  
6. **环境记录**：模型名、`SCHOLAR_RAG_*`、git commit、时间戳（每次报告 metadata）

---

## 七、历史指标归类

| 指标 | 归类 |
|------|------|
| E2E 90%、Schema 97% | **可部分复现为「当前值」**；历史 90/97 **不能**从现报告证实；当前复现预期接近 **100%（Golden / 已有 artifacts）** |
| Hit@5 82%、引用 91%、忠实度提升、MCP↓77% | **必须重新建立评测**；结果未知，可能低于或高于目标 |
| 任何「已达到 xx%」话术 | 在新报告落地前，面试应改为「评测建设中 / 仅有结构硬门槛结果」 |

---

## 八、实验控制清单（实施时遵守）

1. 固定数据集版本（jsonl + git hash）  
2. 固定 RAG 配置（backend/模型/top_k）写入报告 metadata  
3. A/B 同题同序  
4. 失败样本保留在 `raw/`  
5. 禁止按目标百分比筛题  
6. 报告分栏：**历史目标 | 当前复现 | 备注**  
7. 不改正式业务逻辑迎合数字  
8. 本阶段不跑付费调用，待你确认实施范围

---

## 九、请你确认的实施范围（回复选项即可）

请回复例如：

- **P0**：只做零付费 — Schema + Golden E2E 复现 + Hit@5 题集与脚本  
- **P1**：P0 + 引用 ID 合法率 + 人工小样本忠实度（不做 Judge）  
- **P2**：P1 + MCP A/B（需 Gateway + API Key）  
- **P3**：P2 + 多任务 Live E2E  

确认前：**不编写评测脚本、不跑模型、不改生产代码。**

---

## 十、与简历的临时口径（在新结果出来前）

可说：

> 我们已有产物结构硬门槛评测：Golden 10/10、真实 rag-test-001 通过；Hybrid 检索链路可本地复现。忠实度/Hit@5/引用/MCP 降幅的专项评测方案已就绪，正在按固定题集重建，数字以复现报告为准。

不可说：

> 已实测忠实度提升到 0.84 / Hit@5=82% / MCP↓77%（在复现完成前）。
