"""ScholarFlow Chat LLM client backed by langchain_deepseek.ChatDeepSeek."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from scholarflow_api.llm.guards import safe_exc_message
from scholarflow_api.llm.settings import LlmSettings, get_llm_settings

logger = logging.getLogger("scholarflow_api.llm")


class LlmNotConfiguredError(RuntimeError):
    """Raised when DEEPSEEK_API_KEY is missing or empty."""


class LlmInvokeError(RuntimeError):
    """Raised when a real model call fails after retries."""


def build_chat_model(settings: LlmSettings | None = None) -> Any:
    """Construct ChatDeepSeek. Does not perform a network call."""
    cfg = settings or get_llm_settings()
    if not cfg.configured or cfg.api_key is None:
        raise LlmNotConfiguredError(
            "DEEPSEEK_API_KEY is not set; ScholarFlow chat LLM is unavailable"
        )
    try:
        from langchain_deepseek import ChatDeepSeek
    except ImportError as exc:  # pragma: no cover - env specific
        raise LlmNotConfiguredError(
            "langchain_deepseek is not installed in this Python environment"
        ) from exc

    # Prefer ChatDeepSeek (Phase 8.0). Do not pull ScholarFlow config.yaml.
    return ChatDeepSeek(
        model=cfg.model,
        api_key=cfg.api_key.get_secret_value(),
        api_base=cfg.base_url,
        temperature=cfg.temperature,
        max_retries=cfg.max_retries,
        request_timeout=cfg.timeout_seconds,
    )


@dataclass(frozen=True)
class LlmPingResult:
    ok: bool
    model: str
    base_url: str
    invocation: str
    tested_at: str
    response_preview: str | None
    error: str | None
    latency_ms: float | None

    def as_report_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "model": self.model,
            "base_url": self.base_url,
            "invocation": self.invocation,
            "tested_at": self.tested_at,
            "response_preview": self.response_preview,
            "error": self.error,
            "latency_ms": self.latency_ms,
            # Explicit: never include api_key
        }


class SfLlmClient:
    """Thin wrapper around ChatDeepSeek for ScholarFlow (Phase 8.0)."""

    def __init__(self, settings: LlmSettings | None = None) -> None:
        self.settings = settings or get_llm_settings()
        self._model = build_chat_model(self.settings)

    @property
    def model_id(self) -> str:
        return self.settings.model

    def invoke_text(self, prompt: str) -> str:
        """Synchronous text completion via LangChain invoke."""
        from langchain_core.messages import HumanMessage

        try:
            result = self._model.invoke([HumanMessage(content=prompt)])
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM invoke failed: %s", safe_exc_message(exc))
            raise LlmInvokeError(safe_exc_message(exc)) from exc
        content = getattr(result, "content", None)
        if content is None:
            return str(result)
        if isinstance(content, str):
            return content
        # Some providers return list content blocks
        return str(content)


def ping_llm(
    *,
    prompt: str = "Reply with exactly the word PONG and nothing else.",
    settings: LlmSettings | None = None,
) -> LlmPingResult:
    """Perform a real model request. Used for Phase 8.0 acceptance."""
    import time

    cfg = settings or get_llm_settings()
    tested_at = datetime.now(timezone.utc).isoformat()
    if not cfg.configured:
        return LlmPingResult(
            ok=False,
            model=cfg.model,
            base_url=cfg.base_url,
            invocation="ChatDeepSeek.invoke",
            tested_at=tested_at,
            response_preview=None,
            error="DEEPSEEK_API_KEY not configured",
            latency_ms=None,
        )
    try:
        client = SfLlmClient(cfg)
    except LlmNotConfiguredError as exc:
        return LlmPingResult(
            ok=False,
            model=cfg.model,
            base_url=cfg.base_url,
            invocation="ChatDeepSeek.invoke",
            tested_at=tested_at,
            response_preview=None,
            error=safe_exc_message(exc),
            latency_ms=None,
        )

    t0 = time.perf_counter()
    try:
        text = client.invoke_text(prompt)
        latency = (time.perf_counter() - t0) * 1000.0
        preview = text.strip().replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        logger.info(
            "LLM ping ok model=%s latency_ms=%.1f preview_len=%d",
            cfg.model,
            latency,
            len(preview),
        )
        return LlmPingResult(
            ok=True,
            model=cfg.model,
            base_url=cfg.base_url,
            invocation="langchain_deepseek.ChatDeepSeek.invoke",
            tested_at=tested_at,
            response_preview=preview,
            error=None,
            latency_ms=round(latency, 1),
        )
    except Exception as exc:  # noqa: BLE001
        latency = (time.perf_counter() - t0) * 1000.0
        err = safe_exc_message(exc)
        logger.error("LLM ping failed model=%s error=%s", cfg.model, err)
        return LlmPingResult(
            ok=False,
            model=cfg.model,
            base_url=cfg.base_url,
            invocation="langchain_deepseek.ChatDeepSeek.invoke",
            tested_at=tested_at,
            response_preview=None,
            error=err,
            latency_ms=round(latency, 1),
        )
