# ScholarFlow 验收提示词（复制到【新对话】）

请严格按 ScholarFlow 执行，禁止用模型知识库写报告。

## 要求
1. 先加载 skill：`scientific-research-orchestration`
2. 必须调用以下 MCP 工具（名称必须一字不差）：
   - `scholar_mcp_search_academic_papers`（检索 arXiv，至少 3 篇）
   - `scholar_mcp_get_repository_overview`（至少一个 GitHub 仓库，如 `langchain-ai/langchain`）
   - `scholar_mcp_assemble_task_artifacts`（或分别用 matrix/report 工具）
3. task id：`rag-test-001`
4. 主题：RAG（检索增强生成）主流架构与开源实现
5. 用 `write_file` 把 9 个产物写入：`/mnt/user-data/outputs/rag-test-001/`

## 可用工具确认
当前环境应包含：`web_search`、`write_file`、`bash`/`str_replace`，以及全部 `scholar_mcp_*` 工具。
若你只能看到 `read_file` / `review_skill_package`，请直接回复「工具白名单异常」，不要用知识库续写。

## 禁止
- 不要说「没有工具所以用知识库」
- 不要编造论文标题、arXiv ID、GitHub star
- 每条证据必须有真实 `source_url`

## 成功标准（契约 9 件套）
必须写入 `/mnt/user-data/outputs/rag-test-001/`：
research_report.md, research_plan.json, paper_evidence.json, paper_matrix.csv,
repository_evidence.json, repository_matrix.csv, experiment_plan.md,
evidence_review.json, sources.json

不要写 research_plan.md / experiment_plan.json 替代契约文件。
MCP 工具失败时请原样报错并重试一次，不要改用 web_search 兜底伪造流水线。
