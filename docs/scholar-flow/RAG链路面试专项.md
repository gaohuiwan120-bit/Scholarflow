# ScholarFlow RAG 链路面试专项

> 只描述仓库真实实现。目标：回答「你的 RAG 具体怎么实现？」

---

## 30 秒总述（先背这个）

我们的 RAG 不是通用 PDF 知识库，而是**科研产物库 RAG**：

1. Agent 先通过 MCP 拉 arXiv/GitHub，落盘 9 类结构化产物；  
2. `index_research_artifacts` 把产物切成 `EvidenceChunk`，用 **bge-small-en-v1.5** 向量化，BM25 建稀疏索引，JSON（可选 Chroma）持久化；  
3. 追问时 `rag_query` → Dense+BM25 → **RRF** → **hybrid-score 重排** → 返回带 `evidence_id/source_url` 的答案；  
4. **当前 `rag_answer` 不调用 LLM 生成**，而是检索后确定性拼接可引用 bullet；证据不足则 `need_mcp_fallback=true`，Agent 再去调外检工具。

---

## 完整调用链（索引 + 检索两条）

### A. 索引链路（文档进入系统 → 入库）

```
Agent / Demo 调用
  → scholar_mcp/server.py :: index_research_artifacts
      → scholar/rag/pipeline.py :: index_artifacts_dir
          → scholar/rag/chunking.py :: load_chunks_from_artifacts_dir
          → scholar/rag/store.py :: upsert_chunks
              → store.py :: embed_texts
              → 写 corpus.json / vectors.json / bm25_corpus.json
              → （可选）Chroma collection.upsert
```

### B. 检索链路（Query → 返回 Agent）

```
Agent 调用
  → scholar_mcp/server.py :: rag_query
      → scholar/rag/pipeline.py :: rag_answer
          → scholar/rag/retrieve.py :: hybrid_retrieve
              → store.py :: embed_texts          # query 向量化
              → retrieve.py :: _BM25.get_scores  # 稀疏召回
              → retrieve.py :: _rrf_fuse         # 融合
              → store.py :: rerank / hybrid_score_rerank
          → 拼接 answer 字符串 + evidence 列表（JSON）
  → MCP 把 JSON 字符串返回给 Lead Agent（tool result）
```

---

## 逐步函数卡片

### 1）文档进入系统的位置

**入口 1（Agent/MCP）**  
文件：`extensions/scholar_mcp/scholar_mcp/server.py`  
函数：`index_research_artifacts(artifacts_dir, task_id=None)`

- 输入：产物目录路径（如 `.../outputs/rag-test-001`）、可选 task_id  
- 输出：JSON 字符串（upserted/total/backend/embed_model…）  
- 作用：MCP 工具入口，把「已调研产物」送进 RAG 索引  
- 面试表达：文档不是爬网页进来的，是 Agent 先调研落盘后，我再索引进证据库。

**入口 2（本地 Demo）**  
文件：`evaluation/run_rag_demo.py`  
函数：`main()` → `index_artifacts_dir(...)`

- 输入：`--artifacts` 默认 `docs/scholar-flow/samples/rag-test-001`  
- 输出：控制台打印索引信息 + 问答结果  
- 作用：面试可一键演示，不依赖 UI  

**真正业务管线**  
文件：`scholarflow/scholar/rag/pipeline.py`  
函数：`index_artifacts_dir(artifacts_dir, config=None, task_id=None)`

- 输入：目录 Path、可选 `RagConfig`  
- 输出：`dict`（统计信息）  
- 作用：切块 → 入库的编排函数  

---

### 2）文档解析代码

**没有独立 PDF Parser。** 解析就是读产物文本/JSON。

文件：`scholarflow/scholar/rag/chunking.py`  
函数：`load_chunks_from_artifacts_dir`

- 输入：`artifacts_dir`, `task_id`  
- 输出：`list[EvidenceChunk]`  
- 作用：  
  - `paper_evidence.json` / `repository_evidence.json`：`json.loads` 后按 `items` 取字段拼接文本  
  - `sources.json`：补未覆盖的来源  
  - `research_report.md` / `experiment_plan.md` / `research_plan.json` / `evidence_review.json`：`read_text`，JSON 再 dump 成字符串  
