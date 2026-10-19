"""GitHub client: invalid token must not block public API access."""

from __future__ import annotations

import httpx
import pytest

from scholar_mcp.clients.github import get_repository_overview, search_repositories


@pytest.mark.asyncio
async def test_search_retries_unauthenticated_after_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from scholar_mcp.clients import github as gh

    monkeypatch.setattr(gh, "_rejected_token_fingerprints", set())
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization")
        calls.append(auth)
        if auth:
            return httpx.Response(401, json={"message": "Bad credentials"})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "jianzhangcs/ISTA-Net-PyTorch",
                        "html_url": "https://github.com/jianzhangcs/ISTA-Net-PyTorch",
                        "description": "ISTA-Net image compressive sensing",
                        "stargazers_count": 100,
                        "language": "Python",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    bad = "invalid-not-a-real-token-xxxxx"
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        hits = await search_repositories(
            "image compressive sensing",
            max_results=3,
            token=bad,
            client=client,
        )
        # Second call must not re-send the rejected token (avoids burning unauth quota).
        hits2 = await search_repositories(
            "image compressive sensing",
            max_results=3,
            token=bad,
            client=client,
        )
    assert len(calls) == 3  # auth+unauth, then unauth-only
    assert calls[0] and calls[0].startswith("Bearer ")
    assert calls[1] is None
    assert calls[2] is None
    assert hits and hits[0]["repository"] == "jianzhangcs/ISTA-Net-PyTorch"
    assert hits2 and hits2[0]["repository"] == "jianzhangcs/ISTA-Net-PyTorch"


@pytest.mark.asyncio
async def test_overview_retries_unauthenticated_after_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from scholar_mcp.clients import github as gh

    monkeypatch.setattr(gh, "_rejected_token_fingerprints", set())
    repo = "jianzhangcs/ISTA-Net-PyTorch"
    seen_repo_auth: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        auth = request.headers.get("Authorization")
        if path == f"/repos/{repo}":
            seen_repo_auth.append(bool(auth))
            if auth:
                return httpx.Response(401, json={"message": "Bad credentials"})
            return httpx.Response(
                200,
                json={
                    "full_name": repo,
                    "html_url": f"https://github.com/{repo}",
                    "description": "ISTA-Net: Image Compressive Sensing",
                    "language": "Python",
                    "default_branch": "master",
                    "stargazers_count": 100,
                    "forks_count": 10,
                },
            )
        if path.endswith("/readme"):
            return httpx.Response(404)
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Python": 1000})
        if "/contents" in path:
            return httpx.Response(
                200,
                json=[
                    {"name": "models", "type": "dir"},
                    {"name": "train.py", "type": "file"},
                ],
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        ov = await get_repository_overview(
            repo, token="invalid-not-a-real-token-xxxxx", client=client
        )
    assert seen_repo_auth == [True, False]
    assert ov["repository"] == repo
    assert "Compressive Sensing" in (ov.get("description") or "")


@pytest.mark.asyncio
async def test_live_invalid_env_token_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration-lite: bad env token + real public API (skipped if offline/rate-limited)."""
    from scholar_mcp.clients import github as gh

    monkeypatch.setattr(gh, "_rejected_token_fingerprints", set())
    monkeypatch.setenv("GITHUB_TOKEN", "invalid-not-a-real-token-xxxxx")
    try:
        ov = await get_repository_overview("jianzhangcs/ISTA-Net-PyTorch")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "connect" in msg or "timeout" in msg or "network" in msg:
            pytest.skip(f"network unavailable: {exc}")
        if "rate_limit" in msg or "rate limit" in msg or "403" in msg:
            pytest.skip(f"GitHub rate limited: {exc}")
        raise
    assert ov["repository"] == "jianzhangcs/ISTA-Net-PyTorch"
    desc = (ov.get("description") or "").lower()
    assert "compressive sensing" in desc or "compressed sensing" in desc
