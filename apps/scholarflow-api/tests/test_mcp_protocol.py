"""Phase-3 MCP Client ↔ Server protocol tests (stdio).

Offline by default: list tools + schema validation via MCP.
Live network tests are marked and skip when SCHOLARFLOW_LIVE_MCP!=1.
"""

from __future__ import annotations

import json
import os

import pytest

from scholarflow_api.mcp.client import ScholarMcpClient, ScholarMcpError, list_mcp_tools

EXPECTED_TOOLS = {
    "search_academic_papers",
    "get_repository_overview",
    "validate_evidence_schema",
    "assemble_task_artifacts",
    "build_research_report",
    "execute_sandbox_python",
}


def test_mcp_server_lists_expected_tools() -> None:
    tools = list_mcp_tools(timeout_seconds=60.0)
    names = set(tools)
    missing = EXPECTED_TOOLS - names
    assert not missing, f"MCP tools missing: {missing}; got={sorted(names)}"


def test_mcp_validate_schema_tool_offline() -> None:
    """Does not need arXiv/GitHub — pure local schema tool over MCP protocol."""
    payload = {
        "task_id": "sf-mcp-val",
        "title": "t",
        "objective": "o",
        "research_questions": ["q"],
        "search_queries": ["q"],
        "code_search_queries": [],
        "date_range": {"start": None, "end": None},
        "expected_outputs": [],
        "completion_criteria": [],
    }
    client = ScholarMcpClient(timeout_seconds=60.0)
    import asyncio

    result = asyncio.run(
        client.call_tool(
            "validate_evidence_schema",
            {
                "filename": "research_plan.json",
                "payload_json": json.dumps(payload),
            },
            max_attempts=2,
        )
    )
    assert isinstance(result, dict)
    assert result.get("valid") is True
    assert client.last_calls and client.last_calls[-1].ok


@pytest.mark.skipif(
    os.getenv("SCHOLARFLOW_LIVE_MCP") != "1",
    reason="Set SCHOLARFLOW_LIVE_MCP=1 to run live arXiv/GitHub MCP calls",
)
def test_mcp_live_arxiv_and_github() -> None:
    client = ScholarMcpClient(timeout_seconds=90.0)
    import asyncio

    papers = asyncio.run(
        client.call_tool(
            "search_academic_papers",
            {"query": "retrieval augmented generation", "max_results": 2},
            max_attempts=2,
        )
    )
    assert isinstance(papers, dict)
    items = papers.get("items") or []
    assert items
    assert any((p.get("source_url") or "").startswith("http") for p in items)

    repo = asyncio.run(
        client.call_tool(
            "get_repository_overview",
            {"repository": "langchain-ai/langchain"},
            max_attempts=2,
        )
    )
    assert isinstance(repo, dict)
    assert repo.get("source_url")
    assert repo.get("default_branch") or repo.get("key_modules")


def test_mcp_tool_error_is_explicit() -> None:
    client = ScholarMcpClient(timeout_seconds=45.0)
    import asyncio

    with pytest.raises(ScholarMcpError):
        asyncio.run(
            client.call_tool(
                "get_repository_overview",
                {"repository": "not-a-valid-repo-format"},
                max_attempts=1,
            )
        )
    assert client.last_calls
    assert client.last_calls[-1].ok is False