- 面试表达：我们 ingest 的是结构化科研产物，不是通用 Unstructured PDF 流水线；上传文件另有 MCP `extract_uploaded_paper`（读文本前 4000 字），不做 OCR。

补充（非 RAG 主链，但是「文档进系统」上游）：

- arXiv：`clients/arxiv.py` → Agent 写 `paper_evidence.json`  
- GitHub：`clients/github.py` → Agent 写 `repository_evidence.json`  

---

### 3）Chunk 切分代码

文件：`scholarflow/scholar/rag/chunking.py`  
关键符号：`EvidenceChunk`、`_clip`、`load_chunks_from_artifacts_dir`

| 数据类型 | 切分策略 |
|----------|----------|
| paper / repo | 一条证据 ≈ 一个 chunk；字段拼接后 `_clip(..., 1800)` |
| report / experiment / plan / review | **固定窗口 ~1200 字符**滑动切分；单片再 clip 到 1500；过短（&lt;40）丢弃 |

`EvidenceChunk` 字段：`chunk_id, evidence_id, kind, title, text, source_url, verification_status, task_id, metadata`

- 输入：产物目录  
- 输出：chunk 列表  
- 作用：把异构产物变成统一可检索段落  
- 面试表达：证据级切分 + 长文长度窗口；**不是语义切分器**。

---

### 4）Embedding 调用代码

文件：`scholarflow/scholar/rag/store.py`  
函数：`embed_texts(texts, config)` / `_load_embedder(model_name, backend)`

- 输入：文本列表 + `RagConfig`  
- 输出：`list[list[float]]`  
- 作用：  
  - `backend=fastembed`：`TextEmbedding(model_name).embed(texts)`  
  - 默认模型：`BAAI/bge-small-en-v1.5`，维度 384（`config.py`）  
  - 降级 `lite`：`_hash_embed`（面试要说清是 fallback）  
- 文档侧：`upsert_chunks` 里 `embeds = embed_texts(docs, config)`  
- Query 侧：`hybrid_retrieve` 里 `q_emb = embed_texts([query], config)[0]`  
- 缓存：`_load_embedder` 用 `@lru_cache`；向量落盘 `vectors.json`  

面试表达：Query 和 Document 共用同一套 `embed_texts`，保证同空间；生产默认 ONNX bge-small。

---

### 5）向量库存储代码

文件：`scholarflow/scholar/rag/store.py`  
函数：`upsert_chunks(chunks, config)`

- 输入：`list[EvidenceChunk]`, `RagConfig`  
- 输出：统计 dict（upserted/total/vector_store…）  
- 作用：  
  1. 必写 `corpus.json`（文本+元数据）  
  2. 必写 `vectors.json`（chunk_id → 向量）  
  3. 必写 `bm25_corpus.json`（稀疏侧语料）  
  4. 有 chromadb 则 `PersistentClient` → `get_or_create_collection("scholarflow_evidence")` → `collection.upsert`（cosine）  
- 默认目录：`evaluation/rag_index/`（`RagConfig.persist_dir`）

面试表达：检索主路径读 JSON 向量做余弦；Chroma 是双写增强，不是唯一依赖。

---

### 6）Query 检索代码

文件：`scholarflow/scholar/rag/retrieve.py`  
函数：`hybrid_retrieve(query, config, top_k=None, verified_only=False)`

- 输入：用户问题、配置、top_k（默认 5）、是否只取已验证证据  
- 输出：`list[RetrievedEvidence]`（含 score）  
- 作用（按顺序）：  
  1. `load_corpus` / `load_vectors`  
  2. Dense：query 向量 vs 全库余弦，取 top `recall_dense`(20)  
  3. Sparse：`_BM25.get_scores`，取 top `recall_sparse`(20)；分词 jieba/bigram  
  4. `_rrf_fuse` 融合两路 ID  
  5. 可选过滤 `verification_status in {verified, partially_verified}`  
  6. `rerank` = `hybrid_score_rerank`（0.55 词面重叠 + 0.45 dense）  
  7. 业务 bonus：paper/repo、有 source_url、关键词命中  
  8. 截断 top_k  

面试表达：标准 Hybrid Retrieval：向量召回 + BM25 + RRF + 二阶段打分重排；重排不是 Cross-Encoder。

---

### 7）检索结果如何返回 Agent

