# ScholarFlow Phase 8.6 — 最终系统评测与发布验收

- **status**: PASS（有条件发布：能力边界见 §7–§8）
- **tested_at (UTC)**: `2026-10-18`
- **约束遵守**: 未改 API-Key；未启动 ScholarFlow Docker；未覆盖冻结题集 / Golden snapshot；RAG 新结果写入独立目录
- **综合科研浏览器 E2E 数据模式**: **真实 LLM + fixture 工作流**（**不是**全链路 live MCP）

---

## 1. 测试分类与实际命令

| 分类 | 命令 | 说明 |
|------|------|------|
| Mock/离线回归 | `cd apps/scholarflow-api` + `pytest tests/ -q -m "not live_llm"` | 排除真实 DeepSeek |
| Live LLM | `SCHOLARFLOW_LIVE_LLM=1` + `pytest tests/test_llm_live.py tests/test_chat_agent_live.py tests/test_chat_sse_live.py tests/test_workflow_bridge_live.py -m live_llm` | 真实模型自主工具 |
| Live MCP（未跑） | `SCHOLARFLOW_LIVE_MCP=1 pytest …::test_mcp_live_arxiv_and_github` | 外部 arXiv/GitHub；见 §4 |
| API 集成 verify | `python scripts/verify_scholarflow_chat_ui.py` / `verify_scholarflow_sse.py` / `verify_scholarflow_workflow_bridge.py` | 对运行中 `:8100` |
| RAG 50 题 | `python evaluation/run_rag_qa_eval.py --profile baseline --out-dir evaluation/reports/rag_qa/phase8_6_2026-10-18` | **未改** `questions.json` / golden |
| 浏览器 E2E | Vite `:5173` + 人工/自动化操作 | 真实 DeepSeek SSE |

启动/停止见 §9。

---

## 2. 各组通过 / 失败 / 跳过 / 未运行

### 2.1 Mock/离线（`not live_llm`）

| 项 | 数量 |
|----|------|
| passed | **81** |
| skipped | **1** |
| failed | **0** |
| deselected | **8**（全部为 `live_llm`，见下） |

**唯一 skipped（不算通过）：**

| 测试 | 原因 | 最终验收处置 |
|------|------|--------------|
| `tests/test_mcp_protocol.py::test_mcp_live_arxiv_and_github` | 需 `SCHOLARFLOW_LIVE_MCP=1` | **未运行**（外部网络 + 成本）；历史阶段已有 MCP 协议离线测与 live 论文检索旁证 |

### 2.2 先前 8 项 deselected = 全部 `@pytest.mark.live_llm`

| # | 测试 | 类别 | 本轮结果 |
|---|------|------|----------|
| 1 | `test_live_deepseek_ping` | Live LLM | **PASS** |
| 2 | `test_live_direct_answer_no_forced_tool` | Live LLM / 自主不调工具 | **PASS** |
| 3 | `test_live_search_papers_autonomous` | Live LLM / 自主论文工具 | **PASS** |
| 4 | `test_live_rag_or_workflow_choice` | Live LLM / RAG 或工作流 | **PASS** |
| 5 | `test_live_history_isolation` | Live LLM / 会话隔离 | **PASS** |
| 6 | `test_live_sse_token_increments` | Live SSE | **PASS** |
| 7 | `test_live_sse_tool_then_tokens` | Live SSE + 工具后再 token | **PASS** |
| 8 | `test_live_agent_delegates_to_research_workflow` | Live + fixture 工作流 | **PASS** |

**合计 Live LLM：8 passed / 0 failed / 0 skipped（本轮已在最终验收中运行）。**

不得把未选中项算作通过；本轮已显式补跑。

### 2.3 API 集成 verify

| 脚本 | 结果 | 备注 |
|------|------|------|
| `verify_scholarflow_chat_ui.py` | PASS | SSE token + tool→`sf-545e5fc651cd` artifacts 200 |
| `verify_scholarflow_sse.py` | PASS | 直答 STREAM OK；`search_papers` 真 arXiv |
| `verify_scholarflow_workflow_bridge.py` | PASS | **real LLM + fixture** → `sf-d75c2761385d` / 9 产物 |

### 2.4 浏览器 E2E（`:5173`）

| 步骤 | 结果 |
|------|------|
| 新建会话 | PASS |
| 普通问题 + 真实 SSE（可见「停止生成」） | PASS |
| 论文问题 → UI 展示 `search_papers` succeeded + arXiv 链接 | PASS |
| 综合科研 `data_mode=fixture` → `task_id=sf-c29bebae1860`、succeeded、9 产物下载链 | PASS |
| 产物下载 `GET …/artifacts/research_report.md` → **200** | PASS |
| 刷新恢复当前会话（6 条历史） | PASS |
| 切换至另一会话（仅 2 条，历史隔离） | PASS |
| 科研工作台 Tab 仍可用 | PASS |

