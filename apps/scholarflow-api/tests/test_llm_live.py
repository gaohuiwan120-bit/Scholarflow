"""Live DeepSeek integration test — skipped unless SCHOLARFLOW_LIVE_LLM=1."""

from __future__ import annotations

import os

import pytest

from scholarflow_api.llm.client import ping_llm
from scholarflow_api.llm.settings import get_llm_settings, load_root_env_into_process, reset_llm_settings_cache

pytestmark = pytest.mark.live_llm


def test_live_deepseek_ping() -> None:
    if os.getenv("SCHOLARFLOW_LIVE_LLM", "").strip() not in {"1", "true", "TRUE", "yes"}:
        pytest.skip("Set SCHOLARFLOW_LIVE_LLM=1 to run real DeepSeek ping")
    load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    cfg = get_llm_settings()
    if not cfg.configured:
        pytest.skip("DEEPSEEK_API_KEY not configured")
    result = ping_llm()
    assert result.ok, result.error
    assert result.response_preview
    assert result.model == cfg.model
    # Never leak key into assertion messages
    assert "sk-" not in (result.error or "")
