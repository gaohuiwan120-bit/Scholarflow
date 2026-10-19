# ScholarFlow Phase 6 — Agent Benchmark、Golden Answer 回归与全链路质量验收

## 目标

建立可重复运行的 Agent 评测体系：20 离线 + 10 E2E 经 **ScholarFlow FastAPI** 真实入口执行，固化指标口径，产出 JSON/MD 报告与 Golden 快照回归。

**禁止**：用旧 `run_benchmark.py --mode golden` 合成分冒充 E2E 完成率；跑分后改口径凑简历数字。

---

## 指标口径（冻结）

完整定义见 [`evaluation/agent_bench/v1/METRICS.md`](../evaluation/agent_bench/v1/METRICS.md)。  
轻量核查见 [`docs/scholarflow-phase6-audit.md`](scholarflow-phase6-audit.md)（只读复算，不改原始口径）。

| 指标 | 公式 | 简历目标 | 本机实测（fixture） |
|------|------|----------|---------------------|
| **E2E 任务完成率** | `#outcome=succeeded / 10` | 90% | **90%** |
| **E2E 结果正确率** | `#outcome==expect / 10` | （预定义对照） | **100%** |
| Schema 通过率 | schema 校验事件通过数/总数 | ≥97% | **100%**（10/10 事件） |
| 离线结果正确率 | expect 匹配数 / 20 | — | **100%**（20/20） |

说明：

- 桶分布为 `9 succeeded + 1 correct_refuse`：正确拒答计入正确率，**不计入**完成率 → 故完成率 90% 而非 100%。
- 负路径 e2e-07：bench `outcome=succeeded`（校验通过），API `status=failed`。
- Git：`930042d…`，`dirty=true`（未自动 commit）。
- 旧 `golden-baseline.json` 合成分 **≠** 本阶段完成率。
- Schema 分母仅为执行了 `schema_all_json` 的事件（off-09 + e2e-05 = 10），见审计文档。

---

## 统一入口

```powershell
cd E:\AgentProject\scholarflow_project
$env:PYTHONPATH = "$PWD;$PWD\apps\scholarflow-api;$PWD\backend\packages\harness"
backend\.venv\Scripts\python.exe evaluation\run_agent_bench.py --suite all --update-golden
```

| `--suite` | 含义 |
|-----------|------|
| `offline` | 20 离线 |
| `e2e` | 10 E2E |
| `rag` | 现有 50 题 RAG（可选） |
| `sandbox` | process_jail + Docker verify 脚本 |
| `golden` | 重跑并与 snapshot 比较 |
| `all` | offline + e2e + sandbox（加 `--with-rag` 含 RAG-50） |

报告：

- [`evaluation/reports/agent-bench-latest.json`](../evaluation/reports/agent-bench-latest.json)
- [`evaluation/reports/agent-bench-latest.md`](../evaluation/reports/agent-bench-latest.md)
- Golden：[`evaluation/agent_bench/v1/golden/snapshot.json`](../evaluation/agent_bench/v1/golden/snapshot.json)

---

## 任务集

| 套件 | 规格文件 | 入口 |
|------|----------|------|
| 离线 20 | `evaluation/agent_bench/v1/offline_tasks.json` | FastAPI TestClient；off-16 为公开 `rag_answer` + mock MCP |
| E2E 10 | `evaluation/agent_bench/v1/e2e_tasks.json` | 全部 FastAPI TestClient |

覆盖：论文/仓库/实验/编排/依赖/并行/MCP schema/失败传播/Schema/九产物/格式/溯源/RAG/CE stub/补检信号/补检拒答/正常回答/Sandbox 成功与拒绝。

---

## 产品小修（支撑单流验收）

[`review_node`](../apps/scholarflow-api/scholarflow_api/graph/nodes.py)：`repository_analysis` 无 papers 时改为 `needs_supplement`（与 paper-only 缺 repos 对称），避免仓库单流被硬 fail。

---

## Sandbox 附带结果

同次 `--suite all`：

- process_jail verify：**通过**
- Docker 最小 verify：**通过**
- 仍保留：process_jail 非生产级隔离；绝对路径读宿主机缺口见 phase5。

---

## 与旧脚手架关系

| 旧资产 | 阶段 6 角色 |
|--------|-------------|
| `tasks.json` / `benchmark_tasks.json` | 保留兼容；**不**作为 Agent Bench 真跑规格 |
| `run_benchmark.py --mode golden` | 产物打分器；**禁止**写入 `e2e_completion_rate` |
| `e2e_runner.py`（ScholarFlow Gateway） | 保留；本阶段 E2E 走 ScholarFlow API |

---

## 状态总表

| 项 | 状态 |
|----|------|
| 20 离线经 Runtime/API | **已实现且已验证**（20/20） |
| 10 E2E FastAPI | **已实现且已验证**（完成率 90%） |
| Schema 口径 + 实测 | **已实现且已验证**（100%） |
| Golden Answer 快照回归 | **已实现且已验证**（首版 snapshot 已冻结） |
| 统一 CLI + JSON/MD | **已实现且已验证** |
| 简历 90%/97% | **本机 fixture 实测达标**；换环境需重跑，勿改口径 |
| Live 外网 E2E | **未并入完成率**（可选 `--data-mode live`，单独报告） |
