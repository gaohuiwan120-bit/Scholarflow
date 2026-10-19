"""MCP server exposing ScholarFlow research tools."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Allow importing scholarflow.scholar when PYTHONPATH includes backend/packages/harness
_HARNESS = Path(__file__).resolve().parents[3] / "backend" / "packages" / "harness"
if _HARNESS.exists() and str(_HARNESS) not in sys.path:
    sys.path.insert(0, str(_HARNESS))

from scholarflow.scholar.artifacts import build_task_artifacts, list_task_artifact_paths, summarize_artifacts
from scholarflow.scholar.matrix import generate_paper_matrix, generate_repository_matrix
from scholarflow.scholar.models import (
    ExperimentPlan,
    PaperEvidence,
    RepositoryEvidence,
    ResearchPlan,
    ReviewFinding,
)
from scholarflow.scholar.report import build_research_report
from scholarflow.scholar.validation import validate_json_artifact

from scholar_mcp.clients.arxiv import search_academic_papers as arxiv_search
from scholar_mcp.clients.github import get_repository_overview as github_overview

mcp = FastMCP("scholar_mcp")


def _parse_json_maybe(raw: str | dict | list) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


def coerce_items(payload: Any) -> list[dict[str, Any]]:
    """Accept list, {items:[...]}, or a single evidence object."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        # Single evidence object
        if any(key in payload for key in ("evidence_id", "title", "repository", "source_url")):
            return [payload]
    return []


def _slug(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip())[:80].strip("-")
    return cleaned or fallback


