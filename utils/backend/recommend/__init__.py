"""
RAG + LLM job recommendation system.

Embeds scraped job descriptions on retrieval with bge-small-en-v1.5 (CPU, parallel)
+ BM25, scores them against the active profile (semantic + lexical + keyword-group +
skill signals), and optionally layers an LLM verdict on the top candidates.
"""

from .runtime_config import (
    get_runtime_config,
    save_runtime_config,
    DEFAULT_RUNTIME_CONFIG,
)

__all__ = [
    "get_runtime_config",
    "save_runtime_config",
    "DEFAULT_RUNTIME_CONFIG",
]
