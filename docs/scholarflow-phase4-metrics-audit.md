# 阶段 4 指标审计（只核查，不改结果）

审计日期：2026-10-18。原始结果未改动。

证据目录：
- `evaluation/rag_qa/v1/questions.json`
- `evaluation/rag_qa_metrics.py`
- `evaluation/run_rag_qa_eval.py`
- `evaluation/reports/rag_qa/*_latest_summary.json` / `*_latest_raw.json`
- `backend/packages/harness/scholarflow/scholar/rag/citation.py`

---

## 1. 忠实度 0.790 / 0.853 的评分方式

**方式：** 自动词面子串匹配，**无 LLM Judge、无人工模型**。

公式（`evaluation/rag_qa_metrics.py::faithfulness`）：

```
blob = casefold(answer + " " + join(evidence_texts))
faithfulness(q) = |{ p in reference_points | p.casefold() ⊆ blob }| / |reference_points|
若 reference_points 为空 → 记 1.0
faithfulness_mean = mean(faithfulness(q) for all 50 questions)
```

| 值 | Profile | 分母 | 评判模型 |
|----|---------|------|----------|
| 0.790 | `baseline` | **50 题**全部题目的题目级分数均值 | **无**（纯字符串） |
| 0.853 | `full_rag` | 同上 50 题 | **无** |

原始：`baseline_latest_summary.json`、`full_rag_latest_summary.json`。

**局限（待验证强度）：** 子串命中 ≠ 语义忠实；空 `reference_points` 记满分会抬高均值。

---

## 2. 简历 0.62 基线是否可核验？

**结论：仓库内无可核验的原始实验记录。**

- `docs/scholar-flow/ScholarFlow简历与真实源码差异核验报告.md`、`ScholarFlow评测复现方案.md`、阶段 0 审计均写明 **无 50 题集 / 无 0.62 报告**。
- 当前 `baseline=0.790` 来自 **新建** `rag_qa_v1` + 上述子串协议，**口径与历史宣称的 0.62 不可对齐**。
- 因此「0.62→0.84」**不能**由本次实验直接证明「相对旧基线提升」；只能报告 **当前协议下** baseline 0.79 → full_rag 0.853。

---

## 3. Top-5：0.811 / 0.838 / 0.865

**统计单元：题目（question）。**

公式（`top5_hit`）：

```
对有 gold_evidence_ids 的题目：
  hit = 1 若 ∃ g ∈ gold_evidence_ids 且 g ∈ retrieved_ids[:5]
  否则 0
top5_hit_rate = sum(hit) / |{q | gold_evidence_ids 非空}|
```

| Profile | rate | 命中数/分母 |
|---------|------|-------------|
| baseline | 0.8108 | **30/37** |
| no_mcp (CE) | 0.8378 | **31/37** |
| full_rag | 0.8649 | **32/37** |

分母 **37** = 50 题中标注了 `gold_evidence_ids` 的题（不含 needs_mcp / should_refuse 等无 gold 题）。

---

## 4. 引用准确率 ~0.992 的分母与校验深度

**分母：** 50 题中 `citation_report.citation_accuracy` 非空的题目数（实测 **50**）。

**题目级准确率**（`citation.verify_citations`）：

```
accuracy = (cited_markers - invalid_markers) / cited_markers
（无引用标记时 accuracy=None，不计入均值）
```

每条 `〔evidence_id (url)〕` 检查：
1. evidence_id ∈ 当前允许证据集
2. URL 与证据记录一致（非仅「像 URL」）
3. 引用前 320 字符窗口与证据文本 **token overlap ≥ 0.08**（弱内容支持）

**未做：** 主张级自然语言蕴含、人工抽检归档。  
故 0.992 是 **结构+弱内容 overlap** 指标，**不等于**强语义「引用内容完全支持主张」。

---

## 5. baseline / no_mcp / full_rag 是否可比？

| 维度 | baseline | no_mcp | full_rag |
|------|----------|--------|----------|
| 题集 | rag_qa_v1 50 题 | 同 | 同 |
| 语料 | rag-test-001 索引 | 同 | 同 + live MCP 补入证据 |
| 重排 | hybrid-score | cross-encoder ONNX | cross-encoder |
| MCP | **关** (`ENABLE_MCP=0`) | **关** | **开且 live**（当时 `SCHOLARFLOW_LIVE_MCP=1`） |
| 数据模式 | fixture | fixture | **live** |

**可比部分：** baseline ↔ no_mcp（同题同库、仅重排不同）。  
**不完全可比：** full_rag 额外 live MCP 改变证据池与答案，忠实度/Top-5 提升 **混杂了 CE + 补检**。

---

## 6. MCP `30→15` 与同主题 `20→8`

来源：`mcp_reduction_measured.json`（cold_mcp raw vs full_rag_mcp_mock raw）。

| 实验 | 后端 | 口径 |
|------|------|------|
| cold_mcp | **Mock MCP**（`MCP_MOCK=1`），空语料 | 每轮 `mcp_rounds[].tools` 条目数求和 |
| full_rag_mcp_mock | **Mock MCP** + 已索引语料 | 同上 |
| 同主题 | `gold_evidence_ids` 非空的题目上的 MCP 次数 | 20→8 |

**不是** live arXiv/GitHub 调用计数。重试：每轮每次 tool 计 1；多轮则累加。

全量降低 **50%**；同主题 **60%**；相对简历 **77%：未达标**。

---

## 7. baseline MCP=0 vs full_rag MCP=28

- baseline：**故意关闭**补检 → MCP=0 是配置结果，不是「检索已足够」。
- full_rag：live 补检开启 → 不足题触发真实 MCP，合计 28。

**不宜**用「0 vs 28」证明「补检增加了质量且调用更省」；MCP 降幅应使用 **cold_mcp vs indexed**（见上）。baseline↔full_rag 的质量对比也因 MCP 混杂而不纯。

---

## 8. 拒答准确性（should_refuse：q43–q47）

判定（`refuse_ok`）：需出现证据不足/拒答/low confidence/`need_mcp_fallback`，且答案不含 api key/phone/best paper 等。

| Profile | refuse_accuracy | 失败题（raw） |
|---------|-----------------|---------------|
| baseline | 0.4 | q43,q44,q45 失败；q46,q47 通过 |
| no_mcp | 0.4 | q44,q45,q47 失败 |
| full_rag | 0.2 | q43,q44,q45,q47 失败；仅 q46 通过 |

**失败原因：** 检索仍返回语料片段并组装成「看起来像有据」的 bullet，**未走明确拒答**；full_rag 时部分题还触发 MCP，进一步降低拒答率。

---

## 对简历数字的最终判定

| 简历宣称 | 当前实验是否直接支持 |
|----------|----------------------|
| 忠实度 0.62→0.84 | **否**（无 0.62 原始记录；现协议 baseline 已是 0.79） |
| full 达 ~0.84 | **弱支持**（full_rag live **0.853**，但含 MCP 混杂 + 子串协议） |
| Top-5 82% | **支持**（CE no_mcp 83.8%；full_rag 86.5%；分母 37） |
| 引用 91% | **结构指标支持**（≥98%）；**强语义支持待验证** |
| MCP↓77% | **不支持**（同主题 mock 实测 **60%**） |

---

## 审计原则落实

本次**未**修改 `questions.json`、原始 raw/summary、评测口径或结果数字。
