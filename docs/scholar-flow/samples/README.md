# Sample: rag-test-001

真实 ScholarFlow E2E 产物（2026-07-21），已归一化为 ScholarFlow 契约 Schema。

| 文件 | 说明 |
|------|------|
| research_report.md | 综合报告 |
| research_plan.json | 研究计划 |
| paper_evidence.json | 3 篇 arXiv 证据 |
| paper_matrix.csv | 论文对比矩阵 |
| repository_evidence.json | LangChain 仓库证据 |
| repository_matrix.csv | 仓库矩阵 |
| experiment_plan.md | 实验方案 |
| evidence_review.json | 交叉评审 |
| sources.json | 来源清单 |

评分报告：`evaluation/reports/e2e-rag-test-001.md`  
重新评分：`uv run python ../evaluation/normalize_and_score_e2e.py`（在 `backend/` 下）
