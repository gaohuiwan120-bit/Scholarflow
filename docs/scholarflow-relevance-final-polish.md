# ScholarFlow 最终精修：论文相关性分级与下游证据约束

**日期：** 2026-10-19  
**范围：** 最小质量精修（不重构架构、不新开阶段、不重跑多次 live 全流程）  
**历史保留：** `sf-12fa1e2791cb`（succeeded）、`sf-5787ead265f0`、`sf-rel-e2e-1792380524` — **均未覆盖**

---

## 1. 原误判原因（基于 `sf-12fa1e2791cb`）

### 1.1 为何弱相关论文被接受

旧门控 `paper_is_relevant` 基本依赖 `score_paper` 阈值（短 query ≥ 4.0），外加仅针对 GitHub 社会学的硬拒绝：

| 论文（历史任务） | 门控分数/信号（当时） | 误判机制 |
|------------------|----------------------|----------|
| 遥感定向目标检测 survey | ~6.3；`title_phrase:deep learning` + survey；虽有 `sensing_without_compress` 惩罚 | **宽泛 bigram「deep learning」+6** 仍超过阈值 |
| Thrombectomy CT deep learning | ~4.9；`title_phrase:deep learning` | 同上，仅领域词重叠 |
| Deep Learning lecture notes | ~4.9；同上 | 同上 |

查询清洗为 `deep learning image compressed sensing` 后，`deep learning` 作为 contiguous bigram 命中标题即可拿高分；**「compressed sensing」未同时出现在弱相关标题中时，惩罚不足以把分数压到阈值下**。

### 1.2 字段如何参与判断

- **标题 / 摘要 / research_problem：** 进入 `score_paper` 的短语与词项匹配（旧逻辑）。  
- **methodology：** 旧门控**未**使用。  
- 新分级：`title + abstract + research_problem + methodology` 共同组成文本 blob，再做 core/supporting/irrelevant 规则（仍不编造分数；`score_paper` 仅用于排序）。

### 1.3 是否进入实验/报告核心

在 `sf-12fa1e2791cb` 中：**是**。5 篇全部进入 `paper_evidence` / `sources` / `experiment` 的 `upstream_paper_ids` 与报告正文；实验「Reproduce findings from」甚至列出遥感 survey。  
仓库 `Pytorch_ADMM-CSNet` 本身相关，问题在论文侧弱相关混入核心列表。

快照保留：`tests/last_full_workflow_e2e.json`、`data/tasks/sf-12fa1e2791cb/`。

---

## 2. 修改文件

| 文件 | 变更 |
|------|------|
| `scholarflow_api/graph/evidence_gate.py` | `classify_paper_relevance` → `core` / `supporting` / `irrelevant`；CS 主题专用规则；下游 claim/tier 校验；persist 时将 tier 写入 `limitations` |
| `scholarflow_api/graph/nodes.py` | 选文优先 core；无 core 则 paper/experiment fail；experiment 仅用 core 作 `upstream_paper_ids`；supporting 进 `upstream_supporting_paper_ids` + risks 背景句；Review 检查等级匹配 |
| `tests/test_relevance_tiers.py` | **新增** 分级与下游约束测试 |
| `docs/scholarflow-relevance-final-polish.md` | 本文件 |
| `docs/scholarflow-requirements-matrix.md` | 补充 8.6e |

---

## 3. core / supporting / irrelevant 对照

主题：`基于深度学习的图像压缩感知重建`

| 样本 | 期望 | 现判定 |
|------|------|--------|
| Image Compressed Sensing Reconstruction（深度学习重建） | core | core |
| Compressed Sensing… Data-Driven Learning（MRI CS） | core | core |
| Structured Compressed Sensing… | core | core |
| Sparse Recovery survey | supporting | supporting |
| Remote sensing oriented detection | irrelevant | irrelevant |
| Thrombectomy / ischemic stroke CT | irrelevant | irrelevant |
| Deep Learning lecture notes | irrelevant | irrelevant |

规则要点（CS 主题）：

- **core：** 明确 compressed/compressive sensing、图像 CS 重建、ISTA-Net/ADMM-CS 等，或 compress+sensing 共现 / image reconstruction + compress。  
- **supporting：** sparse recovery、measurement matrix 等组件，且非无关领域。  
- **irrelevant：** remote sensing / thrombectomy / lecture notes 等冒名领域，或仅有 deep learning 宽泛重叠。

非 CS 主题（如 RAG fixture）仍走 legacy 分数 → `core`/`irrelevant`，避免破坏既有 fixture 回归。

---

## 4. 下游证据使用

| 环节 | 行为 |
|------|------|
| paper_research | 只保留 core+supporting；CS 主题若 **0 core** → **failed**（证据不足，不凑数） |
| experiment_design | 假设/基线/实现步骤只引用 **core**；supporting 仅在 risks 中标注「Supporting (non-core) background」；`upstream_paper_ids`=core；`upstream_supporting_paper_ids`=supporting |
| review | 确定性规则审查（**非**独立 LLM Reviewer）；core alignment claim 必须绑定 core；等级不匹配 → unsupported/fail |
| assemble | `relevance_tier=…` 写入 limitations 以便溯源；无关文不进产物列表 |

---

## 5. 测试与回归统计

| 套件 | 结果 |
|------|------|
| `test_relevance_tiers.py` + 相关门控/图测试 | 33 passed（子集） |
| `apps/scholarflow-api` 全量（跳过 live_llm/sse/agent/bridge live） | **109 passed, 1 skipped** |
| 历史任务 | `sf-12fa1e2791cb` 仍为 succeeded；未改产物 |

覆盖：

- core 通过；sparse → supporting；遥感/血栓/讲义不进核心  
- 弱相关不主导实验；仅无关 → 工作流 failed  
- RAG fixture 仍可 succeeded  
- 未删除困难样本、未放宽阈值“作弊”、未改历史评测口径  

**未**自动重跑多次 live 全流程（按交付要求）。

---

## 6. 仍然存在的局限

1. 分级仍是**确定性启发式**，非语义向量/专家标注；边界论文（如泛“imaging inverse problems”）可能落错档。  
2. supporting 列表有限；未列出的数学组件可能被标 irrelevant。  
3. 非 CS 主题未启用三级细分（legacy 二元）。  
4. Review 仍是规则机，不会做深度方法学审查。  
5. `sf-12fa1e2791cb` 历史产物仍含弱相关（刻意保留对照，不回写）。

---

## 7. 暂停点

本精修完成，**等待确认**。不进入新阶段。