**模式声明：** 浏览器综合任务 = **真实 DeepSeek + fixture 科研图**，产物标注 fixture，**不可**称为全链路真实外部 MCP 编排。

### 2.5 RAG 评测

见 §4。新结果目录：`evaluation/reports/rag_qa/phase8_6_2026-10-18/`（未覆盖 golden / 历史 summary）。

---

## 3. 真实 Live 验证证据（脱敏）

### 3.1 Live pytest（8/8）

```
test_live_deepseek_ping PASSED
test_live_direct_answer_no_forced_tool PASSED
test_live_search_papers_autonomous PASSED
test_live_rag_or_workflow_choice PASSED
test_live_history_isolation PASSED
test_live_sse_token_increments PASSED
test_live_sse_tool_then_tokens PASSED
test_live_agent_delegates_to_research_workflow PASSED
======================== 8 passed in 39.22s ========================
```

自主工具 vs 固定调用：上述 live agent 测试断言 **模型返回的 tool_calls**；mock 套件另测脚本化工具环，二者分列。

### 3.2 浏览器关键 ID

| 项 | 值 |
|----|-----|
| workflow task_id | `sf-c29bebae1860` |
| status / data_mode | `succeeded` / `fixture` |
| artifact_count | 9（清单） |
| 论文工具证据 | `paper-1811.08772v1` → `https://arxiv.org/abs/1811.08772v1` |

### 3.3 设计稿「12 项」映射

| # | 设计项 | 证据类型 | 状态 |
|---|--------|----------|------|
| 1 | 多轮 | 浏览器 3 turn；mock/API | 覆盖 |
| 2 | 上下文追问 | live isolation；mock history | 覆盖 |
| 3 | 自主论文 | live `search_papers` + 浏览器 | 覆盖 |
| 4 | 自主 GitHub | 无独立 live「只调 GitHub 工具」用例；fixture 工作流含仓库节点；MCP 离线协议测有 | **部分覆盖** |
| 5 | 多工具连续 | mock `test_multi_tool_events` | 覆盖（mock） |
| 6 | 工具后再推理 | live SSE tool→token；浏览器 | 覆盖 |
| 7 | 委托工作流 | live workflow bridge + 浏览器 fixture | 覆盖 |
| 8 | MCP 失败 | `test_live_mode_guard`（失败不伪装成功） | 覆盖（mock/guard） |
| 9 | 拒答 | RAG q43–q47 refuse_accuracy=1.0 | 覆盖 |
| 10 | 会话持久化隔离 | chat_api + 浏览器切换 | 覆盖 |
| 11 | SSE | live + 浏览器 | 覆盖 |
| 12 | max-iter 停止 | mock `test_max_iterations` | 覆盖（mock） |

---

## 4. RAG 评测指标、定义与局限

**数据集：** 冻结 `evaluation/rag_qa/v1/questions.json`（50 题）— **本轮未修改**。  
**本轮 profile：** `baseline`（hybrid-score，MCP off，fixture 语料）。  
**输出：** `evaluation/reports/rag_qa/phase8_6_2026-10-18/baseline_latest_summary.json`

| 指标 | 本轮测得 | 定义 / 分母 | 局限 |
|------|----------|-------------|------|
| refuse_accuracy | **1.0**（5/5） | should_refuse 题是否正确拒答 | 仅 q43–q47 |
| faithfulness_mean | **0.58** | `reference_points` 子串命中率，对 50 题取均值 | **字符串命中 ≠ 语义忠实度**；空 points 记 1.0 会抬高 |
| top5_hit_rate | **0.6757**（25/37） | gold_evidence_ids 非空题中 Top-5 是否命中任一 gold | 分母 37；拒答收紧后较早期 hybrid 报告更低属已知权衡 |
| citation_accuracy_mean | **0.9846**（denom 26） | 引用标记结构校验均值 | 非强语义蕴含 |

**明确不宣称：**

- 无可核验历史 **0.62** 基线 → 禁止写「0.62→0.84」。
- MCP 调用量下降 **77% 未达标**（收尾实测全量约 56%、同主题约 40%；见 `docs/scholarflow-final-polish.md`）。本轮 baseline **未开 MCP**（`mcp_calls_total=0`），不作降幅宣称。
- 未在本轮重跑 `full_rag` Cross-Encoder（8GB 内存友好优先；历史 full_rag 结果仍保留在既有报告中，未覆盖）。

