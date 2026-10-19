# ScholarFlow `sf-fcb37987da7b` 定点排查与修复

**日期：** 2026-10-19  
**失败任务（只读保留）：** `sf-fcb37987da7b`（`partial_succeeded` / `mixed_degraded`）  
**复验任务：** `sf-bed70401a1fa`、`sf-d8aeed8c630d`、`sf-fc98856e797b`（均未覆盖历史）  
**快照：** `apps/scholarflow-api/tests/last_fcb379_fix_e2e.json`

---

## 1. 根因分析（实际调用链）

### 1.1 `sf-fcb37987da7b` 产物指纹 = **旧版 LangGraph 节点**

| 产物特征 | 旧代码行为 | 当前磁盘代码（修复后） |
|----------|------------|------------------------|
| `search_queries` = 整段中文指令 | `orchestrator_node` 曾把 `question` 原样写入 | `extract_paper_query` → 短关键词 |
| `code_search_queries` = `langchain RAG` | 硬编码 | `extract_repo_search_query` / CS→ISTA-Net 提示 |
| `experiment_plan` = Naive RAG / BM25 / NQ | 固定 RAG 模板 | 按 CS 主题生成 PSNR/SSIM 方案 |
| `evidence_review` = Hybrid RAG `supported` | 固定 claim | 动态 claim + tier 校验 |
| 仓库 = `langchain-ai/langchain` | `fetch_repo_via_mcp("langchain-ai/langchain")` | `resolve_live_repository` |

**结论：** 该任务在 **仍加载旧 `nodes.py` 的 API 进程** 上执行（创建于 2026-10-19T04:23Z，早于/并行于本轮精修落地）。磁盘上的 `evidence_gate.py` 三级分类与失败传播 **未被该次进程调用**。

排查时已杀掉旧 `scholarflow_api` / `uvicorn:8100` 进程（PID 23544、20532），避免继续跑旧字节码。

### 1.2 对应文件 / 函数

| 问题 | 文件 | 函数 |
|------|------|------|
| 查询清洗 / 短标题 | `graph/evidence_gate.py` | `extract_paper_query`, `extract_short_topic_title`, `extract_repo_search_query` |
| 编排写入 plan | `graph/nodes.py` | `orchestrator_node` |
| 论文门控 + 无 core 失败 | `graph/nodes.py` | `paper_research_node` + `classify_paper_relevance` |
| 仓库解析 | `graph/adapters.py` | `resolve_live_repository` |
| 实验 / Review | `graph/nodes.py` | `experiment_design_node`, `review_node` |

---

## 2. 本轮最小修复（相对 fcb379）

1. **查询：** 括号英文题名折叠为 `image compressed sensing reconstruction deep learning`；禁止整段指令作唯一 query；仓库查询去掉易碎括号，CS 主题用 `ISTA-Net`/`ADMM-CSNet` 关键词。  
2. **分级：** MRI/临床 CS → `supporting`；遥感复原等 → `irrelevant`；自然图像 CS 重建 → `core`。  
3. **实验：** CS 主题输出 PSNR/SSIM/采样率方案；**删除** Naive RAG/BM25/NQ/SQuAD 固定模板。  
4. **Review：** 无 Hybrid RAG 固定 claim；无 core → 不能完整成功。  
5. **仓库提示：** CS → `jianzhangcs/ISTA-Net`（非 langchain）；搜索失败时仍可尝试 overview。  
6. **无 core 时备用论文 query** 一次：`image compressive sensing deep learning reconstruction`。  
7. **短标题：** `research_plan.title` = 可读主题；`objective` 保留完整指令。

---

## 3. 离线测试

`pytest`（跳过 live_llm/sse/agent/bridge live）：**119+ passed**（含 `test_fcb379_regression.py`）。

覆盖：长中文指令清洗、非 langchain 仓库 query、MRI/遥感分级、无 RAG 实验模板、无 Hybrid RAG claim、无 core 失败、历史 `sf-fcb37987da7b` 未被覆盖。

---

## 4. Live 复验（分开报告）

### 4.1 已验证（真实外部）

| 项 | 结果 |
|----|------|
| 清洗后 arXiv query | `image compressed sensing reconstruction deep learning`（HTTP 200） |
| plan 标题 | `Deep Learning for Image Compressed Sensing Reconstruction` |
| code_search | 无 langchain / RAG |
| core 论文（`sf-fc98856e797b`） | `paper-2207.06746v1`, `paper-0812.3137v1` |
| supporting | `paper-2301.02033v1`, `paper-1907.11711v1` |
| RAG 实验 / Review claim | **未出现** |
| 失败传播 | 无仓库时 **failed**，不混入 langchain fixture，不写伪成功 9 产物 |

### 4.2 未通过完整 live 验收的原因

**GitHub API 本机不可达**（`All connection attempts failed` 于 search 与 `get_repository_overview`）。  
因此仓库节点失败 → 编排失败 → **无九类产物落盘**（符合“无核心仓库证据不得伪装成功”）。

| 路径 | 结论 |
|------|------|
| 查询清洗 + 论文 live + 分级 | **通过** |
| GitHub live 仓库 | **本环境网络失败** |
| 完整九产物 live 成功 | **未达成**（因仓库，非因 RAG 回归） |

历史任务状态仍为：`sf-fcb37987da7b=partial_succeeded`（未改）。

---

## 5. 局限与后续建议

1. 待 GitHub 连通后，用同一问题再跑一次 live，应能选中 `jianzhangcs/ISTA-Net`（或搜索命中的 CS 仓库）并产出一致九件套。  
2. 重启 API（`scripts/start_scholarflow_api.ps1`）后再从 UI 提交，避免旧进程。  
3. 分级仍为启发式；边界论文需人工抽检。

---

## 6. 暂停

定点修复与离线回归完成；完整 live 九产物因 GitHub 网络中断未达标。**等待确认，不进入新阶段。**
