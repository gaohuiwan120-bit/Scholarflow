# ScholarFlow

ScholarFlow extends [ScholarFlow](https://github.com/bytedance/scholarflow) into a multi-agent scientific and technical research platform.

## Quick start

1. Complete Phase 0 baseline (see `docs/scholar-flow/baseline.md`).
2. Copy and enable ScholarFlow MCP in `extensions_config.json` (see `extensions_config.example.json`).
3. Place custom skills under `skills/custom/` (already included in this repo).
4. Start Docker stack:

```bash
./scripts/docker.sh start
```

5. Configure LLM API keys in `.env` and `config.yaml`.

## Components

| Component | Path |
|-----------|------|
| Pydantic schemas | `backend/packages/harness/scholarflow/scholar/` |
| MCP server | `extensions/scholar_mcp/` |
| Orchestration skill | `skills/custom/scientific-research-orchestration/` |
| Paper skill | `skills/custom/paper-evidence-extraction/` |
| Repository skill | `skills/custom/repository-analysis/` |
| Experiment skill | `skills/custom/experiment-plan/` |
| Evaluation | `evaluation/` |
| Agent 开发说明 | `docs/scholar-flow/agent-guide.md` |
| Design docs | `docs/scholar-flow/design.md`, `data-contracts.md` |

## MCP registration

Add to `extensions_config.json`:

```json
"scholar_mcp": {
  "enabled": true,
  "type": "stdio",
  "command": "$SCHOLAR_MCP_PYTHON",
  "args": ["-m", "scholar_mcp.server"],
  "env": {
    "PYTHONPATH": "$SCHOLAR_PYTHONPATH",
    "GITHUB_TOKEN": "$GITHUB_TOKEN"
  },
  "tool_call_timeout": 120,
  "description": "ScholarFlow academic and repository research tools"
}
```

Docker Compose injects `SCHOLAR_MCP_PYTHON` and `SCHOLAR_PYTHONPATH` automatically. For host-native runs, set them in `.env` (see `.env.example`).

## Output contract

Each task writes nine files to `/mnt/user-data/outputs/<task-id>/`. See `docs/scholar-flow/data-contracts.md`.

Host path example (user-scoped sandbox):

`backend/.scholarflow/users/<user_id>/threads/<thread_id>/user-data/outputs/<task-id>/`

Real sample (schema-normalized): `docs/scholar-flow/samples/rag-test-001/`  
Score report: `evaluation/reports/e2e-rag-test-001.md` · Resume bullets: `docs/scholar-flow/resume-highlights.md`  
RAG demo: `docs/scholar-flow/rag.md` · `evaluation/run_rag_demo.py`

## Tests

```bash
cd backend && uv run pytest tests/test_scholar_schemas.py -q
cd extensions/scholar_mcp && uv run pytest -q
# Offline evaluation
cd backend
uv run python ../evaluation/run_eval.py

# E2E benchmark (golden demo)
uv run python ../evaluation/run_benchmark.py --mode golden

# Score real rag-test-001 artifacts (after normalize)
uv run python ../evaluation/normalize_and_score_e2e.py
```

## Trigger example

Ask ScholarFlow:

> Use scientific-research-orchestration to survey transformer efficiency techniques and related GitHub implementations. Task id: `transformer-efficiency-001`.
