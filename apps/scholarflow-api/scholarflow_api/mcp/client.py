"""stdio MCP client that talks to extensions/scholar_mcp via the MCP protocol."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from scholarflow_api.config import repo_root

logger = logging.getLogger("scholarflow_api.mcp")


class ScholarMcpError(RuntimeError):
    """Raised when MCP protocol call fails (not a silent soft failure)."""


def _server_python() -> str:
    root = repo_root()
    candidates = [
        root / "extensions" / "scholar_mcp" / ".venv" / "Scripts" / "python.exe",
        root / "extensions" / "scholar_mcp" / ".venv" / "bin" / "python",
        root / "backend" / ".venv" / "Scripts" / "python.exe",
        root / "backend" / ".venv" / "bin" / "python",
        Path(sys.executable),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return sys.executable


def _server_env() -> dict[str, str]:
    root = repo_root()
    harness = root / "backend" / "packages" / "harness"
    mcp_pkg = root / "extensions" / "scholar_mcp"
    env = os.environ.copy()
    parts = [str(mcp_pkg), str(harness)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    env["PYTHONUNBUFFERED"] = "1"
    # Do not log tokens; just pass through if present for GitHub tool
    return env


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=_server_python(),
        args=["-m", "scholar_mcp.server"],
        env=_server_env(),
        cwd=str(repo_root() / "extensions" / "scholar_mcp"),
    )


def _content_to_text(result: Any) -> str:
    chunks: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
        elif isinstance(item, dict) and item.get("text"):
            chunks.append(str(item["text"]))
    if not chunks and getattr(result, "structuredContent", None):
        return json.dumps(result.structuredContent, ensure_ascii=False)
    return "\n".join(chunks)


@dataclass
class McpCallRecord:
    tool: str
    ok: bool
    duration_ms: int
    input_summary: dict[str, Any]
    error: str | None = None


class ScholarMcpClient:
    """One-shot or reusable stdio session to scholar_mcp FastMCP server."""

    def __init__(self, *, timeout_seconds: float = 60.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.last_calls: list[McpCallRecord] = []

    async def list_tools(self) -> list[str]:
        params = _server_params()

        async def _run() -> list[str]:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    return [t.name for t in listed.tools]

        return await asyncio.wait_for(_run(), timeout=self.timeout_seconds)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        max_attempts: int = 3,
    ) -> Any:
        arguments = arguments or {}
        # Redact secrets from logged summary
        safe_args = {
            k: ("***" if "token" in k.lower() or "key" in k.lower() else v)
            for k, v in arguments.items()
        }
        started = time.perf_counter()
        params = _server_params()
        last_exc: Exception | None = None

        async def _run() -> Any:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    if getattr(result, "isError", False):
                        raise ScholarMcpError(_content_to_text(result) or f"MCP tool error: {name}")
                    text = _content_to_text(result)
                    if not text:
                        raise ScholarMcpError(f"MCP tool {name} returned empty content")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text

        for attempt in range(1, max(1, max_attempts) + 1):
            try:
                payload = await asyncio.wait_for(_run(), timeout=self.timeout_seconds)
                self.last_calls.append(
                    McpCallRecord(
                        tool=name,
                        ok=True,
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        input_summary={**safe_args, "_attempts": attempt},
                    )
                )
                logger.info(
                    "mcp_call tool=%s ok attempt=%s duration_ms=%s",
                    name,
                    attempt,
                    self.last_calls[-1].duration_ms,
                )
                return payload
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "mcp_call tool=%s attempt=%s/%s failed: %s",
                    name,
                    attempt,
                    max_attempts,
                    exc,
                )
                # Do not amplify arXiv/GitHub rate limits with another outer retry loop.
                err_l = str(exc).lower()
                if "429" in err_l or "too many requests" in err_l or "rate limit" in err_l:
                    logger.warning(
                        "mcp_call tool=%s stopping outer retries after rate-limit signal",
                        name,
                    )
                    break
                if attempt < max_attempts:
                    await asyncio.sleep(min(1.5 * attempt, 4.0))

        self.last_calls.append(
            McpCallRecord(
                tool=name,
                ok=False,
                duration_ms=int((time.perf_counter() - started) * 1000),
                input_summary={**safe_args, "_attempts": max_attempts},
                error=f"{type(last_exc).__name__}: {last_exc}",
            )
        )
        logger.error("mcp_call tool=%s failed after retries: %s", name, last_exc)
        raise ScholarMcpError(f"{name} failed: {last_exc}") from last_exc


def list_mcp_tools(*, timeout_seconds: float = 60.0) -> list[str]:
    return asyncio.run(ScholarMcpClient(timeout_seconds=timeout_seconds).list_tools())


def call_mcp_tool(name: str, arguments: dict[str, Any] | None = None, *, timeout_seconds: float = 60.0) -> Any:
    return asyncio.run(ScholarMcpClient(timeout_seconds=timeout_seconds).call_tool(name, arguments))
