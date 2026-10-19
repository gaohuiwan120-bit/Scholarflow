# ScholarFlow 科研工作流主题错配：根因审计与最小修复

**日期：** 2026-10-19  
**原任务（只读保留）：** `sf-5787ead265f0`  
**复验任务：** `sf-rel-e2e-1792380524`（见 `apps/scholarflow-api/tests/last_relevance_e2e_result.json`）  
**范围：** 证据相关性门控、Review 规则、失败传播；不推翻 LangGraph 架构；不伪造检索；不改 API-Key；不启 ScholarFlow Docker。

---

## 1. 根因与代码证据

### 1.1 数据流追踪（原任务 `sf-5787ead265f0`）

| 步骤 | 实际行为 | 问题？ |
|------|----------|--------|
| 用户问题 | 完整保留在 `task_state.json` / `research_plan.objective` | 否 |
| Orchestrator `search_queries` | **整段中文指令**原样作为 arXiv query | **是 — 首次污染点** |
| Orchestrator `code_search_queries` | 硬编码 `langchain RAG` / `retrieval augmented generation` | **是** |
| Paper MCP | `search_academic_papers` query=完整中文长句，`max_results=3` | **是** |
| Paper 原始返回 | GitHub 流行度 / AI Agent / GitHub Emoji 等无关论文（live） | 检索噪声 + 无相关性过滤 |
| Repo 节点 | 硬编码 `fetch_repo_via_mcp("langchain-ai/langchain")`；失败后 fixture 降级 | **是 — 主题错配固化** |
| `data_mode=live` → `mixed_degraded` | `repository_analysis` 降级 `fixture_fallback`（langchain fixture） | 降级无主题校验 |
| Experiment | 固定 Hybrid RAG / Naive RAG / NQ / SQuAD 模板 | **是** |
| Review | 固定 claim「Hybrid retrieval improves over Naive RAG」→ `supported`，理由「Blended/Survey RAG」 | **是 — 与证据/主题无关** |
| Assemble | 9 产物 + `partial_succeeded` | 伪装成“部分成功的完整科研包” |

**问题首次出现位置：**  
`orchestrator_node` 未清洗 query，且旧版 `repository_analysis_node` **硬编码** `langchain-ai/langchain`；Review/Experiment 使用与任务无关的 RAG 固定模板。Paper live 返回虽偏题，但若有相关性门控本可拒绝；真正让错误“成功落盘”的是 **无门控 + 硬编码仓库 + RAG fixture 降级 + 固定 Review claim**。

### 1.2 来源划分（原任务）

| 证据 | 来源 | 模式 |
|------|------|------|
| 3 篇 GitHub/Agent/Emoji 论文 | 外部 arXiv（live MCP） | `live_mcp` |
| `langchain-ai/langchain` | RAG fixture 样本 | `fixture_degraded_from_live` |
| Experiment / Review 文案 | 确定性模板（非 LLM） | `deterministic` |
| `effective_data_mode` | `mixed_degraded` | 与 manifest 一致 |

### 1.3 Review 为何误判 `supported`

旧 `review_node` 在 `decision=="pass"` 时**无条件追加**固定 claim，并把前两篇 paper id 挂上，理由写死为 Blended/Survey RAG——与当前压缩感知任务及实际上游标题均无关。这是规则审查的实现缺陷，不是独立 LLM Reviewer。

---

## 2. 最小修复（实际修改文件）

| 文件 | 变更 |
|------|------|
| `apps/scholarflow-api/scholarflow_api/graph/evidence_gate.py` | **新增**：query 清洗、论文/仓库相关性过滤、fixture 主题兼容、动态 claim + 确定性判定 |
| `apps/scholarflow-api/scholarflow_api/graph/adapters.py` | `search_github_repositories` + `resolve_live_repository`（禁止无关主题默认 langchain） |
| `apps/scholarflow-api/scholarflow_api/graph/nodes.py` | paper/repo 过滤与主题感知降级；experiment 基于上游证据；review 基于动态 claim；失败传播 |
| `extensions/scholar_mcp/...`（若已有） | GitHub search 客户端能力（供 resolve 使用） |
| `apps/scholarflow-api/tests/test_evidence_relevance.py` | **新增** 正/负例回归 |
| `apps/scholarflow-api/tests/test_live_mode_guard.py` | 降级用例改 topic-matched；新增 CS 拒 RAG fixture |
| `apps/scholarflow-api/tests/last_relevance_e2e_result.json` | 复验快照（非 golden） |

**未改：** `sf-5787ead265f0` 产物、RAG golden、冻结题集、API-Key、ScholarFlow Docker。

### 2.1 行为要点

