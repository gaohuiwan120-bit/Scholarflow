# ScholarFlow Live E2E Acceptance Report

- **Date (UTC):** 2026-10-19T05:59:00Z
- **Task ID:** `sf-eb5a55596fa1`
- **Verdict:** **PASS** — live `research_orchestration` completed with real MCP paper/repo evidence, parallel fan-out, core-driven experiment plan, review pass, and nine artifacts persisted.
- **Raw probe JSON:** `apps/scholarflow-api/tests/last_live_e2e_acceptance.json`
- **Task data:** `apps/scholarflow-api/data/tasks/sf-eb5a55596fa1/` (new task; historical tasks untouched)
- **Elapsed:** 20.17s wall clock (API create → terminal)

---

## 1. Task identity

| Field | Value |
| --- | --- |
| `task_id` | `sf-eb5a55596fa1` |
| `kind` | `research_orchestration` |
| `status` (terminal) | `succeeded` |
| `terminal` | `true` |
| `overall_status` | `succeeded` |
| `review_decision` | `pass` |
| `data_mode` | `live` |
| `effective_data_mode` | `live` |
| `degradation_events` | `[]` (no fixture fallback) |
| `allow_fixture_fallback` | `false` |

Question (abbreviated): deep-learning image compressed-sensing reconstruction — papers + real GitHub repos + core-driven experiment + evidence review + nine artifacts.

---

## 2. Retrieval queries & MCP calls

### Paper search queries (plan)

1. `deep learning image compressed sensing core`
2. `deep learning image compressed sensing core reconstruction`
3. `image compressive sensing deep learning`

Effective live query recorded on paper finish event:  
`image compressive sensing deep learning reconstruction`

### Repo search query (plan / node)

`image compressive sensing ISTA-Net language:Python stars:>10`

Selected repository: **`jianzhangcs/ISTA-Net-PyTorch`** (method=`topic_hint`; MCP overview succeeded).

> Residual note: `resolve_meta.search_error` reported `No module named 'scholar_mcp'` for the **direct** GitHub search import inside the API process. Selection still succeeded via curated topic hint + live `get_repository_overview` MCP (not fixture). See §8.

### MCP tool calls (from task state)

| Tool | OK | Duration (ms) | Input (sanitized) |
| --- | --- | --- | --- |
| `search_academic_papers` | true | 9125 | query=`deep learning image compressed sensing core`, max_results=12 |
| `search_academic_papers` | true | 5818 | query=`image compressive sensing deep learning reconstruction`, max_results=12 |
| `get_repository_overview` | true | 9734 | repository=`jianzhangcs/ISTA-Net-PyTorch` |
| `assemble_task_artifacts` | true | 1966 | (assembled payloads) |

Paper node `data_source=live_mcp`; repo node `data_source=live_mcp`; assemble `data_source=live_mcp`.

---

## 3. Paper relevance tiers

Accepted into workflow: **4** (core=2, supporting=2). Rejected during gate: **8** (not persisted as formal evidence).

| Evidence ID | Tier | Title | Source URL | Signals (abbrev.) |
| --- | --- | --- | --- | --- |
| `paper-2207.06746v1` | **core** | Single-Pixel Image Reconstruction Based on Block Compressive Sensing and Deep Learning | https://arxiv.org/abs/2207.06746v1 | title deep learning + compressed/compressive sensing; `tier:core_image_cs_reconstruction` |
| `paper-0812.3137v1` | **core** | Compressive sensing: a paradigm shift in signal processing | https://arxiv.org/abs/0812.3137v1 | CS phrase + `tier:core_image_cs_reconstruction` |
| `paper-2301.02033v1` | **supporting** | Physics-informed … cardiac MRI | https://arxiv.org/abs/2301.02033v1 | `tier:supporting_domain_cs_not_natural_image` |
| `paper-1907.11711v1` | **supporting** | Deep MRI Reconstruction: Unrolled Optimization… | https://arxiv.org/abs/1907.11711v1 | `tier:supporting_sparse_or_generic_cs` |

Irrelevant candidates were rejected by the gate (count=8) and did not enter experiment baselines.

---

## 4. Repository relevance

| Evidence ID | Tier | Repository | Source URL | Description / signals |
| --- | --- | --- | --- | --- |
| `repo-jianzhangcs-ISTA-Net-PyTorch` | **core** | jianzhangcs/ISTA-Net-PyTorch | https://github.com/jianzhangcs/ISTA-Net-PyTorch | Image Compressive Sensing (CVPR2018 PyTorch); `accept:repo_cs_markers` |

Verified as on-topic for image CS reconstruction (not accepted merely because it was a hint).

---

## 5. Parallel execution evidence

Paper and repository nodes started at the **same timestamp** and overlapped in time:

| Node | started_at | ended_at | duration_ms | status | data_source |
| --- | --- | --- | --- | --- | --- |
| `paper_research` | 1792389520.75649 | 1792389535.7130089 | 14956 | succeeded | live_mcp |
| `repository_analysis` | 1792389520.75649 | 1792389530.4972415 | 9740 | succeeded | live_mcp |

