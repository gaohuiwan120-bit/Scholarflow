# Experiment Plan: RAG Architecture Research

## Task ID
`rag-test-001`

## Date
2026-07-21

## Overview
This experiment plan outlines benchmarks and ablation studies for evaluating RAG (Retrieval-Augmented Generation) system architectures, informed by evidence from paper and repository analysis.

---

## Hypotheses

**H1:** Hybrid retrieval (dense + sparse) significantly outperforms single-method retrieval (dense-only or sparse-only) for knowledge-intensive QA tasks, particularly as document corpus size scales up.

**H2:** Modular RAG architectures with flexible component composition achieve higher task adaptability than rigid Naive RAG pipelines.

**H3:** LangChain-based RAG implementations provide a production-ready baseline but introduce measurable overhead compared to custom-optimized pipelines.

---

## Baselines

### Paper-Informed Baselines

| Baseline | Description | Source |
|----------|-------------|--------|
| Naive RAG | Basic retrieve-then-generate pipeline with single retriever | Gao et al. 2023 (2312.10997v5) |
| Advanced RAG | Pre-retrieval and post-retrieval enhancements (query rewriting, re-ranking) | Gao et al. 2023 (2312.10997v5) |
| Modular RAG | Flexible module composition for task-specific optimization | Gao et al. 2023 (2312.10997v5) |
| Blended Retrieval | Hybrid dense + sparse retrieval with query strategies | Sawarkar et al. 2024 (2404.07220v2) |

### Repository-Informed Baseline

| Baseline | Description | Source |
|----------|-------------|--------|
| LangChain RAG | Standard LangChain RAG chain with vector store retriever | langchain-ai/langchain |

---

## Evaluation Metrics

| Metric | Description | Target Task |
|--------|-------------|-------------|
| Retrieval Recall@K | Proportion of relevant documents in top-K retrieved | Retrieval quality |
| Precision@K | Proportion of retrieved documents that are relevant | Retrieval quality |
| F1 Score | Harmonic mean of precision and recall | Generation accuracy |
| Exact Match (EM) | Exact string match between predicted and ground truth | QA accuracy |
| Faithfulness | Proportion of claims supported by retrieved context | Hallucination mitigation |
| End-to-End Latency | Total time from query to generation response | Production readiness |

---

## Datasets

| Dataset | Domain | Size | Purpose |
|---------|--------|------|---------|
| Natural Questions (NQ) | Web QA | ~300K | Retrieval benchmark |
| TREC-COVID | Biomedical | ~171K | Domain-specific retrieval |
| SQuAD | Reading comprehension | ~100K | Generative QA evaluation |

---

## Ablation Studies

### A1: Retriever Component Ablation

Evaluate the impact of different retrieval strategies:
- **A1a**: Dense vector retrieval only (e.g., OpenAI embeddings + FAISS)
- **A1b**: Sparse keyword retrieval only (e.g., BM25)
- **A1c**: Hybrid dense + sparse (Blended RAG approach)
- **A1d**: Hybrid with query rewriting (Advanced RAG)

**Expected Result:** A1c > A1d > A1a > A1b in retrieval recall; A1d may improve precision.

### A2: Chunking Strategy Ablation

Compare chunk size and overlap strategies:
- **A2a**: Fixed chunk size (256 tokens)
- **A2b**: Fixed chunk size (512 tokens)
- **A2c**: Fixed chunk size (1024 tokens)
- **A2d**: Semantic chunking

**Expected Result:** A2b provides the best balance of retrieval relevance and context sufficiency for most QA tasks.

### A3: Re-ranking Ablation

Evaluate post-retrieval re-ranking:
- **A3a**: No re-ranking (direct top-K selection)
- **A3b**: Cross-encoder re-ranking (e.g., Cohere rerank)
- **A3c**: LLM-based re-ranking

**Expected Result:** A3b improves precision by 5-15% over A3a at the cost of 2-3x latency.

---

## Experiment Pipelines

## Proposed Pipeline

### Pipeline 1: Naive RAG Baseline (Reproduce from Gao et al. 2023)

```
Query → Embedding → Vector Search (top-K) → Context Assembly → LLM Generation → Answer
```

**Components:**
- Embedding model: text-embedding-ada-002 or all-MiniLM-L6-v2
- Vector store: Chroma or FAISS
- LLM: GPT-3.5-turbo or Llama 3
- K: 5

### Pipeline 2: Blended RAG (Reproduce from Sawarkar et al. 2024)

```
Query → Dense Embedding + Sparse Encoding → Hybrid Search (top-K) → Context Assembly → LLM Generation → Answer
```

**Components:**
- Dense: Dense Vector Index
- Sparse: Sparse Encoder Index
- Fusion: Weighted score combination (alpha=0.5)
- LLM: GPT-3.5-turbo

### Pipeline 3: LangChain RAG Implementation

```
Document Loading → Text Splitting → Embedding → Vector Store → Retrieval → LLM Chain → Output
```

**Components:**
- DocumentLoader: LangChain loaders
- TextSplitter: RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200)
- VectorStore: Chroma
- Retriever: VectorStoreRetriever
- Chain: RetrievalQA

---

## Reproducibility

- All experiments should use fixed random seeds
- Dataset splits should be standardized (70/15/15 for train/val/test)
- Each experiment should be run with 3 different seeds and mean/variance reported
- Source code and configuration should be version-controlled
- Hardware specifications (GPU type, VRAM, CPU) must be documented

---

## Timeline

| Phase | Activity | Estimated Duration |
|-------|----------|-------------------|
| Setup | Environment configuration, dataset preparation | 1 day |
| A1 | Retriever ablation studies | 2 days |
| A2 | Chunking strategy ablation | 1 day |
| A3 | Re-ranking ablation | 1 day |
| Pipeline 1 | Naive RAG baseline | 1 day |
| Pipeline 2 | Blended RAG implementation | 2 days |
| Pipeline 3 | LangChain RAG implementation | 1 day |
| Analysis | Results compilation, statistical analysis, report writing | 2 days |

---

## References

1. Gao et al. (2023). "Retrieval-Augmented Generation for Large Language Models: A Survey." arXiv:2312.10997v5.
2. Wampler et al. (2025). "Engineering the RAG Stack." arXiv:2601.05264v1.
3. Sawarkar et al. (2024). "Blended RAG: Improving RAG Accuracy with Semantic Search and Hybrid Query-Based Retrievers." arXiv:2404.07220v2.
4. LangChain GitHub Repository. https://github.com/langchain-ai/langchain

## Risks
- Retrieval quality remains the primary bottleneck as corpora scale.
- Abstraction overhead in framework-based pipelines may hide latency costs.
- Abstract-only paper evidence requires full-text verification before claiming SOTA numbers.
