"""arXiv API client for ScholarFlow MCP."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx

from scholar_mcp.clients.resilience import is_rate_limited, with_retry

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
# Prefer HTTPS — HTTP endpoints often return 301 and break clients that do not follow redirects.
ARXIV_ENDPOINT = "https://export.arxiv.org/api/query"


def _normalize_arxiv_id(entry_id: str) -> str:
    if "/abs/" in entry_id:
        return entry_id.rsplit("/abs/", 1)[-1]
    return entry_id


def parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", NS):
        entry_id = entry.findtext("atom:id", default="", namespaces=NS)
        title = (entry.findtext("atom:title", default="", namespaces=NS) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=NS) or "").strip()
        authors = [
            author.findtext("atom:name", default="", namespaces=NS)
            for author in entry.findall("atom:author", NS)
        ]
        published = entry.findtext("atom:published", default="", namespaces=NS)
        year = int(published[:4]) if published and len(published) >= 4 else None
        arxiv_id = _normalize_arxiv_id(entry_id)
        papers.append(
            {
                "evidence_id": f"paper-{arxiv_id}",
                "title": title,
                "authors": [a for a in authors if a],
                "year": year,
                "identifier": arxiv_id,
                "source_url": f"https://arxiv.org/abs/{arxiv_id}",
                "abstract": summary,
                "research_problem": "",
                "methodology": "",
                "key_findings": [summary[:300]] if summary else [],
                "limitations": [],
                "datasets": [],
                "metrics": [],
                "evidence_level": "abstract_only",
                "verification_status": "verified",
            }
        )
    return papers


async def search_academic_papers(
    query: str,
    max_results: int = 10,
    category: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    max_results = max(1, min(max_results, 50))
    search_query = f"all:{query}"
    if category:
        search_query = f"cat:{category} AND {search_query}"
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_ENDPOINT}?{urlencode(params)}"
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def _fetch() -> list[dict[str, Any]]:
        response = await http.get(url)
        response.raise_for_status()
        return parse_arxiv_feed(response.text)

    try:
        if client is None:
            return await with_retry(_fetch)
        return await _fetch()
    except httpx.HTTPStatusError as exc:
        if is_rate_limited(exc):
            retry_after = exc.response.headers.get("Retry-After") if exc.response else None
            raise RuntimeError(
                f"arXiv HTTP 429 Too Many Requests (Retry-After={retry_after!r}) "
                f"for query={query!r}"
            ) from exc
        raise
    finally:
        if owns_client:
            await http.aclose()
