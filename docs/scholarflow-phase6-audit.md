# 阶段 6 轻量验收核查（只读口径核对）

> 核查时间：2026-10-18。不重写阶段 1–5，不修改冻结评测口径，不伪造更高通过率。  
> 原始跑分：`suite=all`，`timestamp=2026-10-18T03:55:22+00:00`，`data_mode=fixture`，`update_golden=true`。  
> 随后 `--suite golden`（无 update）复跑确认 compare **pass**；为避免覆盖，后续 golden 单独对比默认写入 `agent-bench-golden-compare.json`。

---

## 1. 20 离线是否真实执行

| 检查项 | 结论 |
|--------|------|
| 条数 | `offline_results` **20** 条，ID `off-01`…`off-20` |
| 入口 | 绝大多数 `entry=api_task` → FastAPI `POST /api/v1/tasks` + 轮询；`off-07`=`api_mcp_tools`；`off-16`=`rag_pipeline_mock_mcp`（公开 `rag_answer`+mock MCP）；`off-18/19`=`api_sandbox` |
| 逐任务结果 | 每条含 `outcome/status/assertions/duration_ms/schema_checks` |
| 通过 | outcome==expect：**20/20**（结果正确率 100%） |

---

## 2. 10 E2E 是否经真实 API 入口

| ID | entry | kind | API status | bench outcome | expect |
|----|-------|------|------------|---------------|--------|
| e2e-01 | api_task | paper_research | partial_succeeded | succeeded | succeeded |
| e2e-02 | api_task | repository_analysis | partial_succeeded | succeeded | succeeded |
| e2e-03 | api_task | research_orchestration | succeeded | succeeded | succeeded |
| e2e-04 | api_task | experiment_design | succeeded | succeeded | succeeded |
| e2e-05 | api_task | research_orchestration | succeeded | succeeded | succeeded |
| e2e-06 | api_task | research_orchestration | succeeded | succeeded | succeeded |
| e2e-07 | api_task | research_orchestration | **failed**（force_fail_paper） | succeeded | succeeded |
| e2e-08 | api_task | rag_query | succeeded（任务受理） | **correct_refuse** | correct_refuse |
| e2e-09 | api_task | research_orchestration | succeeded | succeeded | succeeded |
| e2e-10 | api_sandbox_pair | — | sandbox statuses | succeeded | succeeded |

全部经 FastAPI TestClient，**不是**内部单函数冒充 E2E，也**不是**旧 ScholarFlow Gateway runner。

---

## 3–4. `9 succeeded + 1 correct_refuse` 与 90% 的关系

预先冻结（`METRICS.md`）的**两套**指标，不可混用：

| 指标 | 预定义公式 | 本跑实测 |
|------|------------|----------|
| **任务完成率** `e2e_completion_rate`（简历「端到端完成率」） | `#\{outcome=succeeded\} / 10`；`correct_refuse` **不算**完成 | **9/10 = 90%** |
| **结果正确率** `e2e_result_correctness_rate` | `#\{outcome == expect_outcome\} / 10` | **10/10 = 100%** |

因此：e2e-08 预期就是正确拒答 → 结果正确，但按冻结完成率口径**故意不进分子**，完成率显示 90% 而非 100%。  
**不是**事后改口径；也不是「最后一个失败」。

e2e-07：bench `outcome=succeeded` 表示「失败路径校验通过」，API `status=failed`。

---

## 5. Schema 100% 分母

| 项 | 内容 |
|----|------|
| 校验对象 | 仅跑了 `schema_all_json` 的任务：`off-09`、`e2e-05` |
| 每任务事件 | 5 个 JSON：`research_plan` / `paper_evidence` / `repository_evidence` / `evidence_review` / `sources` |
| 分母 | **10**（2×5）；通过 **10** → 100% |
| 失败标准 | `validate_json_artifact`（Pydantic 全量）抛错即失败；非「字段存在」 |
| 局限（如实） | 并非全部 30 个任务都计入 schema 分母；仅「期望并执行 schema 断言」的事件计入（符合冻结 METRICS） |

---

## 6. Golden 是否参与版本比较

| 项 | 结论 |
|----|------|
| 快照 | `evaluation/agent_bench/v1/golden/snapshot.json`（30 tasks） |
| 首跑 | `--update-golden` 写入基准 |
| 复跑 | `--suite golden`（无 update）→ `compare_snapshots` → **pass / diff_count=0** |
| 结论 | 具备字段级比较能力；首跑是建立基线，复跑证实 compare 路径可用 |

---

## 7. Sandbox 覆盖

| 后端 | 覆盖 | 证据 |
|------|------|------|
| process_jail | 成功 / 超时 / 失败 exit / 输出截断 / 目录隔离；并记录绝对路径读宿主机缺口 | `ALL_PROCESS_JAIL_CHECKS_PASSED`；`ABS_HOST_READ_GAP` |
| Docker | 真实 `backend=docker`，输出 `in-docker` / `2` | `DOCKER_MIN_OK`（按需 alpine 容器，非 scholarflow 整栈） |

---

## 8. `dirty=true` 记录方式

报告字段：

- `git_commit`: `930042d245402749d89039ca39799db1de4c3768`
- `git_dirty`: `true`（工作区有未提交 ScholarFlow 等改动；**未**自动 commit）
- `suite_version`: `agent-bench-v1`
- `config.data_mode`: `fixture`（**不是** live）

---

## 核查结论

阶段 6 交付方向可接受。关键数字可复算；完成率与正确率需在面试/简历中**分开说清**。fixture ≠ live；Sandbox ≠ 生产级隔离。
