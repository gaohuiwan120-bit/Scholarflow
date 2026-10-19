"""Data adapters: fixture samples vs live MCP protocol calls."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scholarflow_api.mcp.client import ScholarMcpClient, ScholarMcpError

logger = logging.getLogger("scholarflow_api.graph.adapters")


def load_fixture_papers(artifacts_dir: Path) -> list[dict[str, Any]]:
    path = artifacts_dir / "paper_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise FileNotFoundError(f"no paper items in {path}")
    return items


def load_fixture_repositories(artifacts_dir: Path) -> list[dict[str, Any]]:
    path = artifacts_dir / "repository_evidence.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or not items:
        raise FileNotFoundError(f"no repository items in {path}")
    return items


def _normalize_papers_from_mcp(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ScholarMcpError("MCP search_academic_papers did not return items list")
    now = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, Any]] = []
    for i, p in enumerate(items):
        if not isinstance(p, dict):
            continue
        url = (p.get("source_url") or "").strip()
        if not url:
            ident = p.get("identifier") or ""
            url = f"https://arxiv.org/abs/{ident}" if ident else ""
        if not url:
            raise ScholarMcpError(f"paper missing source_url at index {i}")
        # Prefer bare arXiv abs URL; never store Markdown-wrapped links.
        from scholarflow_api.chat.paper_rank import sanitize_source_url

        url = sanitize_source_url(url) or url
        abstract = (p.get("abstract") or "").strip()
        out.append(
            {
                "evidence_id": p.get("evidence_id") or f"paper-live-{i}",
                "title": p.get("title") or "untitled",
                "authors": p.get("authors") or [],
                "year": p.get("year"),
                "venue": p.get("venue"),
                "identifier": p.get("identifier"),
                "source_url": url,
                "abstract": abstract,
                "research_problem": p.get("research_problem") or abstract,
                "methodology": p.get("methodology") or "",
                "datasets": p.get("datasets") or [],
                "metrics": p.get("metrics") or [],
                "key_findings": p.get("key_findings")
                or ([abstract[:300]] if abstract else []),
                "limitations": p.get("limitations") or [],
                "evidence_level": p.get("evidence_level") or "abstract_only",
                "verification_status": p.get("verification_status") or "verified",
                "fetched_at": p.get("fetched_at") or now,
            }
        )
    if not out:
        raise ScholarMcpError("MCP returned zero papers")
    return out


def _normalize_repo_from_mcp(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ScholarMcpError("MCP get_repository_overview did not return object")
    if payload.get("error"):
        raise ScholarMcpError(str(payload["error"]))
    url = (payload.get("source_url") or "").strip()
    repo = payload.get("repository") or ""
    if not url and repo:
        url = f"https://github.com/{repo}"
    if not url:
        raise ScholarMcpError("repository missing source_url")
    modules = payload.get("key_modules") or payload.get("root_listing") or []
    return {
        "evidence_id": payload.get("evidence_id") or f"repo-{str(repo).replace('/', '-')}",
        "repository": repo,
        "source_url": url,
        "description": payload.get("description") or "",
        "language": payload.get("language"),
        "framework": payload.get("framework") or [],
        "architecture_summary": payload.get("architecture_summary") or "",
        "key_modules": modules,
        "installation_summary": payload.get("installation_summary") or "",
        "reproducibility_notes": payload.get("reproducibility_notes") or [],
        "limitations": payload.get("limitations") or [],
        "default_branch": payload.get("default_branch"),
        "root_listing": payload.get("root_listing") or modules,
        "verification_status": payload.get("verification_status") or "verified",
        "fetched_at": payload.get("fetched_at")
        or datetime.now(timezone.utc).isoformat(),
        "stars": payload.get("stars"),
        "forks": payload.get("forks"),
    }


def fetch_papers_via_mcp(
    query: str,
    *,
    max_results: int = 3,
    client: ScholarMcpClient | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Call MCP tool search_academic_papers. Raises ScholarMcpError on failure."""
    mcp = client or ScholarMcpClient(timeout_seconds=90.0)
    import asyncio

    raw = asyncio.run(
        mcp.call_tool(
            "search_academic_papers",
            {"query": query, "max_results": max_results},
        )
    )
    papers = _normalize_papers_from_mcp(raw)
    calls = [c.__dict__ for c in mcp.last_calls]
    return papers, calls