1. **Query 清洗：** 长指令 → `deep learning image compressed sensing`（拉丁优先）。  
2. **相关性：** `score_paper` 启发式 + 压缩感知场景下对 GitHub 社会学 / langchain 的硬拒绝；非 LLM 编造分数。  
3. **Fixture：** `rag-test-001` 视为 RAG 主题；与压缩感知冲突时 **禁止** 静默补齐。  
4. **Review：** 仍为**确定性规则审查**（非独立 LLM）；claim 由当前问题 + evidence_id 生成；Schema 无 `insufficient_evidence` 时映射为 `unverified` + reason 前缀。  
5. **失败传播：** 上游无效 → experiment fail → review fail → assemble skip → `overall_status=failed`（不再用无关证据写出“成功科研报告”）。

---

## 3. 修复前后对照

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| CS 主题 + live 偏题论文 | 照单全收 | 过滤拒绝；零相关 → paper fail |
| CS + langchain 硬编码/fixture | 接受并写入报告 | 主题冲突拒绝 |
| live 失败 + `allow_fixture_fallback` + CS | RAG fixture → `mixed_degraded` 部分成功 | fixture off-topic → **failed** |
| RAG 主题 + RAG fixture | 成功 | 仍成功（回归保留） |
| Review claim | 固定 Hybrid RAG `supported` | 动态 topic/repo alignment；无固定口号 |
| Experiment | 固定 RAG 管道 | 基于 accepted 证据标题/指标 |

**测试：** `pytest`（backend venv）`97 passed, 9 skipped`（全量 scholarflow-api，忽略 live_llm）；其中 `test_evidence_relevance` + `test_live_mode_guard` + `test_research_graph` **21 passed**。

---

## 4. 原任务 vs 新任务状态

| 任务 | 状态 | 说明 |
|------|------|------|
| `sf-5787ead265f0` | **保持** `partial_succeeded` / `mixed_degraded` | 历史证据未覆盖 |
| `sf-rel-e2e-1792380524` | `failed` / `effective_data_mode=live` | 同主题复验；arXiv **429**；RAG fixture 被拒；无 9 产物伪装成功 |

### 4.1 复验观测（`sf-rel-e2e-1792380524`）

- **清洗后 MCP query：** `deep learning image compressed sensing`（日志可见 arXiv URL 已用该 query）。  
- **原始检索：** arXiv 连续 429，MCP `search_academic_papers` 重试后失败。  
- **接受/拒绝：** 无 live 论文被接受；RAG fixture **明确拒绝**（off-topic）。  
- **仓库：** GitHub search 未匹配到主题仓库；langchain fixture 拒绝。  
- **节点：** paper/repo/experiment/review **failed**；assemble **skipped**。  
- **Review：** `Insufficient evidence…` → `unverified`（insufficient_evidence）。  
- **终态：** `failed`（诚实报告检索不足，未混入无关证据）。

---

## 5. 验证结果摘要

| 要求 | 结果 |
|------|------|
| CS 不接受无关 GitHub/Agent 论文 | 单测 + E2E 拒绝路径 **通过** |
| 仓库须相关 | langchain@CS 拒绝；RAG@langchain 接受 |
| live 不足不静默混主题 fixture | CS + fallback **failed** |
| Review 不因无关证据判 supported | 固定口号已移除 |
| 上游无效则 experiment 不用 | **通过** |
| 下游与有效上游一致 | 失败时无假报告；RAG fixture 路径仍一致 |
| 有效 live 可通过 | mock 相关论文+仓库 **通过** |
| 原 fixture / 1–8.5 回归 | 全量 97 passed |

---

## 6. 仍未解决的风险

1. **相关性启发式**仍可能漏杀/误杀边界论文；非语义 embedding 门控。  
2. **arXiv 429 / GitHub 无结果**时只能诚实失败，暂无主题匹配的备用语料（按设计不拿 RAG fixture 顶替）。  
3. Review 仍是规则机，**不能**替代领域专家或 LLM 深度审查。  
4. `insufficient_evidence` 未进入 Pydantic `ReviewStatus` 枚举（用 `unverified` + reason 前缀）。  
5. Fixture 主题目前靠路径约定（`rag-test-001`）+ `fixture_theme_compatible`，尚未独立 `theme.json` 元数据文件。  
6. ~~单次 live 复验因 429 未验证适配器成功~~ → 见 **§8**（适配器 live 已通；**完整工作流 live 成功仍未重跑**）。

---

## 7. 暂停点（阶段修复）

阶段修复交付完成。后续定向复验见 §8。

---

## 8. 定向复验：真实检索成功路径 vs 限流/失败路径（2026-10-19）

**原则：** 失败保护通过 ≠ 真实检索成功。两者分开报告。  
**保护：** `sf-5787ead265f0`（`partial_succeeded`）与 `sf-rel-e2e-1792380524`（`failed`）均未覆盖；未改 Golden/冻结题集/API-Key；未启 ScholarFlow Docker。

### 8.1 查询清洗前后对照

| 项 | 值 |
|----|-----|
| 用户原始问题 | `基于深度学习的图像压缩感知重建` |
| 清洗前（原缺陷） | 整段长指令 / 或硬编码 `langchain RAG` |
| 清洗后论文 query | `deep learning image compressed sensing` |
| 清洗后仓库 query | `deep learning image compressed sensing language:Python stars:>10` |
| 传入 MCP/适配器参数 | `{query: "deep learning image compressed sensing", max_results: 3}`（探针）；无 RAG/Agent 固定覆盖 |

