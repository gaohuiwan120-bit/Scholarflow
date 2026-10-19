"""LLM settings for ScholarFlow API — env / root .env only; env / root .env only."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr

from scholarflow_api.config import repo_root

# Keys this module may pull from repo-root ``.env`` when missing in ``os.environ``.
_ALLOWED_ENV_KEYS = frozenset(
    {
        "DEEPSEEK_API_KEY",
        "SCHOLARFLOW_LLM_MODEL",
        "SCHOLARFLOW_LLM_BASE_URL",
        "SCHOLARFLOW_LLM_TIMEOUT",
        "SCHOLARFLOW_LLM_MAX_RETRIES",
        "SCHOLARFLOW_LLM_TEMPERATURE",
        "SCHOLARFLOW_CHAT_MAX_TOOL_ITERS",
        "SCHOLARFLOW_ARTIFACTS_DIR",
        "SCHOLARFLOW_TASKS_DIR",
        "SCHOLARFLOW_CONVERSATIONS_DIR",
        "SCHOLARFLOW_TASK_TIMEOUT",
        "SCHOLARFLOW_API_PORT",
    }
)

DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def _parse_dotenv_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    name, _, raw = s.partition("=")
    name = name.strip()
    if not name or name not in _ALLOWED_ENV_KEYS:
        return None
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        val = val[1:-1]
    return name, val


def load_root_env_into_process(*, overwrite: bool = False) -> list[str]:
    """Load allowed keys from repo-root ``.env`` into ``os.environ``.

    Returns names that were newly set (never values). Does not modify ``.env``.
    """
    path = repo_root() / ".env"
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return loaded
    for line in text.splitlines():
        parsed = _parse_dotenv_line(line)
        if parsed is None:
            continue
        name, val = parsed
        if not overwrite and name in os.environ and os.environ[name].strip():
            continue
        if not val.strip():
            continue
        os.environ[name] = val
        loaded.append(name)
    return loaded


class LlmSettings(BaseModel):
    """Chat LLM configuration. API key is SecretStr and must never be logged."""

    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: SecretStr | None = None
    timeout_seconds: float = Field(default=60.0, ge=5.0, le=300.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tool_iters: int = Field(default=8, ge=1, le=32)

    @property
    def configured(self) -> bool:
        if self.api_key is None:
            return False
        return bool(self.api_key.get_secret_value().strip())


@lru_cache
def get_llm_settings() -> LlmSettings:
    load_root_env_into_process(overwrite=False)
    key_raw = os.getenv("DEEPSEEK_API_KEY", "").strip()
    kwargs: dict = {}
    if key_raw:
        kwargs["api_key"] = SecretStr(key_raw)
    model = os.getenv("SCHOLARFLOW_LLM_MODEL", "").strip()
    if model:
        kwargs["model"] = model
    base = os.getenv("SCHOLARFLOW_LLM_BASE_URL", "").strip()
    if base:
        kwargs["base_url"] = base
    timeout = os.getenv("SCHOLARFLOW_LLM_TIMEOUT", "").strip()
    if timeout:
        kwargs["timeout_seconds"] = float(timeout)
    retries = os.getenv("SCHOLARFLOW_LLM_MAX_RETRIES", "").strip()
    if retries:
        kwargs["max_retries"] = int(retries)
    temp = os.getenv("SCHOLARFLOW_LLM_TEMPERATURE", "").strip()
    if temp:
        kwargs["temperature"] = float(temp)
    iters = os.getenv("SCHOLARFLOW_CHAT_MAX_TOOL_ITERS", "").strip()
    if iters:
        kwargs["max_tool_iters"] = int(iters)
    return LlmSettings(**kwargs)


def llm_configured() -> bool:
    return get_llm_settings().configured


def reset_llm_settings_cache() -> None:
    """Test helper — clear cached settings after env changes."""
    get_llm_settings.cache_clear()
