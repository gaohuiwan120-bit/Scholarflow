"""python -m scholarflow_api"""

from __future__ import annotations

import logging

import uvicorn

from scholarflow_api.config import get_settings
from scholarflow_api.llm.settings import load_root_env_into_process

logger = logging.getLogger("scholarflow_api")


def main() -> None:
    # Load allowed keys from repo-root .env into process env (no values logged).
    loaded = load_root_env_into_process(overwrite=False)
    if loaded:
        logger.info("Loaded env keys from repo .env: %s", ",".join(sorted(loaded)))
    settings = get_settings()
    uvicorn.run(
        "scholarflow_api.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
