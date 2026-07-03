"""LLM reachability probe for the scheduled daily job search.

"Is the LLM running?" is answered by whether the configured OpenAI-compatible
endpoint responds to ``GET {base_url}/models``. ``base_url`` is read from
``config/llm_endpoint_config.json`` (see ``utils/backend/llm/config.py``), so
this automatically follows whatever endpoint the app is configured to use
(currently ``http://localhost:9090/v1``, served by ``llamacpp-router.service``).
"""

from __future__ import annotations

import requests
from loguru import logger

from ..llm.config import load_llm_endpoint_config

# A boot-time reachability probe should be snappy, not the full inference timeout.
_MAX_PROBE_TIMEOUT = 10.0


def _models_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


def check_llm_ready(timeout: float | None = None) -> bool:
    """Return True if the configured LLM endpoint answers ``GET /models`` with HTTP 2xx.

    Any connection error, timeout, missing ``base_url``, or non-2xx response is
    treated as "the LLM is not running" (returns False) rather than raising.
    """
    config = load_llm_endpoint_config()
    base_url = str(config.get("base_url") or "").strip()
    if not base_url:
        logger.warning("LLM endpoint base_url is not configured; treating LLM as unavailable.")
        return False

    if timeout is None:
        try:
            timeout = float(config.get("timeout", _MAX_PROBE_TIMEOUT))
        except (TypeError, ValueError):
            timeout = _MAX_PROBE_TIMEOUT
        timeout = min(timeout, _MAX_PROBE_TIMEOUT)

    url = _models_url(base_url)
    headers = {}
    api_key = str(config.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        logger.info(f"LLM not reachable at {url}: {e}")
        return False

    if resp.ok:
        return True
    logger.info(f"LLM endpoint {url} returned HTTP {resp.status_code}; treating as unavailable.")
    return False
