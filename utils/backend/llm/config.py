"""
Load / save the OpenAI-compatible endpoint configuration.

Stored at ``config/llm_endpoint_config.json`` (gitignored). This is intentionally
separate from ``utils/LocalLLM/llm_config.json`` (the bundled llama-server model
manager): this file only describes *which endpoint to talk to*, so it can point at
a remote API or the local server interchangeably.
"""

import json
import os
from typing import Any, Dict

from loguru import logger

from ..paths import get_project_root

# Shared root (same across the main checkout and every git worktree); see utils/backend/paths.py.
CONFIG_PATH = str(get_project_root() / "config" / "llm_endpoint_config.json")

DEFAULT_LLM_ENDPOINT: Dict[str, Any] = {
    "enabled": False,
    # base_url should include the OpenAI version prefix, e.g. ".../v1".
    "base_url": "http://127.0.0.1:8080/v1",
    "api_key": "",
    "model": "",
    "temperature": 0.2,
    "max_tokens": 1024,
    "timeout": 60,
    # Bounded "thinking" for reasoning models (vLLM/Qwen/Gemma convention): the model may reason
    # up to this many tokens, then must emit the answer. Sent top-level on the request as
    # ``thinking_token_budget``; the client raises the effective ``max_tokens`` by this budget so
    # the answer still fits after the model finishes thinking (reasoning models otherwise spend the
    # whole ``max_tokens`` on thinking and return an empty ``content``). Minimum 1024; endpoints
    # that reject the parameter (e.g. hosted OpenAI) degrade gracefully. See
    # docs/plans/thinking-token-budget.md (supersedes the earlier disable_thinking mechanism).
    "thinking_token_budget": 1024,
}

# Keys the API is allowed to persist (ignore anything else a client posts).
_ALLOWED_KEYS = tuple(DEFAULT_LLM_ENDPOINT.keys())

# Thinking budget can be tuned up but not below this floor ("at least 1024").
MIN_THINKING_TOKEN_BUDGET = 1024


def _clamp_thinking_budget(value: Any) -> int:
    """Coerce a persisted thinking budget to an int ≥ MIN_THINKING_TOKEN_BUDGET."""
    try:
        return max(MIN_THINKING_TOKEN_BUDGET, int(value))
    except (TypeError, ValueError):
        return MIN_THINKING_TOKEN_BUDGET


def load_llm_endpoint_config() -> Dict[str, Any]:
    """Return the saved endpoint config merged over defaults."""
    config = dict(DEFAULT_LLM_ENDPOINT)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                config.update({k: saved[k] for k in _ALLOWED_KEYS if k in saved})
        except Exception as e:  # pragma: no cover - corrupt file fallback
            logger.error(f"Error loading LLM endpoint config: {e}")
    config["thinking_token_budget"] = _clamp_thinking_budget(config.get("thinking_token_budget"))
    return config


def save_llm_endpoint_config(data: Dict[str, Any]) -> bool:
    """Persist the endpoint config (only known keys), merged over the current values."""
    try:
        config = load_llm_endpoint_config()
        config.update({k: data[k] for k in _ALLOWED_KEYS if k in data})
        config["thinking_token_budget"] = _clamp_thinking_budget(config.get("thinking_token_budget"))
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving LLM endpoint config: {e}")
        return False
