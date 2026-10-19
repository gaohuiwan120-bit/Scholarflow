# ScholarFlow Benchmark 评测体系

面向 **Agent 社招** 的可量化评测框架：结构完整性 + 质量指标 + E2E 硬门槛。

---

## 1. 三层评测模型

| 层级 | 测什么 | 脚本 |
|------|--------|------|
| **L1 结构层** | 9 文件齐全、JSON 可解析、Schema 合法、矩阵行数一致 | `evaluation/metrics.py` |
| **L2 质量层** | 主题相关性、URL 合法性、证据丰富度、反占位符 | `evaluation/quality_metrics.py` |
| **L3 E2E 门槛** | 关键指标硬门槛（完整性=1、Schema=1、URL≥0.8、相关性≥0.5） | `e2e_pass_gate` |

---

## 2. Benchmark 任务集

**10 个固定 topic**：`evaluation/benchmark_tasks.json`

每个 task 包含：

- `prompt` — 可直接发给 ScholarFlow 的 E2E 指令
- `keywords` — 主题相关性评分用词
- `min_papers` / `min_repos` — 证据覆盖阈值

---

## 3. 运行方式

### 3.1 Golden 模式（简历 Demo / CI）

使用 realistic 样例产物评分，验证评测管线本身：

```bash
cd backend
uv run python ../evaluation/run_benchmark.py --mode golden
```

输出：

- `evaluation/reports/latest.json`
- `evaluation/reports/latest.md`

### 3.2 Artifacts 模式（真实 E2E 后评分）

1. 跑 E2E（见下节）
2. 将每个 task 的 9 文件放入 `evaluation/results/<task-id>/`
3. 评分：

```bash
uv run python ../evaluation/run_benchmark.py --mode artifacts --artifacts-root ../evaluation/results
```

### 3.3 E2E Prompt 导出 / 执行

```bash
# 仅导出 10 条 prompt（无需 LLM）
uv run python ../evaluation/e2e_runner.py --dry-run

# 真实调用 ScholarFlowClient（需 DEEPSEEK_API_KEY + Gateway）
uv run python ../evaluation/e2e_runner.py --limit 3
```

### 3.4 优化前后对比

```bash
uv run python ../evaluation/compare_runs.py \
  evaluation/reports/baseline.json \
  evaluation/reports/optimized.json \
  --output evaluation/reports/comparison.md
```

---

## 4. 指标说明（面试可背）

| 指标 | 含义 | 简历表述 |
|------|------|----------|
| `artifact_completeness` | 9 类产物齐全率 | 端到端产物完整率 |
| `schema_validity` | Pydantic 校验通过率 | 结构化输出合法率 |
| `topic_relevance` | 关键词命中率 | 主题相关性 |
| `url_validity` | arXiv/GitHub URL 比例 | 来源可追溯率 |
| `evidence_coverage` | 论文/仓库数量达标 | 证据覆盖度 |
| `e2e_pass_rate` | 硬门槛通过率 | **核心 KPI** |

---

## 5. 推荐工作流（写简历前）

```
1. 配置 DEEPSEEK_API_KEY + GITHUB_TOKEN
2. 用 docs/scholar-flow/e2e-prompt.md 在 UI 跑真实任务（如 rag-test-001）
3. 从 Sandbox 拷贝产物到 evaluation/results/<benchmark-task-id>/
   或直接：uv run python ../evaluation/normalize_and_score_e2e.py
4. 查看 evaluation/reports/e2e-rag-test-001.md / latest.md
5. 把 pass rate 写进 resume-highlights.md
6. compare_runs.py 做优化前后对比（可选）
```

### 已完成基线（2026-07-21）

| 模式 | pass rate | avg score | 报告 |
|------|-----------|-----------|------|
| 真实 artifacts（rag-survey） | 100% | 1.00 | `evaluation/reports/e2e-rag-test-001.md` |
| Golden 10-case | 100% | 0.99 | `evaluation/reports/golden-baseline.md` |

---

## 6. 与旧版 run_eval.py 的关系

- `run_eval.py` — 20 task **fixture** 结构自检（快速 CI）
- `run_benchmark.py` — **10 task 质量 benchmark**（简历级）

两者互补，不互相替代。