证据：`apps/scholarflow-api/tests/last_relevance_live_probe.json`；单测 `test_query_cleaning_cs_topic`。

### 8.2 真实 MCP/适配器请求与返回（Path A — 小规模，非完整工作流）

**一次** arXiv + **一次** GitHub 探针（无完整 LangGraph 重跑，避免叠加重试）：

| 来源 | 状态 | 原始返回摘要 | 门控后 |
|------|------|--------------|--------|
| arXiv | **成功**（~3.3s） | 3 篇：Structured Compressed Sensing…；Learn to Accumulate…；Modern Mathematics of Deep Learning | 接受 2 / 拒绝 1；首篇与 CS 强相关（`paper-2410.18954v2`） |
| GitHub | **成功**（~0.9s） | `lixing0810/Pytorch_ADMM-CSNet`（ADMM-CSNet 图像压缩感知）；`nmduc/deep-ternary`（图像 CS） | 2/2 接受；均可追溯 URL |

**真实检索成功路径（适配器级）：已验证。**  
**真实检索成功路径（完整工作流 end-to-end succeeded）：本次未重跑**（按“优先小规模适配器验证”执行）。Mock 全链路成功见 `test_path_a_mock_relevant_live_succeeds`。

边界备注：启发式将 *The Modern Mathematics of Deep Learning* 以 score 4.8 接受——可能偏松；**未**为通过测试下调门槛，记为残留误放风险。

### 8.3 429 处理行为（审计 + 最小加固）

| 检查项 | 修复前 | 现状态 |
|--------|--------|--------|
| 识别 HTTP 429 | 仅作为通用 `HTTPError` | `is_rate_limited` + arXiv 包装为明确 `arXiv HTTP 429 … Retry-After=` |
| 遵守 Retry-After | **否** | `with_retry` 读取 Retry-After，**上限 30s**；缺省 5s |
| 有上限退避 | 指数退避 max 3 次 | 保留 max 3；429 用 capped Retry-After |
| 并行无节制重试 | MCP 外层 3 次 × arXiv 内层 3 次，易放大 429 | MCP `call_tool` 遇 429/**rate limit** **立即停止外层重试** |
| 失败错误信息 | TaskGroup 笼统信息 | 保留/传播含 429 与 query 的错误串 |
| 无关 fixture | CS 主题已拒绝（上轮） | Mock `test_path_b_arxiv_429_rejects_offtopic_fixture` **通过** |
| 状态区分 | — | 检索失败 → 节点 `failed` → `overall_status=failed`；不写伪装成功报告 |

无第二论文源（无 Semantic Scholar/OpenAlex 配置）；429 时**不能**换无关来源伪造成功。

### 8.4 失败路径（Path B — Mock）

| 场景 | 结果 |
|------|------|
| arXiv 429 + fixture fallback | `failed`；RAG fixture 拒绝；experiment fail；无产物伪装成功 |
| live 返回无关 GitHub/Agent 论文 | 门控拒绝；工作流 `failed`；Review 无 `supported` |
| 无关仓库 / 全源无效 | 上轮 + 本轮回归覆盖 |

### 8.5 工作流依赖（规则审查，非 LLM Reviewer）

- paper / repo 独立 I/O；experiment 只消费上游有效 `evidence_id`。  
- Review 使用当前任务动态 claim；无效证据不判 `supported`。  
- 无效上游阻止正式科研结论；assemble 在 `review=fail` 时 skip。  
- **未**实现独立 LLM Reviewer。

### 8.6 测试统计

| 套件 | 结果 |
|------|------|
| `scholarflow-api`（跳过 live_llm/sse/agent/bridge live） | **101 passed, 1 skipped** |
| `test_retrieval_paths` + relevance + live_mode_guard | 18 passed |
| `extensions/scholar_mcp/tests/test_resilience.py` | **4 passed**（含 429 Retry-After） |

### 8.7 尚未验证 / 残留风险

1. **完整 live 工作流**在 arXiv 可用时的 `succeeded` 终态（适配器已通，全图未再跑）。  
2. 启发式误放（如泛 Deep Learning 综述）。  
3. GitHub 无 token 时的 403 行为（本次 search 已成功，未专项压测）。  
4. 诊断性错误报告产物（当前 fail → assemble skip；无单独 diagnostic artifact 文件）。

### 8.8 本轮结论（分开报告）

| 路径 | 结论 |
|------|------|
| **失败保护 / 降级** | **通过**（Mock + 上轮 429 E2E 记录保留） |
| **真实检索成功（适配器）** | **通过**（arXiv + GitHub 探针，见 `last_relevance_live_probe.json`） |
| **真实检索成功（完整工作流）** | **尚未验证** |

**暂停，不进入新阶段。**
