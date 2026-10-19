# ScholarFlow RAG QA v1（固定 50 题）

- **版本**：`rag_qa_v1`（见 `VERSION`）
- **语料**：`docs/scholar-flow/samples/rag-test-001`（冻结；评测后不得为刷分改题）
- **文件**：`questions.json`

## 题型分布

| eval_type | 约数量 | 说明 |
|-----------|--------|------|
| direct | 20 | 单证据可答 |
| cross_doc | 8 | 跨文档 |
| discriminate / source_trace | 6 | 相似论文/仓库区分 |
| needs_mcp | 8 | 语料外，应触发补检 |
| should_refuse | 5 | 应拒答/不确定 |
| citation | 3 | 引用与 URL 校验 |

## 标注字段

- `gold_evidence_ids`：相关证据（可为空）
- `expected_sources`：期望 URL
- `reference_points`：忠实度检查用要点（小写子串匹配）
- `needs_mcp` / `should_refuse`

## 跑评测

```powershell
cd E:\AgentProject\scholarflow_project
# Baseline (hybrid-score)
$env:SCHOLAR_RAG_RERANK_MODEL="hybrid-score"
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile baseline

# Full RAG (real ONNX Cross-Encoder；模型已在 evaluation/models/ce-minilm)
$env:SCHOLAR_RAG_RERANK_MODEL="cross-encoder"
$env:SCHOLAR_RAG_CE_MODEL_DIR="evaluation\models\ce-minilm"
backend\.venv\Scripts\python.exe evaluation\run_rag_qa_eval.py --profile full_rag
```

指标由脚本根据原始结果计算，**禁止**把简历目标值写入结果 JSON。
