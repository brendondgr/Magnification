"""
Runtime knobs for the recommendation pipeline (parallelism + analysis toggles +
score weights). Stored at ``config/runtime_config.json`` (gitignored) and editable
from the Options panel's Runtime tab.
"""

import json
import os
from typing import Any, Dict

from loguru import logger

from ..paths import get_project_root

# Shared root (same across the main checkout and every git worktree); see utils/backend/paths.py.
CONFIG_PATH = str(get_project_root() / "config" / "runtime_config.json")

# Reserve a couple of cores so the dev server stays responsive.
_CPU = os.cpu_count() or 4
_DEFAULT_WORKERS = max(1, _CPU - 2)

DEFAULT_RUNTIME_CONFIG: Dict[str, Any] = {
    # analysis toggles
    "enable_analysis": True,        # run RAG analysis after a scrape
    "enable_llm_rerank": True,      # LLM fit verdict on the top-N (no-ops without an endpoint)
    "enable_llm_skills": False,     # use the LLM (vs gazetteer) for skill extraction
    "enable_llm_compensation": True,  # LLM-extract pay from descriptions when not parsed
    # parallelism
    "embed_workers": _DEFAULT_WORKERS,
    "embed_batch_size": 32,
    "linkedin_workers": 1,          # LinkedIn desc fetch is forced serial (rate-limit); kept for reference
    "linkedin_delay": 0.5,          # seconds between requests (jittered) — eases rate-limiting
    "llm_workers": 4,
    # ranking
    "top_n_llm": 0,                 # optional LLM-fit cap: 0 = all jobs; N>0 = top-N (semantic+bm25) only
    "weights": {                    # must sum to 1.0; `llm` renormalized out when absent
        "semantic": 0.30,
        "bm25": 0.15,
        "keyword": 0.10,
        "skill": 0.05,
        "llm": 0.40,
    },
}

_ALLOWED_KEYS = tuple(DEFAULT_RUNTIME_CONFIG.keys())


def get_runtime_config() -> Dict[str, Any]:
    """Return the saved runtime config merged over defaults (weights deep-merged)."""
    config = json.loads(json.dumps(DEFAULT_RUNTIME_CONFIG))  # deep copy
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                for k in _ALLOWED_KEYS:
                    if k not in saved:
                        continue
                    if k == "weights" and isinstance(saved[k], dict):
                        config["weights"].update(saved[k])
                    else:
                        config[k] = saved[k]
        except Exception as e:  # pragma: no cover - corrupt file fallback
            logger.error(f"Error loading runtime config: {e}")
    return config


def save_runtime_config(data: Dict[str, Any]) -> bool:
    """Persist the runtime config (known keys only), merged over current values."""
    try:
        config = get_runtime_config()
        for k in _ALLOWED_KEYS:
            if k not in data:
                continue
            if k == "weights" and isinstance(data[k], dict):
                config["weights"].update(data[k])
            else:
                config[k] = data[k]
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving runtime config: {e}")
        return False
