# ScholarFlow data contracts

All JSON artifacts use UTF-8. CSV matrices use comma separators and `\n` line endings.

## research_plan.json → `ResearchPlan`

| Field | Type | Required |
|-------|------|----------|
| task_id | string | yes |
| title | string | yes |
| objective | string | yes |
| research_questions | string[] | no |
| search_queries | string[] | no |
| code_search_queries | string[] | no |
| date_range | `{start?, end?}` | no |
| expected_outputs | string[] | no |
| completion_criteria | string[] | no |

## paper_evidence.json → `PaperEvidenceCollection`

Wrapper: `{ "items": PaperEvidence[] }`

| Field | Type | Notes |
|-------|------|-------|
| evidence_id | string | stable id |
| title | string | |
| authors | string[] | |
| year | int | optional |
| venue | string | optional |
| identifier | string | e.g. arXiv id |
| source_url | string | required, non-empty |
| research_problem | string | |
| methodology | string | |
| datasets | string[] | |
| metrics | string[] | |
| key_findings | string[] | |
| limitations | string[] | |
| evidence_level | enum | abstract_only, metadata_only, full_text, secondary_source |
| verification_status | enum | verified, partially_verified, unverified, inaccessible |

## repository_evidence.json → `RepositoryEvidenceCollection`

Wrapper: `{ "items": RepositoryEvidence[] }`

| Field | Type |
|-------|------|
| evidence_id | string |
| repository | string | `owner/name` |
| source_url | string |
| description | string |
| language | string |
| framework | string[] |
| architecture_summary | string |
| key_modules | string[] |
| installation_summary | string |
| reproducibility_notes | string[] |
| limitations | string[] |
| verification_status | enum |

## experiment_plan.md

Markdown document derived from `ExperimentPlan`:

- objective, hypotheses, datasets, baselines
- proposed_pipeline, evaluation_metrics, ablation_studies
- resource_requirements, implementation_steps, risks

## evidence_review.json → `ReviewFindingCollection`

Each `ReviewFinding`:

| Field | Type |
|-------|------|
| claim | string |
| related_evidence_ids | string[] |
| status | supported, partially_supported, unsupported, conflicting, unverified |
| reason | string |
| recommended_action | string |

## sources.json → `SourceCollection`

Each `SourceRecord`:

| Field | Type |
|-------|------|
| evidence_id | string |
| kind | paper, repository, upload, web |
| title | string |
| url | string |
| accessed_at | ISO8601 string, optional |
| verification_status | enum |

## Matrices

- `paper_matrix.csv` — one row per `PaperEvidence` (see `scholarflow.scholar.matrix.PAPER_MATRIX_COLUMNS`)
- `repository_matrix.csv` — one row per `RepositoryEvidence`

## research_report.md

Human-readable synthesis built by `scholarflow.scholar.report.build_research_report`.

## Path convention

Virtual sandbox path: `/mnt/user-data/outputs/<task_id>/`

Helper: `scholarflow.scholar.paths.artifact_path(task_id, filename)`
