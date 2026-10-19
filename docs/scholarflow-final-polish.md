# ScholarFlow 最终精细化收尾审计（阶段 1–7 后）

> 目标：提高质量与面试可信度；不重写架构；不伪造历史 0.62；不把未达标指标硬编码为达标。  
> 日期：2026-10-18。冻结题集 `evaluation/rag_qa/v1` **未改**。新对照结果写入 `evaluation/reports/rag_qa/final_polish_2026-10-18/`（保留历史报告）。

---

## 1. RAG 质量与拒答（q43–q47）

### 历史失败（phase4 审计，未改原始口径）

| Profile | refuse_accuracy | 失败题 |
|---------|-----------------|--------|
| baseline | 0.4 | q43–q45 |
| full_rag | 0.2 | q43–q45,q47 |

根因：弱相关 hit 仍被拼成「有据」bullet；主题重叠把疑问词/`artifacts` 算进命中。

### 必要修复（代码）

1. `rag_answer`：仅当 `sufficient` 才作答；不足时**空 hit 拒答**（不再用弱命中拼答案）。  
2. `evidence_is_sufficient`：扩展 stopwords；收紧 overlap；对 award/phone/secret/gpu hour 等 **claim marker** 要求证据中出现。

### 对照评测（baseline，本机）

| 指标 | 收尾前（同目录首轮） | 收尾后 |
|------|----------------------|--------|
| refuse_accuracy (q43–q47) | 0.4 | **1.0**（5/5） |
| faithfulness_mean | 0.63 | **0.58** |
| top5_hit_rate (denom 37) | 0.7838 | **0.6757** |
| citation_accuracy_mean | 0.9889 | **0.9846** |

**权衡（如实）：** 拒答显著改善；因 sufficiency 变严，语料内 Top-5 / 忠实度均值下降。面试应说「拒答可靠性优先于弱命中硬答」，**不要**同时宣称忠实度已达 0.84。  
**仍禁止：** 把缺失的历史 **0.62** 补写成真实基线。

引用：citation 仍为结构校验（id/URL）；非强语义蕴含——与 phase4 审计一致。

---

## 2. 多 Agent 真实性

| 项 | 结论 |
|----|------|
| 四类工作流 | `paper_research` / `repository_analysis` / `experiment_design` / `research_orchestration` — API+图实测 |
| 职责与依赖 | experiment `depends_on` paper+repo；assemble 依赖 review |
| 并行证据 | `test_paper_and_repo_parallel_overlap` + Bench off-06/e2e-03 时间窗重叠 |
| Review | `force_fail_review` → failed；assemble skipped |
| 确定性 vs 模型 | **节点多为确定性模板 + fixture/MCP 数据**；RAG 答案为检索拼装，**非**生成式 LLM 多 Agent 对辩。面试勿虚构「每个 Sub-Agent 都调大模型」 |

---

## 3. MCP 调用量

| 实验 | MCP calls | 说明 |
|------|-----------|------|
| cold_mcp（空语料+mock） | **50** | 全量 50 题触发 |
| full_rag_mcp_mock（有索引+mock） | **22** | 全量降低 **56%** |
| 同主题 needs_mcp（q35–q42） | cold **10** → indexed **6** | 同主题降低 **40%** |

相对简历 **77%：仍未达标**（历史 audit 同主题曾测 60%；本轮同主题 40%）。  
质量同看：full_rag_mcp_mock faith≈0.86、top5≈0.81（含 CE+mock 补检，**勿与纯 baseline 拒答口径混谈**）。

---

## 4. 任务持久化

| 原状 | 阶段 1 `TaskStore` 纯内存，进程重启丢状态 |
|------|------------------------------------------|
| 轻量改进 | `task_state.json` 落盘到 `SCHOLARFLOW_TASKS_DIR/<id>/`；`get` 可冷加载 |
| 测试 | `apps/scholarflow-api/tests/test_task_store_persist.py` 通过 |
| 非目标 | 未引入 Redis/DB；不破坏现有 API |

产物落盘（9 件套）本已存在；本次补的是**任务状态**可恢复。

---

## 5. Sandbox

| 项 | 状态 |
|----|------|
| Docker | `--network=none`（默认）、`--memory`、`--cpus`、`--pids-limit`、`--read-only`、`tmpfs`、非 root、**新增 `no-new-privileges`**；bind 仅 task workdir |
| process_jail（Windows） | 超时/截断/cwd 隔离有；**无硬内存 cap、无 OS 网络隔离**；绝对路径可读宿主机（已记录） |
| 宣称边界 | **不可**称生产级隔离；**不**启动 scholarflow 整栈 |

---

## 6. 最终回归

- pytest：task persist + research graph/API + sandbox + RAG refuse — **27 passed, 1 skipped**  
- Golden snapshot / 历史报告：**保留**（新结果进 `final_polish_2026-10-18/`）  
- `git dirty=true`：未 reset/clean/commit  

---

## 文件变更清单（本收尾）

| 路径 | 变更 |
|------|------|
| `scholarflow/scholar/rag/pipeline.py` | sufficiency 门控拒答 |
| `scholarflow/scholar/rag/retrieve.py` | stopwords / overlap / claim markers |
| `scholarflow/scholar/sandbox/backends.py` | docker `no-new-privileges` |
| `scholarflow_api/services/task_store.py` | JSON 状态持久化 |
| `tests/test_task_store_persist.py` | 新增 |
| `backend/tests/test_scholar_rag_refuse.py` | 新增 |
| `docs/scholarflow-final-polish.md` | 本文件 |
| `docs/scholarflow-requirements-matrix.md` | 更新最终标注 |
| `evaluation/reports/rag_qa/final_polish_2026-10-18/` | 新对照评测（不覆盖冻结历史叙事） |

---

## 仍未解决 / 不可宣称

1. 历史忠实度 **0.62** 无原始记录。  
2. MCP↓ **77%** 未达标（本轮全量 56%、同主题 40%）。  
3. 收紧拒答后 baseline Top-5/faith **低于** phase4 宽松口径数字——勿同时吹满分。  
4. 引用准确率为结构指标，非强语义。  
5. Sandbox 非生产隔离；fixture ≠ live。  
6. 多 Agent 叙事须区分确定性节点与真实 LLM 推理。