---

## 5. 功能完成状态（A–E 摘要）

### A. 对话与会话 — 达标（已知限制见 §6）

直接回答、多轮、刷新恢复、会话隔离、SSE token、停止生成 UI、重复提交禁用（发送中 disabled）均已验证。

### B. Agent 工具 — 达标（GitHub 自主项部分）

普通问题可不调工具；论文可自主 `search_papers`；RAG/工作流可自主选择；工具回灌后再答；失败/参数校验/max-iter 有 mock 覆盖。

### C. 科研工作流 — 达标（fixture 路径）

提交→TaskStore→终态→产物清单与下载→回灌聊天；fixture/live 标注准确。全链路 live MCP 编排 **未**作为本轮浏览器达标条件。

### D. RAG 与证据 — 如实报告

50 题冻结集保留；baseline 重跑；指标与局限见 §4。

### E. 安全与可靠性 — 有披露

Key 不进前端/health（仅 flags）；会话≠任务目录分离；工具 Schema 校验；Sandbox 非生产级隔离已披露。

---

## 6. 已知安全风险与工程限制

1. **非幂等 turn：** 重复 `POST …/turns` 或 `/turns/stream` 会再次调模型并追加消息（无 client `request_id`）。
2. **单进程会话锁：** ConversationStore 进程内锁；多 API 进程写同一会话无 OS 文件锁（设计为单机单进程）。
3. **Sandbox：** Docker 模式有网络/内存限制；Windows `process_jail` **无**硬内存 cap / OS 网络隔离；不可称生产级绝对隔离。
4. **Live MCP 全量：** `test_mcp_live_arxiv_and_github` 本轮未跑；论文检索 live 已有旁证，GitHub live 工具独立回归不足。
5. **刷新瞬间任务卡片：** 可能短暂显示「任务仍在运行」直至状态拉取完成（随后纠正为 succeeded + 下载链）。
6. **8GB：** 不默认起 ScholarFlow 整栈；Chat 走 Vite+FastAPI。
7. **verify 脚本会刷新 8.3/8.4 文档头部证据：** 历史 PASS 结论保留；冻结题集与 Golden **未**被覆盖。

---

## 7. 当前可对外宣称的能力

- 本机 Vite + FastAPI 的 ScholarFlow：**Chat 默认** + **科研工作台保留**。
- 真实 DeepSeek 多轮对话、SSE 流式、停止生成。
- 真实 LLM **自主**工具调用（论文检索、RAG/工作流选择），工具结果回灌后再回答。
- Agent 委托科研 StateGraph，**fixture** 下产出可下载九件套，且 **明确标注 fixture**。
- 会话 JSON/JSONL 持久化与会话间隔离。
- Hybrid RAG（检索拼装）+ 拒答收紧后 refuse_accuracy=1.0（本轮 baseline）。
- MCP 协议工具与 live 模式下失败不静默伪装成功（guard 测）。

---

## 8. 仍不可宣称的能力

- 「忠实度 0.62→0.84」或简历目标 faithfulness=0.84 已达标。
- 「MCP 调用量下降 77%」已达标。
- 全链路 **live MCP** 综合科研浏览器 E2E（本轮综合任务为 fixture）。
- 每个 Sub-Agent 均为大模型对辩式多智能体（图内多为确定性节点 + 数据）。
- 生产级沙箱 / 多进程安全文件锁 / turn 幂等。
- 将字符串 faithfulness 说成严格语义忠实度。
- ScholarFlow 整栈已作为 ScholarFlow 演示依赖（刻意不启动）。

---

## 9. 最终启动与停止命令

```powershell
# 启动 API（:8100）— 从仓库根 .env 注入允许的 Key，不打印密钥
powershell -File scripts/start_scholarflow_api.ps1

# 另开终端：启动前端（:5173）
powershell -File scripts/start_scholarflow_web.ps1

# 浏览器打开
# http://127.0.0.1:5173/

# 停止本机 8100/5173（不碰 Docker / 其他项目）
powershell -File scripts/stop_scholarflow.ps1
```

健康检查：`GET http://127.0.0.1:8100/health`（应见 `llm_configured` 等 flags，**无** API-Key 明文）。

---

## 10. 结论

阶段 **8.6 PASS（有条件）**：Mock 81 + Live LLM 8 + API verify + 浏览器 E2E + RAG baseline 重跑均已完成并分列报告；未达标指标与未跑 Live MCP 已如实披露。

**暂停。** 不自动进入新阶段；等待最终确认。
