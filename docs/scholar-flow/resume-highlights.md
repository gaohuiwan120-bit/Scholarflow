# ScholarFlow 简历要点（Agent 社招）

> 数字来自本仓库真实跑分（2026-07-21）。写简历时按岗位删减到 4–6 条。

---

## 项目标题

**ScholarFlow — 基于 ScholarFlow 的多智能体科研调研 Agent 平台**  
Python · LangGraph · MCP · Pydantic · Docker

---

## 推荐 Bullet（选 4–6 条）

1. 基于字节开源 **ScholarFlow** 增量设计科研 Agent 平台，采用 **4 Skill + MCP + Schema** 三层架构，未修改 LangGraph 核心，实现文献/代码/实验三路 Sub-Agent 编排。

2. 独立实现 **`scholar_mcp` MCP Server**（arXiv / GitHub / 矩阵 / 校验 / 组装 / RAG），带重试与 Docker 部署；真实 E2E 任务 `rag-test-001` 产出契约 **9 类文件**；产物库 RAG 使用 **bge-small-en-v1.5 + BM25 + RRF + hybrid-score 重排**，回答强制绑定 `evidence_id`/`source_url`。

3. 设计 **Pydantic 数据契约** 与 **9 类结构化研究产物**（JSON/CSV/Markdown），确定性生成对比矩阵与来源清单，降低纯 LLM 自由文本幻觉。

4. 搭建 **10-case Benchmark**（结构 + 质量 + 硬门槛）：Golden 模式 **E2E pass rate 100%**、平均分 **0.99**；真实 artifacts（RAG survey）**pass 100%**、平均分 **1.00**。

5. 提供 `compare_runs.py` / `normalize_and_score_e2e.py`，支持优化前后对比与沙箱产物归一化评分。

6. 输出完整工程文档（架构 / 契约 / Benchmark / 生产清单）与 MCP/Schema 单元测试。

---

## 量化数字（已填）

| 指标 | 数字 | 来源 |
|------|------|------|
| 真实 E2E pass rate | **100%** (1/1) | `evaluation/reports/e2e-rag-test-001.json` |
| 真实 E2E 平均分 | **1.00** | 同上（`rag-survey` / `rag-test-001`） |
| Golden 10-case pass rate | **100%** (10/10) | `evaluation/reports/golden-baseline.json` |
| Golden 平均分 | **0.99** | 同上 |
| 产物完整率 | **100%** | `artifact_completeness=1.0` |
| Schema 合法率 | **100%** | `schema_validity=1.0`（5/5 JSON） |
| URL 可追溯率 | **100%** | `url_validity=1.0` |

样本产物：`docs/scholar-flow/samples/rag-test-001/`  
沙箱原路径：`backend/.scholarflow/users/.../threads/6e2f2d96-.../user-data/outputs/rag-test-001/`

---

## 面试 30 秒 Elevator Pitch

> 我在 ScholarFlow 上做了 ScholarFlow，面向科研调研的多 Agent 扩展。用 4 个 Skill 编排，独立 MCP 接 arXiv 和 GitHub，输出走 Pydantic 契约落成 9 类文件。我跑通了真实 RAG 调研 E2E，硬门槛全过；另外有 10 个 topic 的 Golden benchmark，pass rate 100%。重点是可追溯来源和可自动评分，而不是再造一套 Agent 框架。

---

## 口径注意

- **可写**：真实任务产出 9 件套 + artifacts 评分通过；MCP 工具链已接入并用于检索/仓库。
- **慎写**：「10 个 topic 全部真人在线 E2E」——目前真人完整 artifacts 评分是 **1 个** RAG case；10/10 是 Golden 模式。
- **勿提交**：`.env`、GitHub/DeepSeek token。

---

## 可能被问的问题

| 问题 | 回答要点 |
|------|----------|
| 和 ScholarFlow 什么关系？ | 增量扩展，复用 Lead Agent / task / Sandbox，自研 MCP + Skill + Schema |
| 怎么防幻觉？ | Skill 规则 + source_url + verification_status + benchmark 抽检 |
| 评测可信吗？ | 结构自动 + 质量启发式 + 硬门槛；真实 case 已 spot check |
| 生产了吗？ | Docker 准生产；未上 K8s 多租户 |

---

## 相关文档

- [agent-guide.md](agent-guide.md) — Agent 全貌
- [benchmark.md](benchmark.md) — 评测方法
- [e2e-prompt.md](e2e-prompt.md) — 验收提示词
- [production.md](production.md) — 工程清单
