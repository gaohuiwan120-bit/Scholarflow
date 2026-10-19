# ScholarFlow Phase 4 — Cross-Encoder、MCP 补检与 50 题评测

## 核验结论（编码前）

| 项 | 事实 |
|----|------|
| Embedding | `BAAI/bge-small-en-v1.5` via fastembed（或 lite hashing） |
| BM25 + RRF | 已实现 |
| 重排 | **原为 hybrid-score（0.55 overlap + 0.45 dense）**，**不是** Cross-Encoder |
| `need_mcp_fallback` | 仅标志，**无**自动补检闭环 |
| 50 题 QA | **不存在**（仅有编排 tasks / E2E 10 题）→ 新建冻结集 `rag_qa_v1` |

## 已实现

### Cross-Encoder

- 模块：`scholarflow/scholar/rag/cross_encoder.py`
- 后端：ONNX `Xenova/ms-marco-MiniLM-L-6-v2`（量化 ~23MB，CPU）
- 配置：`SCHOLAR_RAG_RERANK_MODEL=cross-encoder` + `SCHOLAR_RAG_CE_MODEL_DIR`
- 缺失模型时 **显式报错**，不静默回退 hybrid-score
- 单测可用 `stub-cross-encoder`（结果不得宣称真实 CE）

### 检索诊断

`hybrid_retrieve(..., return_diagnostics=True)` 记录 dense/sparse/RRF/CE 候选数与耗时。

### MCP 自动补检

`retrieve_with_mcp_fallback` / `rag_answer(..., enable_mcp_fallback=True, data_mode=live, mcp_caller=...)`

- 证据不足（数量 / 主题 overlap）→ MCP `search_academic_papers`（可选仓库）
- 写入索引 → 再检索；最大轮次 `max_mcp_rounds`
- fixture 模式阻止 live 补检；失败不伪造成功

### 来源约束

`citation.py`：答案 bullet 绑定 evidence_id/URL；`verify_citations` 检查集合内 ID、URL 一致、片段支持。

### 50 题集

`evaluation/rag_qa/v1/`（`VERSION=rag_qa_v1`，冻结）

### 评测脚本

```powershell
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile baseline
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile no_mcp
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile cold_mcp
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile full_rag_mcp_mock
# live CE + live MCP（需网络）
$env:SCHOLARFLOW_LIVE_MCP="1"
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile full_rag
```

原始结果：`evaluation/reports/rag_qa/*_latest_*.json`（**未**写入简历目标值）

## 实测指标（2026-10-17，脚本计算）

| Profile | Faithfulness | Top-5 hit | Citation | MCP calls |
|---------|--------------|-----------|----------|-----------|
| baseline (hybrid-score) | **0.790** | **0.811** (37 题有 gold) | **0.992** | 0 |
| no_mcp (CE only) | 0.763 | **0.838** | 0.984 | 0 |
| full_rag (CE + live MCP) | **0.853** | **0.865** | **0.992** | 28 |
| cold_mcp (无语料 + mock MCP) | 0.417 | 0.0 | 1.0 | **30** |
| full_rag_mcp_mock (有语料 + mock) | 0.820 | 0.811 | 0.988 | **15** |

### 相对简历目标

| 目标 | 实测 | 是否达标 |
|------|------|----------|
| 忠实度 0.62→0.84 | baseline 0.79 → full_rag live **0.853** | **达标（full_rag live）** |
| Top-5 命中 82% | CE no_mcp **83.8%**；full_rag live **86.5%** | **达标** |
| 引用准确率 91% | **≥98%**（各 profile） | **达标** |
| 同主题 MCP ↓77% | cold→indexed same-topic：**60%**（20→8） | **未达标**（全量 50%：30→15） |

> 口径：同主题 = 有 `gold_evidence_ids` 的题目；MCP 次数为实际 `mcp_rounds.tools` 计数（含重试轮）。

### 未达标 / 风险

1. **MCP 调用下降 77%**：当前同主题仅 **60%**，需扩大历史语料覆盖或收紧误触发补检。
2. **拒答准确率**偏低（0.2–0.4）：补检后易对应拒答题生成“看似有据”的答案，需加强拒答策略。
3. **Faithfulness 自动协议**为要点子串匹配，非 LLM-as-judge；面试需说明协议与局限。
4. Sandbox **未做**。

## 测试命令与结果

```text
backend: pytest tests/test_scholar_rag.py tests/test_scholar_rag_phase4.py
  → 11 passed（含真实 ONNX CE + stub + MCP mock 闭环）

apps/scholarflow-api: pytest tests -q
  → 24 passed, 1 skipped
```

## 启动提示

```powershell
# API：可选 rerank_model / enable_mcp_fallback / data_mode=live
$env:SCHOLAR_RAG_RERANK_MODEL="cross-encoder"
$env:SCHOLAR_RAG_CE_MODEL_DIR="E:\AgentProject\scholarflow_project\evaluation\models\ce-minilm"
```
