# ScholarFlow 生产级工程清单

面向 Agent 社招的「准生产」能力说明。

---

## 1. 已实现的工程能力

| 能力 | 实现 | 位置 |
|------|------|------|
| **容器化部署** | Docker Compose 开发栈 | `docker/docker-compose-dev.yaml` |
| **MCP 隔离** | 独立 stdio MCP Server | `extensions/scholar_mcp/` |
| **外部 API 容错** | 指数退避重试（3 次） | `scholar_mcp/clients/resilience.py` |
| **Schema 校验** | Pydantic 拦截非法 JSON | `scholarflow/scholar/validation.py` |
| **确定性聚合** | 矩阵/报告 Python 生成 | `scholarflow/scholar/artifacts.py` |
| **可观测性（ScholarFlow 原生）** | Langfuse / LangSmith tracing | `config.yaml` → `tracing` |
| **Token 计量** | ScholarFlow token_usage | `config.yaml` → `token_usage.enabled: true` |
| **评测回归** | Benchmark + compare | `evaluation/` |

---

## 2. 推荐生产配置

### 2.1 Langfuse Tracing

在 `config.yaml` 中启用（需 `.env` 配置 Key）：

```yaml
tracing:
  langfuse:
    enabled: true
    public_key: $LANGFUSE_PUBLIC_KEY
    secret_key: $LANGFUSE_SECRET_KEY
    host: https://cloud.langfuse.com
```

**简历表述：** 集成 Langfuse 追踪多 Agent / MCP 工具调用链。

### 2.2 MCP 超时

`extensions_config.json`：

```json
"tool_call_timeout": 120
```

### 2.3 GitHub Token

`.env`：

```env
GITHUB_TOKEN=ghp_xxx
```

降低 GitHub API 限流失败率。

---

## 3. 可靠性设计

### 3.1 反幻觉策略（多层）

1. **Skill 协议** — 禁止编造 DOI/arXiv/统计数据
2. **MCP 工具** — 证据必须带 `source_url`
3. **Schema** — `verification_status` 字段强制标注
4. **Benchmark** — `url_validity` + `anti_fabrication_heuristic`

### 3.2 失败降级

- arXiv/GitHub 请求失败 → MCP retry 3 次
- 仍失败 → Agent 应标记 `verification_status: inaccessible`
- 聚合层不因单条 evidence 缺失而崩溃

---

## 4. 性能优化实验（简历对比项）

| 实验 | 做法 | 对比指标 |
|------|------|----------|
| 并行编排 | Skill 内 3 路 task 并发 vs 串行 | `elapsed_seconds`（e2e_runner manifest） |
| 检索策略 | 2–3 关键词 vs 长句 query | `topic_relevance` + arXiv 命中数 |
| 确定性工具 | Python 矩阵 vs 纯 LLM 生成 CSV | `matrix_row_consistency` + 人工幻觉抽检 |

用 `compare_runs.py` 输出 before/after 表格。

---

## 5. 健康检查

```bash
curl http://localhost:2026/health
bash scripts/verify_scholarflow.sh
```

---

## 6. 尚未实现（诚实边界）

- 多租户 / RBAC
- K8s 生产编排（ScholarFlow provisioner 模式可选但未在本项目验证）
- 自动 LLM-as-judge（可后续加）
- 专用 Research Workspace 前端

面试时主动说明边界，反而加分。
