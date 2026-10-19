# RAG 主流架构与开源实现研究报告

## Objective
Survey mainstream RAG architectures (Naive / Advanced / Modular) and open-source implementations with traceable paper and repository evidence.

## Key Paper Findings
- Naive to Advanced to Modular RAG evolution is the dominant taxonomy.
- Hybrid dense+sparse retrieval improves accuracy on NQ / SQUAD-style tasks.
- Trust and evaluation frameworks are required for production RAG stacks.

## Experiment Plan Summary
Retriever ablation, chunking strategy, and re-ranking ablations are proposed; see experiment_plan.md for hypotheses, pipelines, and risks.

## 执行摘要

本报告系统研究检索增强生成（Retrieval-Augmented Generation, RAG）的主流架构范式及其开源实现。通过分析3篇 arXiv 论文和1个主要开源框架，全面考察了 RAG 架构从 Naive → Advanced → Modular 的演化路径、混合检索策略的改进效果，以及 LangChain 等工业级实现的技术栈。

---

## 1. 研究背景与动机

大型语言模型（LLM）在知识密集型任务中面临三大核心挑战：
- **知识截止**：模型训练数据有时间截断，无法获取最新信息
- **幻觉（Hallucination）**：模型可能生成看似合理但事实错误的内容
- **缺乏可追溯性**：模型推理过程不透明，无法验证知识来源

RAG 通过将外部知识库的检索结果融入生成过程，有效缓解了上述问题 [citation:Retrieval-Augmented Generation Survey](https://arxiv.org/abs/2312.10997v5)。

---

## 2. 主流架构范式

### 2.1 Naive RAG（朴素 RAG）

最基础的 RAG 实现，遵循 **检索→生成** 的流水线：

```
用户查询 → 编码 → 向量检索（top-K）→ 上下文拼接 → LLM生成 → 回答
```

**优点**：实现简单，适合入门
**局限**：检索质量瓶颈、无查询优化、无结果重排

### 2.2 Advanced RAG（高级 RAG）

在 Naive RAG 基础上增加预处理和后处理优化 [citation:Retrieval-Augmented Generation Survey](https://arxiv.org/abs/2312.10997v5)：

- **预检索增强**：查询重写（Query Rewriting）、查询扩展（Query Expansion）、假设文档嵌入（HyDE）
- **后检索增强**：重排序（Re-ranking）、上下文压缩（Context Compression）、过滤（Filtering）

### 2.3 Modular RAG（模块化 RAG）

最灵活的架构范式，支持可插拔模块组合：

- 检索模块：稀疏检索、稠密检索、混合检索
- 生成模块：不同 LLM 后端的替换
- 融合模块：多源信息融合策略
- 记忆模块：长期/短期记忆管理

**关键优势**：任务特定优化、高度可定制、渐进式升级路径

---

## 3. 检索策略分析

### 3.1 单一检索方法对比

| 方法 | 优点 | 缺点 |
|------|------|------|
| 稠密向量检索（Dense） | 语义理解强，支持跨语言 | 需要大量训练数据，冷启动困难 |
| 稀疏关键词检索（Sparse） | 精确匹配，可解释性强 | 语义理解弱，同义词处理差 |

### 3.2 混合检索（Blended RAG）

Blended RAG 方法融合稠密向量索引和稀疏编码索引，配合混合查询策略，在 NQ、TREC-COVID、SQuAD 等多个基准上取得了显著优于单一方法的效果 [citation:Blended RAG](https://arxiv.org/abs/2404.07220v2)。

**核心发现**：
- 混合检索在检索准确性上全面超越纯稠密或纯稀疏方法
- 混合查询策略比纯语义搜索或纯关键词搜索效果更好
- Blended RAG 在生成式 QA 数据集上甚至超越了微调（fine-tuning）性能

---

## 4. RAG 工程化实践

### 4.1 RAG 技术栈统一分类

Wampler 等人（2025）提出了覆盖2018-2025年的系统性文献综述，将 RAG 技术整合到统一分类法中，并强调了信任框架（Trust Frameworks）在生产部署中的关键作用 [citation:Engineering the RAG Stack](https://arxiv.org/abs/2601.05264v1)。

### 4.2 LangChain 开源实现

LangChain 是目前最主流的 RAG 实现框架，提供模块化组件和广泛的第三方集成 [citation:LangChain GitHub](https://github.com/langchain-ai/langchain)：

| 组件 | 功能 |
|------|------|
| **langchain-core** | 基础抽象层和接口定义 |
| **langchain-community** | 超过700个第三方集成（向量数据库、嵌入模型、LLM） |
| **langchain** | 链式组合、智能体、检索策略 |
| **langgraph** | 有向无环图工作流编排 |

**RAG 标准实现流程（LangChain）**：

```
DocumentLoader → TextSplitter → Embedding → VectorStore → Retriever → RetrievalQA → 回答
```

LangChain 兼容多种向量数据库（Chroma、Pinecone、Weaviate、FAISS）和 LLM 提供商（OpenAI、Anthropic、Llama 等），为生产级 RAG 部署提供了完整的工具链。

---

## 5. 实验计划概览

基于研究发现，设计了三组消融实验：

| 实验 | 假设 | 预期结果 |
|------|------|----------|
| 检索器消融 | 混合检索 > 单一方法 | 混合 > 稠密 > 稀疏 |
| 分块策略 | 中等块大小（512 tokens）最优 | 512 tokens 适合大多数 QA 场景 |
| 重排评估 | 交叉编码器重排提精度 | 精度提升 5-15%，延迟增 2-3x |

---

## 6. 结论

RAG 架构已从简单的 Naive 模式演进到高度灵活的 Modular 模式，混合检索策略在多项基准上展示了显著优势。LangChain 作为主要开源框架，提供了生产级 RAG 实现的完整基础设施。

### 建议
1. **新项目**：从 Modular RAG 架构起步，逐步优化检索组件
2. **性能优化**：优先采用 Blended RAG 混合检索策略
3. **生产部署**：结合信任框架进行系统评估，推荐使用 LangChain 生态

---

## 参考文献

1. [Gao et al. (2023). "Retrieval-Augmented Generation for Large Language Models: A Survey." arXiv:2312.10997v5.](https://arxiv.org/abs/2312.10997v5)
2. [Wampler et al. (2025). "Engineering the RAG Stack." arXiv:2601.05264v1.](https://arxiv.org/abs/2601.05264v1)
3. [Sawarkar et al. (2024). "Blended RAG: Improving RAG Accuracy with Semantic Search and Hybrid Query-Based Retrievers." arXiv:2404.07220v2.](https://arxiv.org/abs/2404.07220v2)
4. [LangChain GitHub Repository.](https://github.com/langchain-ai/langchain)

---

*生成日期：2026-07-21 | 任务ID：rag-test-001*