def normalize_paper_item(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    data = dict(item)
    evidence_id = str(data.get("evidence_id") or "").strip()
    if not evidence_id:
        identifier = str(data.get("identifier") or "").strip()
        title = str(data.get("title") or f"paper-{index + 1}")
        evidence_id = f"paper-{_slug(identifier or title, f'p{index + 1}')}"
    data["evidence_id"] = evidence_id
    if not str(data.get("source_url") or "").strip():
        identifier = str(data.get("identifier") or "").strip()
        data["source_url"] = f"https://arxiv.org/abs/{identifier}" if identifier else f"https://example.invalid/{evidence_id}"
    # Drop unknown helper fields that confuse agents but keep via model ignore
    return data


def normalize_repo_item(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    data = dict(item)
    evidence_id = str(data.get("evidence_id") or "").strip()
    repository = str(data.get("repository") or data.get("title") or f"repo-{index + 1}")
    if not evidence_id:
        evidence_id = f"repo-{_slug(repository.replace('/', '-'), f'r{index + 1}')}"
    data["evidence_id"] = evidence_id
    data["repository"] = repository
    if not str(data.get("source_url") or "").strip():
        data["source_url"] = f"https://github.com/{repository}" if "/" in repository else f"https://github.com/unknown/{evidence_id}"
    return data


def parse_papers(payload: Any) -> list[PaperEvidence]:
    items = coerce_items(payload)
    return [PaperEvidence.model_validate(normalize_paper_item(item, i)) for i, item in enumerate(items)]


def parse_repos(payload: Any) -> list[RepositoryEvidence]:
    items = coerce_items(payload)
    return [RepositoryEvidence.model_validate(normalize_repo_item(item, i)) for i, item in enumerate(items)]


def parse_reviews(payload: Any) -> list[ReviewFinding]:
    items = coerce_items(payload)
    return [ReviewFinding.model_validate(item) for item in items]


@mcp.tool()
async def search_academic_papers(query: str, max_results: int = 10, category: str | None = None) -> str:
    """Search arXiv for academic papers matching a query."""
    papers = await arxiv_search(query=query, max_results=max_results, category=category)
    return json.dumps({"items": papers}, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_repository_overview(repository: str) -> str:
    """Fetch GitHub repository metadata and README summary for owner/name."""
    overview = await github_overview(repository=repository)
    return json.dumps(overview, ensure_ascii=False, indent=2)


@mcp.tool()
def extract_uploaded_paper(file_path: str, title: str | None = None) -> str:
    """Extract basic metadata from an uploaded paper file path inside the sandbox."""
    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": f"file not found: {file_path}"})
    content_preview = path.read_text(encoding="utf-8", errors="replace")[:4000]
    inferred_title = title or path.stem.replace("_", " ")
    payload = {
        "evidence_id": f"upload-{path.stem}",
        "title": inferred_title,
        "source_url": f"file://{path.as_posix()}",
        "research_problem": "",
        "methodology": "",
        "key_findings": [],
        "limitations": [],
        "evidence_level": "full_text" if path.suffix.lower() in {".txt", ".md"} else "metadata_only",
        "verification_status": "partially_verified",
        "content_preview": content_preview,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def generate_research_matrix(kind: str, items_json: str) -> str:
    """Generate paper_matrix.csv or repository_matrix.csv from JSON items.

    Accepts either a JSON list, ``{\"items\": [...]}``, or a single evidence object.
    """
    payload = _parse_json_maybe(items_json)
    if kind == "paper":
        return generate_paper_matrix(parse_papers(payload))
    if kind == "repository":
        return generate_repository_matrix(parse_repos(payload))
    raise ValueError("kind must be 'paper' or 'repository'")


@mcp.tool()
def validate_evidence_schema(filename: str, payload_json: str) -> str:
    """Validate a ScholarFlow JSON artifact against its Pydantic schema."""
    payload = _parse_json_maybe(payload_json)
    if filename == "paper_evidence.json":
        payload = {"items": [p.model_dump() for p in parse_papers(payload)]}
    elif filename == "repository_evidence.json":
        payload = {"items": [r.model_dump() for r in parse_repos(payload)]}
    elif filename == "evidence_review.json":
        payload = {"items": [r.model_dump() for r in parse_reviews(payload)]}
    validated = validate_json_artifact(filename, payload)
    return json.dumps({"valid": True, "filename": filename, "payload": validated}, ensure_ascii=False, indent=2)


@mcp.tool(name="build_research_report")
def build_research_report_tool(
    research_plan_json: str,
    paper_evidence_json: str,
    repository_evidence_json: str,
    experiment_plan_json: str,
    evidence_review_json: str = '{"items": []}',
) -> str:
    """Build research_report.md from structured ScholarFlow JSON inputs."""
    plan = ResearchPlan.model_validate(_parse_json_maybe(research_plan_json))
    papers = parse_papers(_parse_json_maybe(paper_evidence_json))
    repos = parse_repos(_parse_json_maybe(repository_evidence_json))
    experiment = ExperimentPlan.model_validate(_parse_json_maybe(experiment_plan_json))
    reviews = parse_reviews(_parse_json_maybe(evidence_review_json))
    return build_research_report(plan, papers, repos, experiment, reviews)


@mcp.tool()
def list_task_artifacts(task_id: str) -> str:
    """List expected virtual artifact paths for a ScholarFlow task."""
    paths = list_task_artifact_paths(task_id)
    return json.dumps({"task_id": task_id, "artifacts": paths}, ensure_ascii=False, indent=2)


@mcp.tool()
def assemble_task_artifacts(
    research_plan_json: str,
    paper_evidence_json: str,
    repository_evidence_json: str,
    experiment_plan_json: str,
    evidence_review_json: str = '{"items": []}',
) -> str:
    """Build all nine ScholarFlow artifacts as filename -> content map.

    Paper/repo JSON may be a raw list or ``{\"items\": [...]}``. Missing
    ``evidence_id`` fields are auto-filled from title/identifier/repository.
    """
    plan = ResearchPlan.model_validate(_parse_json_maybe(research_plan_json))
    papers = parse_papers(_parse_json_maybe(paper_evidence_json))
    repos = parse_repos(_parse_json_maybe(repository_evidence_json))
    experiment = ExperimentPlan.model_validate(_parse_json_maybe(experiment_plan_json))
    reviews = parse_reviews(_parse_json_maybe(evidence_review_json))
    artifacts = build_task_artifacts(plan, papers, repos, experiment, reviews)
    return json.dumps(summarize_artifacts(artifacts) | {"contents": artifacts}, ensure_ascii=False)


@mcp.tool()
def index_research_artifacts(artifacts_dir: str, task_id: str | None = None) -> str:
    """Index a ScholarFlow artifact directory into the hybrid RAG evidence store."""
    from scholarflow.scholar.rag import index_artifacts_dir

    result = index_artifacts_dir(artifacts_dir, task_id=task_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def rag_query(question: str, top_k: int = 5, verified_only: bool = True) -> str:
    """Hybrid RAG over indexed research evidence: Dense + BM25 + RRF + hybrid-score rerank.

    Returns an answer bound to evidence_id/source_url. If confidence is low,
    ``need_mcp_fallback`` is true and the caller should run arXiv/GitHub tools.
    """
    from scholarflow.scholar.rag import rag_answer

    result = rag_answer(question, top_k=top_k, verified_only=verified_only)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def execute_sandbox_python(
    task_id: str,
    code: str,
    timeout_seconds: float = 8.0,
    allow_network: bool = False,
    prefer_docker: bool = True,
) -> str:
    """Execute a short Python snippet in ScholarFlow controlled sandbox.

    Default: no network. Prefer Docker when available; otherwise process jail.
    Process jail is not production-grade isolation — do not run untrusted malware samples.
    """
    from scholarflow.scholar.sandbox import SandboxRequest, execute_sandbox

    result = execute_sandbox(
        SandboxRequest(
            task_id=task_id,
            code=code,
            timeout_seconds=timeout_seconds,
            allow_network=allow_network,
            prefer_docker=prefer_docker,
        )
    )
    return result.model_dump_json(indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
