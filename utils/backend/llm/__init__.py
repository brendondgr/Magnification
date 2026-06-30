"""
OpenAI-compatible LLM integration for the recommendation system.

All AI features (resume->profile building, skill extraction, job recommendation,
keyword generation) talk to a single user-configured OpenAI-compatible endpoint
(base_url + api_key + model). The endpoint can point at OpenAI, vLLM, Ollama, or
the bundled local llama-server.
"""

from .client import OpenAIClient, LLMConfigError
from .config import (
    load_llm_endpoint_config,
    save_llm_endpoint_config,
    DEFAULT_LLM_ENDPOINT,
)

__all__ = [
    "OpenAIClient",
    "LLMConfigError",
    "load_llm_endpoint_config",
    "save_llm_endpoint_config",
    "DEFAULT_LLM_ENDPOINT",
]
