# ScholarFlow Hybrid RAG（面试可运行）

## 实际可运行技术栈（与代码一致）

| 组件 | 实现 |
|------|------|
| Embedding | `BAAI/bge-small-en-v1.5`（384-d，fastembed ONNX） |
| 稀疏召回 | BM25 + jieba |
| 融合 | RRF |
| 重排 | hybrid-score（dense cosine + 词面重叠） |
| 向量存储 | JSON 语料 + 可选 Chroma 双写 |
| 引用约束 | 强制 `evidence_id` / `source_url` |

> 说明：默认**不**宣称正在跑 `bge-m3`。若简历曾写 m3，面试口径改为「BGE 系列，本机 Demo 用 bge-small-en-v1.5 ONNX；架构可切换更大模型」。

## 安装（只需一次）

```powershell
cd E:\AgentProject\scholarflow_project\backend
uv pip install fastembed chromadb rank-bm25 jieba
```

## 一键演示

```powershell
cd E:\AgentProject\scholarflow_project\backend
uv run python ../evaluation/run_rag_demo.py
```

成功标志：末尾打印 `=== DEMO OK ===`，且 Top 证据含 `paper-2404.07220v2` 一类真实 `source_url`。

换问题：

```powershell
uv run python ../evaluation/run_rag_demo.py --question "LangChain RAG pipeline components"
```

## MCP

- `scholar_mcp_index_research_artifacts`
- `scholar_mcp_rag_query`

Docker 下需 recreate gateway 后生效。容器内也需能 import `scholarflow.scholar.rag`（harness 已挂载）。

## 代码

`backend/packages/harness/scholarflow/scholar/rag/`
