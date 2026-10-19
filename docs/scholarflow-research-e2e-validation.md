# ScholarFlow 完整科研工作流端到端复验

**日期：** 2026-10-19  
**主题：** 基于深度学习的图像压缩感知重建  
**入口：** `TaskStore.create` → `execute_stored_task` → `ResearchTaskRuntime` → LangGraph `research_orchestration`  
**快照：** `apps/scholarflow-api/tests/last_full_workflow_e2e.json`  
**产物目录：** `apps/scholarflow-api/data/tasks/sf-12fa1e2791cb/artifacts/`

**历史保留（未覆盖）：**

| 任务 | 状态 |
|------|------|
| `sf-5787ead265f0` | `partial_succeeded`（错配历史） |
| `sf-rel-e2e-1792380524` | `failed`（429 失败保护） |

未改 Golden / 冻结题集 / API-Key；未启 ScholarFlow Docker；`allow_fixture_fallback=False`。

---

## 1. task_id 与终态

| 字段 | 值 |
|------|-----|
| task_id | `sf-12fa1e2791cb` |
| TaskStore status | `succeeded` |
| overall_status | `succeeded` |
| review_decision | `pass` |
| requested data_mode | `live` |
| **effective_data_mode** | **`live`** |
| degradation_events | `[]` |
| 耗时 | ~7.9 s |
| 9 产物 | 全部落盘；manifest `data_mode=live` |

### 验收判定（与系统终态分开）

| 维度 | 判定 | 说明 |
|------|------|------|
| 全链路可跑通（TaskStore→Graph→MCP→产物） | **通过** | 见下节 |
| 仓库与主题相关 | **通过** | ADMM-CSNet 图像压缩感知实现 |
| 核心论文与主题相关 | **通过** | 至少 2 篇强相关 CS / data-driven CS |
| **全部**接受论文均紧扣「图像压缩感知重建」 | **未完全满足** | 3 篇弱相关仍被启发式放行（见 §4） |
| Review 为确定性规则（非 LLM） | 如实 | 动态 claim；无固定 Hybrid RAG slogan |
| 跨文件一致性 | **通过** | evidence_id / URL / upstream 对齐 |

**结论：系统终态 `succeeded`；严格主题纯度验收为「条件通过」——核心证据成立，门控对弱相关「deep learning」论文仍有漏放。未为通过验收放宽门控或改期望。**

---

## 2. 实际数据模式

- 请求：`data_mode=live`，`allow_fixture_fallback=false`
- 生效：`effective_data_mode=live`（无 fixture 混入）
- MCP 调用（均 `ok`）：
  1. `search_academic_papers` `{query: "deep learning image compressed sensing", max_results: 12}` → 1 attempt
  2. `get_repository_overview` `{repository: "lixing0810/Pytorch_ADMM-CSNet"}` → 1 attempt
  3. `assemble_task_artifacts` → live 组装 9 件套

清洗后 query（非整段中文指令、非 langchain/RAG 覆盖）：

- 论文：`deep learning image compressed sensing`
- 仓库：`deep learning image compressed sensing language:Python stars:>10`

---

## 3. 逐节点执行记录

时间戳为 Unix epoch（相对重叠即可）；`data_source` 为节点声明来源。

### 3.1 orchestrator

| 项 | 内容 |
|----|------|
| 状态 | succeeded |
| data_source | deterministic |
| 起止 | 1792383025.166 → 1792383025.166（0 ms） |
| 输入 | question=主题原文 |
| 输出 | ResearchPlan：`search_queries` 已清洗；`code_search_queries` 为主题+GitHub 过滤 |

### 3.2 paper_research（与 repo 并行）

| 项 | 内容 |
|----|------|
| 状态 | succeeded |
| data_source | **live_mcp** |
| 起止 | 1792383025.167 → 1792383029.411（4243 ms） |
| 输入 | 清洗 query；MCP max_results=12 |
| 输出 | 接受 5 篇；拒绝 6 篇（summary） |
| 证据 | 见 §4；URL 均为 `https://arxiv.org/abs/...` |

### 3.3 repository_analysis（与 paper 并行）

| 项 | 内容 |
|----|------|
| 状态 | succeeded |
| data_source | **live_mcp** |
| 起止 | 1792383025.168 → 1792383031.019（5850 ms） |
| 输入 | GitHub search → 选中 `lixing0810/Pytorch_ADMM-CSNet` |
| 输出 | 1 仓库 overview（含 README/模块列表） |
| 证据 | `repo-lixing0810-Pytorch_ADMM-CSNet` → https://github.com/lixing0810/Pytorch_ADMM-CSNet |

### 3.4 并行证据（时间窗）

```
paper: [3025.167 ──────────────── 3029.411]
repo:  [3025.168 ────────────────────────── 3031.019]
```

- `started_at` 几乎同时（Δ≈1 ms）
- 区间重叠：`parallel_overlap=true`
- 非仅凭子任务数量或总耗时推断

### 3.5 experiment_design