文件：`extensions/scholar_mcp/scholar_mcp/server.py`  
函数：`rag_query(question, top_k=5, verified_only=True)`

- 输入：问题字符串等  
- 输出：**JSON 字符串**（MCP tool result）  
- 内层：`rag_answer(...)` 返回 dict，再 `json.dumps`  

Agent 侧（ScholarFlow Lead）：

1. LLM 发起 tool call：`scholar_mcp_rag_query`  
2. 运行时把 tool 返回 JSON 塞回对话消息  
3. Lead 再决定：直接转述给用户，或因 `need_mcp_fallback=true` 去调 arXiv/GitHub  

面试表达：RAG 对 Agent 暴露为 MCP Tool；契约字段含 `answer/evidence/need_mcp_fallback/retrieval`。

---

### 8）Context 如何拼接 Prompt

**真实情况：没有 ChatPromptTemplate 把 context 塞进 system/user 再调 LLM。**

文件：`scholarflow/scholar/rag/pipeline.py`  
函数：`rag_answer`

拼接逻辑（确定性模板）：

```text
基于 ScholarFlow 科研证据库检索（backend=..., embed=...）：

- [paper] <snippet280字> 〔evidence_id (source_url)〕
- [repository] ...
...
以上结论均绑定 evidence_id/source_url；若证据不足请再走 MCP 补检。
```

- 输入：`RetrievedEvidence` 列表  
- 输出：`answer` 字符串 + `evidence` 结构化列表  
- 作用：把检索结果变成可追溯回答文本  

若 Lead Agent 再用自然语言润色，那是 **ScholarFlow Agent 二次处理 tool 结果**，不在 `rag/` 模块内部。

面试表达（关键防穿帮）：

> 我们模块内是 retrieve-and-cite 的确定性组装；经典「Context→Prompt→LLM」若发生，是外层 Agent 对 tool JSON 的再生成，不是 `pipeline.rag_answer` 调模型。

---

### 9）LLM 如何基于 Context 生成答案

| 层级 | 是否调 LLM | 说明 |
|------|------------|------|
| `rag_answer` | **否** | docstring 写明 `no LLM required`；纯检索+拼接 |
| Lead Agent | **可能** | 收到 tool JSON 后可能总结给用户（框架行为） |
| 证据不足 | 不生成幻觉答案 | 返回固定提示 + `need_mcp_fallback=true` |

面试表达：

> RAG 核心保证「每条结论可挂证据」；生成式润色留给 Agent。这样评测引用准确率更可控。

---

## 一张图记住端到端

```
[调研产物目录]
        │
        ▼
index_research_artifacts
        │
        ▼
load_chunks_from_artifacts_dir ──► EvidenceChunk[]
        │
        ▼
upsert_chunks ── embed_texts(bge-small) ──► vectors.json
             ── corpus/bm25 json
             ── Chroma(optional)
        │
        ▼
用户追问 ──► rag_query ──► rag_answer
                              │
                              ▼
                         hybrid_retrieve
                         (Dense + BM25 + RRF + hybrid-score)
                              │
                              ▼
                         拼接带引用 answer（无 LLM）
                              │
                              ▼
                         JSON 返回 Lead Agent
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
              直接回复用户        need_mcp_fallback
                                  → 再调 arXiv/GitHub
```

---

## 面试官追问速查

| 追问 | 真实答案 |
|------|----------|
| Embedding 模型？ | `BAAI/bge-small-en-v1.5`，384 维，fastembed |
| 向量库？ | 主：JSON；可选 Chroma cosine |
| Hybrid？ | 有，Dense+BM25+RRF |
| Rerank？ | hybrid-score，不是 Cross-Encoder |
| Top-K？ | 默认 5；召回各 20 |
| 和 Agent 怎么接？ | MCP `rag_query` / `index_research_artifacts` |
| Context 拼 Prompt？ | 模块内模板拼接；不在此调 LLM |
| 数据从哪来？ | Agent 产出的 9 类文件，不是裸爬虫 |

---

## 现场演示

```powershell
cd E:\AgentProject\scholarflow_project\backend
uv run python ../evaluation/run_rag_demo.py
```

打开代码顺序建议：`pipeline.py` → `chunking.py` → `store.py` → `retrieve.py` → `server.py`（两个 MCP tool）。
