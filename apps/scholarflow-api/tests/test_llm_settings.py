"""Unit tests for ScholarFlow LLM settings (no live network)."""

from __future__ import annotations

import os

from scholarflow_api.llm.guards import redact_secrets, safe_exc_message
from scholarflow_api.llm.settings import (
    get_llm_settings,
    load_root_env_into_process,
    reset_llm_settings_cache,
)


def test_redact_secrets_masks_sk_tokens() -> None:
    text = "failed auth sk-abcdefghijklmnopqrstuvwxyz123456"
    out = redact_secrets(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out
    assert "[REDACTED]" in out


def test_safe_exc_message_redacts() -> None:
    msg = safe_exc_message(RuntimeError("api_key=sk-secretvaluehere123"))
    assert "sk-secretvaluehere123" not in msg


def test_get_llm_settings_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-unit-test-key-not-real")
    monkeypatch.setenv("SCHOLARFLOW_LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("SCHOLARFLOW_LLM_BASE_URL", "https://api.deepseek.com")
    reset_llm_settings_cache()
    cfg = get_llm_settings()
    assert cfg.configured is True
    assert cfg.model == "deepseek-chat"
    assert cfg.base_url == "https://api.deepseek.com"
    # SecretStr must not appear in repr dumps casually as plain child of model_dump
    dumped = cfg.model_dump()
    assert "sk-unit-test-key-not-real" not in str(dumped)
    reset_llm_settings_cache()


def test_load_root_env_does_not_log_values() -> None:
    # Smoke: function returns key names only
    names = load_root_env_into_process(overwrite=False)
    assert isinstance(names, list)
    for n in names:
        assert n.isidentifier() or "_" in n
        assert not n.startswith("sk-")


def test_health_exposes_llm_flags_without_key() -> None:
    from fastapi.testclient import TestClient

    from scholarflow_api.app import app

    reset_llm_settings_cache()
    client = TestClient(app)
    data = client.get("/health").json()
    assert "llm_configured" in data
    assert "llm_model" in data
    body = str(data)
    assert "sk-" not in body
    # If process already has key from root .env, configured may be true — that is fine.
    if data["llm_configured"]:
        assert data.get("llm_provider") == "deepseek"
        assert data.get("llm_model")


def test_unconfigured_when_key_empty(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    # Ensure empty overrides any prior value for this test
    os.environ["DEEPSEEK_API_KEY"] = ""
    reset_llm_settings_cache()
    # Force re-read without loading from file overwriting empty — temporarily
    # block file load by clearing key after load
    from scholarflow_api.llm import settings as settings_mod

    settings_mod.get_llm_settings.cache_clear()
    monkeypatch.setattr(
        settings_mod,
        "load_root_env_into_process",
        lambda overwrite=False: [],
    )
    cfg = settings_mod.get_llm_settings()
    assert cfg.configured is False
    reset_llm_settings_cache()