| 项 | 内容 |
|----|------|
| 状态 | succeeded |
| data_source | deterministic |
| 起止 | 1792383031.020 → 同（0 ms） |
| 输入 | 上游 papers + repos |
| 输出 | 假设/基线/管道引用 **实际标题与 `lixing0810/Pytorch_ADMM-CSNet`**；`upstream_paper_ids` / `upstream_repo_ids` 与上游一致 |
| 非 RAG 固定模板 | 无 Naive RAG / Hybrid retrieval slogan |

### 3.6 review（确定性规则审查）

| 项 | 内容 |
|----|------|
| 状态 | succeeded（decision=pass） |
| data_source | deterministic |
| 起止 | 1792383031.020 → 1792383031.043（23 ms） |
| claims | 4 条动态 claim，均绑定本次 `evidence_id` |
| 固定 Hybrid RAG claim | **不存在** |
| 判定 | 规则认为 linked 证据通过相关性检查 → `supported`（**≠ LLM Reviewer**） |

### 3.7 assemble

| 项 | 内容 |
|----|------|
| 状态 | succeeded |
| data_source | live_mcp |
| 起止 | 1792383031.043 → 1792383032.972（1928 ms） |
| 输出 | 9 artifacts；manifest `data_mode=live` |

---

## 4. 论文与仓库相关性核验

### 4.1 论文（人工主题核验 vs 门控）

| evidence_id | 标题（摘要） | 人工判定 | 门控 |
|-------------|--------------|----------|------|
| paper-2410.18954v2 | Structured Compressed Sensing… | **强相关**（压缩感知） | 接受 score 14.25 |
| paper-1903.07824v1 | CS → clinical / data-driven learning | **相关**（CS+学习，偏 MRI） | 接受 11.0 |
| paper-2302.10473v6 | 遥感定向目标检测 survey | **弱/无关**（remote sensing≠CS） | 误放 6.3（已有 `sensing_without_compress` 惩罚仍过阈） |
| paper-2302.04143v2 | Thrombectomy CT deep learning | **无关** | 误放 4.9 |
| paper-2301.00942v1 | DL lecture notes | **无关** | 误放 4.9 |

门控从 12 条中拒绝 6 条（已滤掉部分噪声），但 top-5 截断仍混入弱相关。

### 4.2 仓库

| evidence_id | 仓库 | 人工判定 |
|-------------|------|----------|
| repo-lixing0810-Pytorch_ADMM-CSNet | ADMM-CSNet：Image Compressive Sensing（TPAMI 2019）PyTorch | **强相关**；含 `train.py`/`test.py`/`csnet_model/` 等实现痕迹 |

---

## 5. Review 结果

见 `evidence_review.json`：4 条 claim，全部 `supported`，理由均为规则机「passes topic relevance checks」。  
因弱相关论文也被门控标为通过，**topic_alignment claim 在规则意义上成立，在严格科研语义上过宽**——记为未覆盖风险，非本轮重构范围。

---

## 6. 产物一致性检查

| 文件 | 存在 | 备注 |
|------|------|------|
| research_plan.json | ✓ | 清洗后 search_queries |
| paper_evidence.json | ✓ | 5 篇 live；source_url 可点开 |
| paper_matrix.csv | ✓ | |
| repository_evidence.json | ✓ | ADMM-CSNet |
| repository_matrix.csv | ✓ | |
| experiment_plan.md | ✓ | 引用上游标题与仓库名 |
| evidence_review.json | ✓ | 动态 claim |
| sources.json | ✓ | id↔url 与上游一致 |
| research_report.md | ✓ | 与 evidence 列表一致 |
| manifest.json | ✓ | 9 项；`data_mode=live` |

交叉检查（脚本）：`consistency.ok=true`，无孤儿 evidence_id、无固定 RAG claim、experiment upstream ⊆ 上游集合。  
无虚构下载包；证据均为 arXiv abs / GitHub 公开页。

---

## 7. 失败、降级与未覆盖

| 项 | 状态 |
|----|------|
| 本轮 429 | 未触发（arXiv 200 OK） |
| fixture 降级 | 未发生（`effective_data_mode=live`） |
| 历史任务 | 保留 |
| 弱相关论文漏放 | **未解决**（启发式阈值残留） |
| 独立 LLM Reviewer | **未实现**（仍为规则审查） |
| 诊断专用失败报告文件 | 本轮成功路径未行使；失败时仍 assemble skip |

---

## 8. 总结表

| 问题 | 答案 |
|------|------|
| 是否经 TaskStore / ResearchTaskRuntime / 完整 StateGraph？ | **是** |
| paper∥repo 是否并行？ | **是**（时间窗重叠） |
| 是否真 MCP？ | **是**（search_academic_papers + get_repository_overview + assemble） |
| 仓库是否图像 CS 实现？ | **是**（ADMM-CSNet） |
| 实验是否读真实上游？ | **是** |
| Review 是否本次证据？ | **是**（规则机） |
| 报告与来源一致？ | **是** |
| 严格「全部论文紧扣主题」？ | **否（条件通过）** |

**暂停，等待确认。不进入新阶段。**