def fetch_repo_via_mcp(
    repository: str,
    *,
    client: ScholarMcpClient | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not (repository or "").strip():
        raise ScholarMcpError("repository must be owner/name")
    mcp = client or ScholarMcpClient(timeout_seconds=90.0)
    import asyncio

    raw = asyncio.run(mcp.call_tool("get_repository_overview", {"repository": repository}))
    repo = _normalize_repo_from_mcp(raw)
    calls = [c.__dict__ for c in mcp.last_calls]
    return repo, calls


def search_github_repositories(query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
    """Direct GitHub search (same token rules as MCP client). Used to avoid hardcoding langchain.

    Needs ``scholar_mcp`` on ``sys.path`` (see ``ensure_scholar_mcp_on_path``). This path
    is intentional: candidate search runs in-process before MCP ``get_repository_overview``.
    """
    import asyncio

    from scholarflow_api.config import ensure_scholar_mcp_on_path

    ensure_scholar_mcp_on_path()
    from scholar_mcp.clients.github import search_repositories

    return asyncio.run(search_repositories(query=query, max_results=max_results))


def resolve_live_repository(
    question: str,
    *,
    client: ScholarMcpClient | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Pick a topic-related repo: explicit name → GitHub search → curated hint.

    Never defaults to langchain-ai/langchain for unrelated topics.
    """
    from scholarflow_api.graph.evidence_gate import (
        extract_repo_search_query,
        filter_relevant_repos,
        suggest_hardcoded_repo,
    )

    meta: dict[str, Any] = {"candidates": [], "selected": None, "method": None}
    calls: list[dict[str, Any]] = []

    hinted = suggest_hardcoded_repo(question)
    candidates: list[str] = []
    if hinted:
        candidates.append(hinted)
        meta["method"] = "topic_hint"

    # Always try search for better topical match.
    search_q = extract_repo_search_query(question)
    try:
        hits = search_github_repositories(search_q, max_results=5)
        meta["candidates"] = hits
        for h in hits:
            name = h.get("repository")
            if name and name not in candidates:
                candidates.append(str(name))
        if hits and meta.get("method") != "topic_hint":
            meta["method"] = "github_search"
        elif hits:
            meta["method"] = "topic_hint+github_search"
    except Exception as exc:  # noqa: BLE001
        meta["search_error"] = str(exc)

    if not candidates:
        raise ScholarMcpError(
            f"No topic-matched GitHub repository for query={search_q!r}. "
            "Specify owner/name in the question or retry when GitHub search is available."
        )

    last_err: Exception | None = None
    for name in candidates[:5]:
        try:
            repo, c = fetch_repo_via_mcp(name, client=client)
            calls.extend(c)
            accepted, rejected = filter_relevant_repos(question, [repo])
            if accepted:
                meta["selected"] = name
                meta["rejected_preview"] = [
                    {
                        "repository": r.get("repository"),
                        "signals": r.get("relevance_signals"),
                    }
                    for r in rejected
                ]
                return accepted[0], calls, meta
            last_err = ScholarMcpError(
                f"repository {name} failed topic relevance for the question"
            )
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue

    raise ScholarMcpError(
        f"No relevant repository after search/hints. last_error={last_err}"
    )


def validate_schema_via_mcp(filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    mcp = ScholarMcpClient(timeout_seconds=60.0)
    return asyncio.run(
        mcp.call_tool(
            "validate_evidence_schema",
            {"filename": filename, "payload_json": json.dumps(payload, ensure_ascii=False)},
        )
    )


def assemble_via_mcp(
    plan: dict[str, Any],
    papers: list[dict[str, Any]],
    repos: list[dict[str, Any]],
    experiment: dict[str, Any],
    reviews: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Call MCP assemble_task_artifacts; return (payload, call records)."""
    import asyncio

    # ExperimentPlan fields only
    exp_keys = {
        "objective",
        "hypotheses",
        "datasets",
        "baselines",
        "proposed_pipeline",
        "evaluation_metrics",
        "ablation_studies",
        "resource_requirements",
        "implementation_steps",
        "risks",
    }
    exp = {k: v for k, v in experiment.items() if k in exp_keys}
    # Strip plan extras that ResearchPlan schema rejects if configured strictly
    plan_clean = {
        k: v
        for k, v in plan.items()
        if k
        in {
            "task_id",
            "title",
            "objective",
            "research_questions",
            "search_queries",
            "code_search_queries",
            "date_range",
            "expected_outputs",
            "completion_criteria",
        }
    }
    mcp = ScholarMcpClient(timeout_seconds=90.0)
    raw = asyncio.run(
        mcp.call_tool(
            "assemble_task_artifacts",
            {
                "research_plan_json": json.dumps(plan_clean, ensure_ascii=False),
                "paper_evidence_json": json.dumps({"items": papers}, ensure_ascii=False),
                "repository_evidence_json": json.dumps({"items": repos}, ensure_ascii=False),
                "experiment_plan_json": json.dumps(exp, ensure_ascii=False),
                "evidence_review_json": json.dumps({"items": reviews}, ensure_ascii=False),
            },
        )
    )
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict) or "contents" not in raw:
        raise ScholarMcpError("assemble_task_artifacts missing contents")
    return raw, [c.__dict__ for c in mcp.last_calls]
