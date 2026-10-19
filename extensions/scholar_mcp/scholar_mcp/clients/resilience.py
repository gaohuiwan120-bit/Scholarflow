"""Retry and backoff helpers for external API clients."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cap Wait to avoid indefinite stalls when Retry-After is huge or missing.
_MAX_RETRY_AFTER_SECONDS = 30.0
_DEFAULT_429_DELAY_SECONDS = 5.0


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Return delay for HTTP 429; None if not a rate-limit response."""
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    if exc.response is None or exc.response.status_code != 429:
        return None
    raw = exc.response.headers.get("Retry-After") or exc.response.headers.get("retry-after")
    if raw is None:
        return _DEFAULT_429_DELAY_SECONDS
    try:
        # Prefer integer seconds; ignore HTTP-date form for simplicity.
        return float(str(raw).strip())
    except ValueError:
        return _DEFAULT_429_DELAY_SECONDS


def is_rate_limited(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return exc.response.status_code == 429
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay_seconds: float = 0.5,
    retry_on: tuple[type[Exception], ...] = (httpx.HTTPError, TimeoutError),
    max_retry_after_seconds: float = _MAX_RETRY_AFTER_SECONDS,
) -> T:
    """Bounded exponential backoff; HTTP 429 respects Retry-After (capped)."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except retry_on as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            ra = _retry_after_seconds(exc)
            if ra is not None:
                delay = min(max(ra, 0.0), max_retry_after_seconds)
                logger.warning(
                    "HTTP 429 rate limited; sleeping %.1fs (Retry-After/cap) "
                    "before attempt %s/%s: %s",
                    delay,
                    attempt + 1,
                    max_attempts,
                    exc,
                )
            else:
                delay = base_delay_seconds * (2 ** (attempt - 1))
                logger.warning("Retry %s/%s after error: %s", attempt, max_attempts, exc)
            await asyncio.sleep(delay)
    assert last_error is not None
    raise last_error
