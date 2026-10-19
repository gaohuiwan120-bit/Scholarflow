"""Paths and runtime settings for ScholarFlow API (Phase 1)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


def repo_root() -> Path:
    """apps/scholarflow-api/scholarflow_api/config.py -> repo root."""
    return Path(__file__).resolve().parents[3]


def ensure_harness_on_path() -> Path:
    """Make ``scholarflow.scholar`` importable without installing the pack editable."""
    harness = repo_root() / "backend" / "packages" / "harness"
    harness_str = str(harness)
    if harness_str not in sys.path:
        sys.path.insert(0, harness_str)
    return harness


def ensure_scholar_mcp_on_path() -> Path:
    """Make ``scholar_mcp`` importable for in-process GitHub search helpers.

    The MCP stdio subprocess already prepends ``extensions/scholar_mcp`` via
    ``ScholarMcpClient._server_env``. The API process itself historically only
    put ``apps/scholarflow-api`` + harness on ``PYTHONPATH``, so
    ``adapters.search_github_repositories`` failed with ``No module named
    'scholar_mcp'`` even while ``get_repository_overview`` over MCP succeeded.
    """
    # Prefer explicit env override (same key the start script may inject).
    override = (os.getenv("SCHOLAR_MCP_DIR") or "").strip()
    mcp_root = Path(override) if override else (repo_root() / "extensions" / "scholar_mcp")
    mcp_str = str(mcp_root.resolve())
    if mcp_str not in sys.path:
        sys.path.insert(0, mcp_str)
    return mcp_root


class Settings(BaseModel):
    """Application settings — env overrides only, no secrets required for RAG demo."""

    app_name: str = "ScholarFlow API"
    host: str = "127.0.0.1"
    port: int = 8100
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    default_artifacts_dir: Path = Field(
        default_factory=lambda: repo_root()
        / "docs"
        / "scholar-flow"
        / "samples"
        / "rag-test-001"
    )
    default_task_id_for_index: str = "rag-test-001"
    task_timeout_seconds: float = 180.0
    # Phase-1 runtime id — future LangGraph runtime will register under another name
    active_runtime: str = "rag_v1"


@lru_cache
def get_settings() -> Settings:
    ensure_harness_on_path()
    ensure_scholar_mcp_on_path()
    artifacts = os.getenv("SCHOLARFLOW_ARTIFACTS_DIR")
    timeout = os.getenv("SCHOLARFLOW_TASK_TIMEOUT")
    port = os.getenv("SCHOLARFLOW_API_PORT")
    kwargs: dict = {}
    if artifacts:
        kwargs["default_artifacts_dir"] = Path(artifacts)
    if timeout:
        kwargs["task_timeout_seconds"] = float(timeout)
    if port:
        kwargs["port"] = int(port)
    return Settings(**kwargs)
