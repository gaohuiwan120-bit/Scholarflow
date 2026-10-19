"""GitHub REST API client for ScholarFlow MCP."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx

from scholar_mcp.clients.resilience import with_retry

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# After a 401 with a configured token, skip Authorization for the rest of the
# process. Otherwise every public GET doubles traffic and burns the unauthenticated
# 60 req/h budget (observed: 401 then unauth 403 rate limit during live E2E).
_rejected_token_fingerprints: set[str] = set()


def _token_fingerprint(token: str) -> str:
    # Never store the raw token; length + edge chars are enough to key the cache.
    return f"{len(token)}:{token[:4]}:{token[-2:]}"


def _mark_token_rejected(token: str) -> None:
    _rejected_token_fingerprints.add(_token_fingerprint(token))


def _is_token_rejected(token: str) -> bool:
    return _token_fingerprint(token) in _rejected_token_fingerprints


def _resolve_token(token: str | None) -> str | None:
    value = (token or os.environ.get("GITHUB_TOKEN") or "").strip()
    if not value or value.startswith("your-") or value == "$GITHUB_TOKEN":
        return None
    # Common placeholder / truncated lengths (GitHub PATs are longer when valid).
    if value in {"x", "token", "changeme", "REPLACE_ME"}:
        return None
    if _is_token_rejected(value):
        return None
    return value


def _base_headers(*, include_auth: bool, token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "scholar-mcp/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if include_auth and token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _classify_github_http(status: int, body: str = "") -> str:
    if status == 401:
        return "http_401_unauthorized"
    if status == 403:
        low = (body or "").lower()
        if "rate limit" in low or "secondary rate" in low:
            return "http_403_rate_limit"
        return "http_403_forbidden"
    if status == 429:
        return "http_429"
    if status == 404:
        return "http_404"
    return f"http_{status}"


async def _get_with_auth_fallback(
    http: httpx.AsyncClient,
    url: str,
    *,
    token: str | None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    """GET with optional Bearer token; on 401 retry once without auth for public data.

    Never logs the token value. Invalid/expired GITHUB_TOKEN previously caused
    all live repo calls to fail even though public unauthenticated API worked.
    After the first 401, the token is remembered as rejected so later calls skip
    auth and do not double-spend the unauthenticated rate limit.
    """
    use_auth = bool(token) and not _is_token_rejected(token or "")
    resp = await http.get(
        url,
        params=params,
        headers=_base_headers(include_auth=use_auth, token=token if use_auth else None),
    )
    if resp.status_code == 401 and token and use_auth:
        _mark_token_rejected(token)
        logger.warning(
            "GitHub API HTTP 401 with configured token (token not logged); "
            "disabling token for this process and retrying unauthenticated for %s",
            url.split("?")[0],
        )
        resp = await http.get(
            url,
            params=params,
            headers=_base_headers(include_auth=False, token=None),
        )
    return resp


async def search_repositories(
    query: str,
    max_results: int = 5,
    token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Search public GitHub repositories. Returns lightweight hits (full_name, html_url, description)."""
    q = (query or "").strip()
    if not q:
        return []
    max_results = max(1, min(int(max_results), 10))
    resolved = _resolve_token(token)
    owns_client = client is None
    # Client without default Authorization — we set headers per request for 401 fallback.
    http = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def _fetch() -> list[dict[str, Any]]:
        resp = await _get_with_auth_fallback(
            http,
            f"{GITHUB_API}/search/repositories",
            token=resolved,
            params={"q": q, "sort": "stars", "order": "desc", "per_page": max_results},
        )
        if resp.status_code in {401, 403, 429}:
            kind = _classify_github_http(resp.status_code, resp.text)
            raise PermissionError(
                f"GitHub search {kind}. "
                "If using GITHUB_TOKEN, ensure it is a valid PAT (or unset invalid token). "
                "Unauthenticated core limit is 60/h; invalid tokens previously doubled spend. "
                f"body={resp.text[:200]}"
            )
        resp.raise_for_status()
        items = (resp.json() or {}).get("items") or []
        out: list[dict[str, Any]] = []
        for it in items:
            full = it.get("full_name") or ""
            if not full or full.count("/") != 1:
                continue
            out.append(
                {
                    "repository": full,
                    "source_url": it.get("html_url") or f"https://github.com/{full}",
                    "description": it.get("description") or "",
                    "stars": it.get("stargazers_count"),
                    "language": it.get("language"),
                }
            )
        return out

    try:
        if client is None:
            return await with_retry(_fetch)
        return await _fetch()
    finally:
        if owns_client:
            await http.aclose()


async def get_repository_overview(
    repository: str,
    token: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    repo = repository.strip().strip("/")
    if repo.count("/") != 1:
        raise ValueError("repository must be in owner/name format")
    resolved = _resolve_token(token)
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def _fetch() -> dict[str, Any]:
        repo_resp = await _get_with_auth_fallback(
            http, f"{GITHUB_API}/repos/{repo}", token=resolved
        )
        if repo_resp.status_code in {401, 403, 429}:
            kind = _classify_github_http(repo_resp.status_code, repo_resp.text)
            raise PermissionError(
                f"GitHub API {kind} for repos/{repo}. "
                "Unset invalid GITHUB_TOKEN or provide a valid PAT. "
                "If http_403_rate_limit: wait for X-RateLimit-Reset or use a valid token. "
                f"body={repo_resp.text[:300]}"
            )
        if repo_resp.status_code == 404:
            raise FileNotFoundError(f"GitHub repository not found: {repo}")
        repo_resp.raise_for_status()
        repo_data = repo_resp.json()
        readme_text = ""
        readme_resp = await _get_with_auth_fallback(
            http, f"{GITHUB_API}/repos/{repo}/readme", token=resolved
        )
        if readme_resp.status_code == 200:
            payload = readme_resp.json()
            readme_text = base64.b64decode(payload.get("content", "")).decode(
                "utf-8", errors="replace"
            )
        languages_resp = await _get_with_auth_fallback(
            http, f"{GITHUB_API}/repos/{repo}/languages", token=resolved
        )
        languages: dict[str, int] = (
            languages_resp.json() if languages_resp.status_code == 200 else {}
        )
        primary_language = repo_data.get("language")
        default_branch = repo_data.get("default_branch") or "main"
        root_entries: list[str] = []
        contents_resp = await _get_with_auth_fallback(
            http,
            f"{GITHUB_API}/repos/{repo}/contents/",
            token=resolved,
            params={"ref": default_branch},
        )
        if contents_resp.status_code == 200 and isinstance(contents_resp.json(), list):
            for item in contents_resp.json()[:40]:
                name = item.get("name")
                kind = item.get("type")
                if name:
                    root_entries.append(f"{name}/" if kind == "dir" else str(name))
        return {
            "evidence_id": f"repo-{repo.replace('/', '-')}",
            "repository": repo,
            "source_url": repo_data.get("html_url", f"https://github.com/{repo}"),
            "description": repo_data.get("description") or "",
            "language": primary_language,
            "framework": list(languages.keys())[:5],
            "architecture_summary": readme_text[:2000],
            "key_modules": root_entries,
            "installation_summary": "",
            "reproducibility_notes": [],
            "limitations": [],
            "default_branch": default_branch,
            "root_listing": root_entries,
            "stars": repo_data.get("stargazers_count"),
            "forks": repo_data.get("forks_count"),
            "verification_status": "verified",
            "fetched_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        }

    try:
        if client is None:
            return await with_retry(_fetch)
        return await _fetch()
    finally:
        if owns_client:
            await http.aclose()
