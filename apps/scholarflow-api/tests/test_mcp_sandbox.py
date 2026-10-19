"""Real MCP stdio call to execute_sandbox_python (not a direct Python import of the tool)."""

from __future__ import annotations

import json

import pytest


def test_mcp_execute_sandbox_python_via_protocol(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_SANDBOX_ROOT", str(tmp_path / "mcp-sb"))
    from scholarflow_api.mcp.client import ScholarMcpClient, call_mcp_tool

    # Discovery over MCP protocol
    client = ScholarMcpClient(timeout_seconds=60.0)
    import asyncio

    tools = asyncio.run(client.list_tools())
    assert "execute_sandbox_python" in tools

    # Invocation over MCP protocol (stdio ClientSession.call_tool)
    raw = call_mcp_tool(
        "execute_sandbox_python",
        {
            "task_id": "mcp-sb-1",
            "code": "print('mcp-sandbox-ok')\n",
            # MCP stdio cold-start + nested process_jail needs headroom on Windows
            "timeout_seconds": 30.0,
            "allow_network": False,
            "prefer_docker": False,
        },
        timeout_seconds=120.0,
    )
    if isinstance(raw, str):
        payload = json.loads(raw)
    else:
        payload = raw
    assert payload.get("status") == "succeeded"
    assert "mcp-sandbox-ok" in (payload.get("stdout") or "")
    assert payload.get("backend") == "process_jail"
    # Ensure client recorded a real tool call
    # (call_mcp_tool creates a fresh client; re-check via second list is enough for protocol)


def test_mcp_sandbox_reject_via_protocol(tmp_path, monkeypatch):
    monkeypatch.setenv("SCHOLARFLOW_SANDBOX_ROOT", str(tmp_path / "mcp-sb2"))
    from scholarflow_api.mcp.client import call_mcp_tool

    raw = call_mcp_tool(
        "execute_sandbox_python",
        {
            "task_id": "mcp-sb-bad",
            "code": "import subprocess\nprint(1)\n",
            "prefer_docker": False,
        },
        timeout_seconds=90.0,
    )
    payload = json.loads(raw) if isinstance(raw, str) else raw
    assert payload.get("status") == "rejected"
    assert "denied_import" in (payload.get("error_summary") or "")
