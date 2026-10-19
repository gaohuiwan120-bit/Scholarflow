"""Tests for MCP client retry logic."""

from __future__ import annotations

import httpx
import pytest

from scholar_mcp.clients.resilience import is_rate_limited, with_retry


class FlakyError(Exception):
    pass


@pytest.mark.asyncio
async def test_with_retry_recovers_on_second_attempt() -> None:
    calls = {"count": 0}

    async def op() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            raise FlakyError("temporary")
        return "ok"

    result = await with_retry(op, max_attempts=3, base_delay_seconds=0.01, retry_on=(FlakyError,))
    assert result == "ok"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_with_retry_raises_after_max_attempts() -> None:
    async def op() -> str:
        raise FlakyError("always fails")

    with pytest.raises(FlakyError):
        await with_retry(op, max_attempts=2, base_delay_seconds=0.01, retry_on=(FlakyError,))


@pytest.mark.asyncio
async def test_with_retry_respects_retry_after_on_429() -> None:
    calls = {"count": 0}
    req = httpx.Request("GET", "https://export.arxiv.org/api/query")

    async def op() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            resp = httpx.Response(429, headers={"Retry-After": "0"}, request=req)
            raise httpx.HTTPStatusError("rate limited", request=req, response=resp)
        return "ok"

    result = await with_retry(op, max_attempts=3, base_delay_seconds=0.01)
    assert result == "ok"
    assert calls["count"] == 2


def test_is_rate_limited_detects_429_status() -> None:
    req = httpx.Request("GET", "https://example.com")
    resp = httpx.Response(429, request=req)
    exc = httpx.HTTPStatusError("too many", request=req, response=resp)
    assert is_rate_limited(exc)
    assert is_rate_limited(RuntimeError("arXiv HTTP 429 Too Many Requests"))
    assert not is_rate_limited(RuntimeError("connection reset"))
