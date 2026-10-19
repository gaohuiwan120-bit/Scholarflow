# Scholar MCP

Standalone MCP server for ScholarFlow.

## Tools

- `search_academic_papers` — arXiv search
- `get_repository_overview` — GitHub repo metadata
- `extract_uploaded_paper` — read uploaded paper path
- `generate_research_matrix` — CSV matrices
- `validate_evidence_schema` — Pydantic validation
- `build_research_report` — markdown report
- `list_task_artifacts` — virtual output paths
- `assemble_task_artifacts` — all nine artifacts

## Run locally

```bash
uv run --directory extensions/scholar_mcp python -m scholar_mcp.server
```

Set `PYTHONPATH=backend/packages/harness` so shared schemas resolve.

## Tests

```bash
cd backend
$env:PYTHONPATH="backend/packages/harness;extensions/scholar_mcp"
uv run pytest extensions/scholar_mcp/tests/test_scholar_mcp.py -q
```
