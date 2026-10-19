# Agent Bench v1 — Frozen Metric Definitions

**Suite version:** `agent-bench-v1`  
**Freeze rule:** definitions below are fixed before scored runs. Do not rewrite criteria after measuring to make résumé numbers look better.

Old `evaluation/run_benchmark.py --mode golden` synthesizes artifacts and **must not** fill `e2e_completion_rate`.

---

## 1. Per-task outcomes (mutually exclusive)

| Outcome | Meaning |
|---------|---------|
| `succeeded` | All assertions for the expected success path pass |
| `partial_succeeded` | Spec explicitly allows partial; actual API/runtime status matches |
| `correct_refuse` | Insufficient evidence / MCP rounds exhausted; refuse text + flags match |
| `failed` | Business assertion failed |
| `infra_error` | Import/timeout/infra (e.g. MCP stdio cold-start hard fail); reported separately |

---

## 2. End-to-end completion rate (résumé target: 90%)

\[
\text{e2e\_completion\_rate} = \frac{\#\{\text{e2e outcome}=succeeded\}}{10}
\]

- Denominator is fixed at **10** (suite size). Unrun / `infra_error` still count in the denominator.
- `partial_succeeded` and `correct_refuse` are **not** completion successes.
- Negative-path E2E that **verify** API `failed` (e.g. force_fail_paper) use `expect_outcome=succeeded` when assertions pass — the bench outcome is verification success, while recorded `status` remains `failed`.
- Fixture and live results are **never** merged into one completion rate.

### 2b. Result correctness rate (separate; do not conflate with §2)

\[
\text{e2e\_result\_correctness\_rate} = \frac{\#\{\text{outcome}=\text{expect\_outcome}\}}{10}
\]

- Counts `correct_refuse` when that was expected.
- A run may show completion **90%** and correctness **100%** at once (9 succeeded + 1 expected refuse).

---

## 3. Schema pass rate (résumé target: ≥97%)

- **Event:** one `validate_json_artifact` call per expected JSON file among:
  - `research_plan.json`, `paper_evidence.json`, `repository_evidence.json`,
  - `evidence_review.json`, `sources.json`
- Pass = full Pydantic validation (types, required fields, enums), not “key exists”.
- Denominator = sum of expected schema events across offline + e2e tasks that expect those files.
- Tasks that must **not** emit artifacts: missing files are OK (not in denominator); unexpected full 9-pack is a task failure.
- Same file is not double-counted within one task.

---

## 4. Artifact completeness

When `expect_artifacts` is `nine` or an explicit list:

- All required files exist and parse.
- Schema events pass for JSON members.
- Content belongs to the current task (plan `task_id` / question linkage where available).
- `evidence_id` ↔ `source_url` traceability via `sources.json` / evidence collections.
- Failure / refuse tasks must not spuriously produce a complete nine-pack when `expect_artifacts` is `none` or `minimal`.

---

## 5. Offline pass rate

\[
\text{offline\_pass\_rate} = \frac{\#\{\text{outcome matches expect\_outcome}\}}{20}
\]

`correct_refuse` counts as pass **only** when that was the expected outcome for the task.

---

## 6. Golden Answer regression

Snapshot fields (per task): `outcome`, `status`, `artifact_count`, `schema_ok`, key `subtask_roles`, sandbox status / refuse flags.

- Compare is field-level diff.
- Update only via `--update-golden` (report marks the update).
- This is **not** the legacy synthetic golden scorer.
