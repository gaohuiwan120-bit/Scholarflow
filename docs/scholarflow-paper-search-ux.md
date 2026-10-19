# ScholarFlow 论文检索与结果展示优化记录

- **status**: PASS（小范围优化；有对照，不宣称“相关性已达标黄金标准”）
- **tested_at (UTC)**: `2026-10-18T15:21Z`（以 `scholarflow-paper-search-ux-evidence.json` 为准）
- **范围**: 增量优化 `search_papers` 重排 + Chat 论文卡片 / Markdown / 工具折叠
- **未改**: 阶段 8.0–8.5 主架构、API-Key、冻结题集、Golden snapshot、ScholarFlow Docker

## 1. 修改文件清单

| 路径 | 变更 |
|------|------|
| `apps/scholarflow-api/scholarflow_api/chat/paper_rank.py` | **新建**：URL 清洗、标题/摘要启发式重排、`kind_hint`（仅标题含 survey/review） |
| `apps/scholarflow-api/scholarflow_api/chat/tools.py` | `search_papers` 过采 + 重排；返回 authors/abstract/year；工具说明与 SYSTEM_PROMPT |
| `apps/scholarflow-api/scholarflow_api/chat/agent.py` | evidence_refs 富化；search_papers 摘要；截断 JSON 兜底 |
| `apps/scholarflow-api/scholarflow_api/chat/schemas.py` | EvidenceRef 增加 authors/year/abstract/kind_hint/relevance_score |
| `apps/scholarflow-api/scholarflow_api/graph/adapters.py` | 保留 abstract；source_url 清洗 |
| `apps/scholarflow-api/tests/test_paper_rank.py` | **新建** Mock 重排/URL/弱词惩罚 |
| `apps/scholarflow-web/src/markdown.tsx` | 表格 / 列表 / 粗体 / 链接渲染修复 |
| `apps/scholarflow-web/src/ChatPage.tsx` | 论文卡片；工具详情默认折叠；去重证据列表 |
| `apps/scholarflow-web/src/api.ts` | EvidenceRef 类型对齐 |
| `apps/scholarflow-web/src/styles.css` | 卡片 / 表格 / 工具折叠样式 |
| `scripts/verify_scholarflow_paper_search_ux.py` | Live 对照 + Agent SSE 验证 |
| `docs/scholarflow-paper-search-ux-evidence.json` | 原始对照证据 |
| `docs/scholarflow-paper-search-ux.md` | 本文档 |

## 2. 问题分析（优化前）

1. arXiv `all:{query}` + `sortBy=relevance`：宽泛查询易混入仅含 sparse/recovery/sensing 的弱相关条目。
2. 工具层按 MCP 原序截断，**无本地重排**；authors/abstract 在 slim 中丢失，模型难以区分代表性工作。
3. 前端 Markdown 表格以原始 `|` 行展示；工具 JSON 默认展开；证据区与正文论文列表重复。

## 3. 实际检索对照（真实 arXiv，非伪造）

证据：`docs/scholarflow-paper-search-ux-evidence.json`。

### 3.1 宽泛：`compressed sensing`

| | Top 标题（节选） |
|--|--|
| arXiv 原序 | Learning Structured CS…；CS Clinical Practice…；Quantization and Compressive Sensing；Hierarchical CS；quest for optimal sampling… |
| 重排后 | Learning Structured CS…；Hierarchical CS；AdaBoost one-bit CS；Clinical Practice…；Photoacoustic CS… |

`order_changed=true`；URL 均为裸 `https://arxiv.org/abs/...`。

### 3.2 专题：`deep learning compressed sensing image reconstruction`

重排后 Top 含 CS 图像重建 / MRI / single-pixel 相关真实条目；并对 **remote sensing**（仅 sensing、无 compress）施加惩罚（单元测试覆盖）。

**声明：** `order_changed` 与启发式 `relevance_score` **不等于**人工相关性标注提升，也不可写成“检索质量已达到 gold standard”。

### 3.3 Live Agent（用户原问题）

- 查询：「能不能帮我找一找关于压缩感知的论文」
- SSE：`tool_start` 出现；`done.status=completed`
- `evidence_refs` ≥1；URL 为裸 https；浏览器出现「论文结果」卡片 +「打开原文」+「查看工具详情」折叠
- 模型自主调用 `search_papers`（例：query=`compressed sensing survey`），非关键词硬路由

## 4. 测试结果分列

| 类型 | 结果 |
|------|------|
| Mock | `test_paper_rank.py` **5 passed**；`test_chat_sse_mock` + `test_chat_api` **24 passed** |
| 检索对照 | `verify_scholarflow_paper_search_ux.py` PASS（宽泛+专题 order_changed + url_ok） |
| Live 工具回灌 | 同上脚本 + 浏览器压缩感知查询 PASS |
| UI | 论文卡片、折叠工具详情、工作台 Tab 仍可用 |

## 5. 剩余问题

1. 启发式重排无法替代学术影响力排序；宽泛查询仍可能缺少 Candès/Donoho 等经典（arXiv relevance 候选集限制）。
2. 模型偶发连续两次 `search_papers`（多 query），UI 会显示两次工具行——均为真实事件。
3. 若工具结果被截断导致摘要 JSON 解析失败，前端对 `{` 开头摘要默认折叠（不在主界面展开）。
4. Markdown 仅为轻量自研渲染，复杂嵌套语法仍可能 residual。

## 6. 试用

刷新 **http://127.0.0.1:5173/** 后新建会话，再试「压缩感知」或「深度学习图像压缩感知」。

**暂停。** 不自动开展更大规模开发。
