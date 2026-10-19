#!/usr/bin/env python3
"""Phase 8.0: real DeepSeek ping for ScholarFlow LLM client.

Never prints or writes API key material. Writes a redacted evidence report.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "scholarflow-api"
HARNESS = ROOT / "backend" / "packages" / "harness"
for p in (API, HARNESS):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)


def main() -> int:
    from scholarflow_api.llm.client import ping_llm
    from scholarflow_api.llm.guards import redact_secrets
    from scholarflow_api.llm.settings import get_llm_settings, load_root_env_into_process, reset_llm_settings_cache

    loaded = load_root_env_into_process(overwrite=False)
    reset_llm_settings_cache()
    cfg = get_llm_settings()

    print("=== ScholarFlow LLM Phase 8.0 live verify ===")
    print(f"loaded_env_key_names={sorted(loaded)}")
    print(f"llm_configured={cfg.configured}")
    print(f"model={cfg.model}")
    print(f"base_url={cfg.base_url}")
    print(f"timeout_seconds={cfg.timeout_seconds}")
    print(f"max_retries={cfg.max_retries}")
    print("invocation=langchain_deepseek.ChatDeepSeek.invoke")

    result = ping_llm()
    payload = result.as_report_dict()
    # Belt-and-suspenders: redact anything that slipped into error text
    if payload.get("error"):
        payload["error"] = redact_secrets(str(payload["error"]))
    if payload.get("response_preview"):
        payload["response_preview"] = redact_secrets(str(payload["response_preview"]))

    print("--- result ---")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    report_path = ROOT / "docs" / "scholarflow-phase8-0.md"
    tested = payload.get("tested_at") or datetime.now(timezone.utc).isoformat()
    status = "PASS" if result.ok else "FAIL"
    lines = [
        "# ScholarFlow Phase 8.0 — LLM Client 验收记录",
        "",
        f"- **status**: {status}",
        f"- **tested_at (UTC)**: `{tested}`",
        f"- **model**: `{payload['model']}`",
        f"- **base_url**: `{payload['base_url']}`",
        f"- **invocation**: `{payload['invocation']}`",
        f"- **ok**: `{payload['ok']}`",
        f"- **latency_ms**: `{payload.get('latency_ms')}`",
        f"- **response_preview**: `{payload.get('response_preview')}`",
        f"- **error**: `{payload.get('error')}`",
        "",
        "## 约束核对",
        "",
        "- 使用 `langchain_deepseek.ChatDeepSeek`（未复制 ScholarFlow `config.yaml`）。",
        "- 密钥仅从进程环境 / 根目录 `.env` 的 `DEEPSEEK_API_KEY` 读取；本报告不含密钥明文。",
        "- 未启动 scholarflow Docker / Next.js 主站。",
        "- 未实现 8.1+ 会话/Agent/SSE。",
        "",
        "## 修改文件（8.0）",
        "",
        "- `apps/scholarflow-api/scholarflow_api/llm/*`",
        "- `apps/scholarflow-api/scholarflow_api/models.py`（health llm 字段）",
        "- `apps/scholarflow-api/scholarflow_api/app.py`",
        "- `apps/scholarflow-api/scholarflow_api/__main__.py`",
        "- `scripts/start_scholarflow_api.ps1`",
        "- `scripts/verify_scholarflow_llm.py`",
        "- `apps/scholarflow-api/tests/test_llm_settings.py`",
        "- `apps/scholarflow-api/tests/test_llm_live.py`",
        "",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote_report={report_path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