- `started_same_second`: **true**
- `time_ranges_overlap`: **true**
- Events: `paper_started` / `repo_started` share `ts=1792389520.75649`; `repo_finished` before `paper_finished`; then `join_gate`.

Downstream: experiment → review → assemble ran only after join.

---

## 6. Experiment design ↔ upstream evidence

Structured experiment fields recorded:

- **`upstream_paper_ids` (core only):** `paper-2207.06746v1`, `paper-0812.3137v1`
- **`upstream_supporting_paper_ids` (background):** `paper-2301.02033v1`, `paper-1907.11711v1`
- **`upstream_repo_ids`:** `repo-jianzhangcs-ISTA-Net-PyTorch`

Experiment plan content checks:

- Baselines / pipeline cite **CORE** paper titles and `jianzhangcs/ISTA-Net-PyTorch`
- Metrics: PSNR, SSIM, params, FLOPs/time
- Ablations: measurement-rate sweep, module ablation, loss/schedule
- Risks explicitly mark supporting MRI papers as **background only**
- No Hybrid RAG / Naive RAG template language

---

## 7. Review results

`review_decision=pass`; reviewer=`deterministic_rules`; **5** claims; **0** Hybrid/Naive RAG slogan claims.

| Claim (abbrev.) | Status | Related IDs |
| --- | --- | --- |
| Core papers topically related | supported | paper-2207…, paper-0812… |
| Core paper contributes (SPI / BCS) | supported | paper-2207.06746v1 |
| Core paper contributes (paradigm shift) | supported | paper-0812.3137v1 |
| Supporting are background only | supported | paper-2301…, paper-1907… |
| Repository related | supported | repo-jianzhangcs-ISTA-Net-PyTorch |

Failure items: **none**.

---

## 8. Nine artifacts

Directory: `apps/scholarflow-api/data/tasks/sf-eb5a55596fa1/artifacts/`

| Filename | Exists | Bytes (approx.) | Content / consistency |
| --- | --- | --- | --- |
| `research_report.md` | yes | present | Objective + core/supporting papers with arXiv URLs + ISTA-Net-PyTorch README excerpt + experiment summary + review; no RAG slogans |
| `research_plan.json` | yes | present | Live search/code queries; expected nine outputs |
| `paper_evidence.json` | yes | 4 items | IDs/URLs match sources; tier tags in limitations |
| `paper_matrix.csv` | yes | present | Matrix of accepted papers |
| `repository_evidence.json` | yes | 1 item | ISTA-Net-PyTorch + GitHub URL |
| `repository_matrix.csv` | yes | present | Repo matrix |
| `experiment_plan.md` | yes | present | Core-driven baselines/ablations; supporting listed as non-primary |
| `evidence_review.json` | yes | 5 items | Matches §7 |
| `sources.json` | yes | 5 sources | 4 arXiv + 1 GitHub URLs aligned with evidence IDs |

Assemble node: `Built 9 artifacts (live_mcp)`; `persisted=true`.

---

## 9. Tests run with this acceptance

| Suite | Result |
| --- | --- |
| `apps/scholarflow-api/tests/test_evidence_relevance.py` | included below |
| `apps/scholarflow-api/tests/test_retrieval_paths.py` | included below |
| `apps/scholarflow-api/tests/test_fcb379_regression.py` | included below |
| `apps/scholarflow-api/tests/test_paper_rank.py` | included below |
| `apps/scholarflow-api/tests/test_relevance_tiers.py` | included below |
| `apps/scholarflow-api/tests/test_research_graph.py` | included below |
| **Subtotal (scholarflow-api)** | **45 passed** |
| `extensions/scholar_mcp/tests/test_github_auth_fallback.py` | **2 passed, 1 skipped** (live rate-limit skip path) |

---

## 10. Acceptance gates (checklist)

| Gate | Result |
| --- | --- |
| Live only (no fixture degradation) | PASS |
| Papers via live MCP | PASS |
| Repos via live MCP | PASS |
| Paper ‖ repo parallel timestamps | PASS |
| Has core papers | PASS |
| Has on-topic repo | PASS |
| No Hybrid/Naive RAG review slogans | PASS |
| Nine artifacts present | PASS |
| `overall_status` succeeded | PASS |

### Residual (non-blocking)

- API-process direct `scholar_mcp` import for GitHub **search** failed (`No module named 'scholar_mcp'`), so search candidates were empty and selection used **topic_hint** + live MCP overview. Repo evidence itself is still live MCP, not fixture. Recommend ensuring `extensions/scholar_mcp` is on the API `PYTHONPATH` (or start script) so search and hint both run without that import error.

---

## 11. Final verdict

**端到端 live 验收通过。**

Complete research orchestration used authenticated GitHub + arXiv via MCP, ran paper and repository nodes in parallel, graded evidence into core/supporting, designed experiments from core upstream IDs, passed review without RAG templates, and persisted nine consistent artifacts under `sf-eb5a55596fa1`.
