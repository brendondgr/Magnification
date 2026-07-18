"""
A thin OpenAI-compatible chat client over ``requests``.

Mirrors the request shape the bundled llama-server already speaks
(``POST {base_url}/chat/completions``) so the same client works against OpenAI,
vLLM, Ollama, or the local server. Supports single calls, JSON-structured output,
and parallel fan-out (``chat_many``) for scoring/keyword-generation workloads.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from .config import load_llm_endpoint_config


class LLMConfigError(RuntimeError):
    """Raised when the LLM endpoint is unconfigured or disabled."""


class OpenAIClient:
    """Minimal OpenAI-compatible chat client."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: int = 60,
        thinking_token_budget: int = 1024,
    ):
        if not base_url:
            raise LLMConfigError("LLM base_url is not configured.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.model = model or None
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        # Bounded reasoning: the model may think up to this many tokens, then must answer. Sent
        # top-level as ``thinking_token_budget``; the effective ``max_tokens`` is raised by this
        # amount so the answer still fits after thinking. 0 disables it (no param sent). Latched
        # off for the rest of this client's life if the endpoint rejects it (see _request_content).
        try:
            self.thinking_token_budget = max(0, int(thinking_token_budget or 0))
        except (TypeError, ValueError):
            self.thinking_token_budget = 0
        self._thinking_param_ok = True

    # ---- construction -------------------------------------------------

    @classmethod
    def from_config(cls, config: Optional[Dict[str, Any]] = None,
                    require_enabled: bool = True) -> "OpenAIClient":
        """Build a client from the saved endpoint config (or an override dict)."""
        cfg = dict(config) if config is not None else load_llm_endpoint_config()
        if require_enabled and not cfg.get("enabled"):
            raise LLMConfigError("LLM endpoint is disabled. Enable it in Options.")
        return cls(
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key"),
            model=cfg.get("model"),
            temperature=cfg.get("temperature", 0.2),
            max_tokens=cfg.get("max_tokens", 1024),
            timeout=cfg.get("timeout", 60),
            thinking_token_budget=cfg.get("thinking_token_budget", 1024),
        )

    # ---- low-level ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(self, messages: List[Dict[str, str]], **overrides) -> str:
        """
        Send a chat-completion request and return the assistant text content.

        Bounded reasoning: when a ``thinking_token_budget`` is set (and the endpoint supports it),
        the request carries that budget and raises ``max_tokens`` by it — so a reasoning model may
        think up to the budget and still have its full answer budget left. An empty response
        (reasoning still exhausted the budget) is retried once.
        """
        answer_max = overrides.get("max_tokens", self.max_tokens)
        budget = self.thinking_token_budget if self._thinking_param_ok else 0
        payload = {
            "model": overrides.get("model", self.model),
            "messages": messages,
            "temperature": overrides.get("temperature", self.temperature),
            "max_tokens": (answer_max + budget) if budget > 0 else answer_max,
            "stream": False,
        }
        if budget > 0:
            payload["thinking_token_budget"] = budget

        timeout = overrides.get("timeout", self.timeout)
        content, finish = self._request_content(payload, timeout, answer_max)
        # Reasoning models occasionally still burn the budget (finish_reason == "length")
        # and return nothing; a single retry recovers the common transient case.
        if content is None or not str(content).strip():
            content, finish = self._request_content(payload, timeout, answer_max)
        return content or ""

    def _request_content(self, payload: Dict[str, Any], timeout: int, answer_max: int):
        """
        POST one chat-completion and return ``(content, finish_reason)``.

        If the endpoint rejects the ``thinking_token_budget`` parameter (HTTP 400), drop it,
        restore ``max_tokens`` to the plain answer budget, remember not to send it again on this
        client, and retry once so a strict endpoint (e.g. hosted OpenAI) still works.
        """
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=timeout)
        if (getattr(resp, "status_code", 200) == 400
                and "thinking_token_budget" in payload):
            logger.warning("Endpoint rejected thinking_token_budget; retrying without it.")
            self._thinking_param_ok = False
            payload = {k: v for k, v in payload.items() if k != "thinking_token_budget"}
            payload["max_tokens"] = answer_max
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        try:
            choice = data["choices"][0]
            return choice["message"]["content"], choice.get("finish_reason")
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected chat-completion response shape: {e}") from e

    def chat_json(self, messages: List[Dict[str, str]], **overrides) -> Any:
        """Send a chat request and parse the response as JSON (tolerant of fences)."""
        text = self.chat(messages, **overrides)
        return _extract_json(text)

    def chat_many(self, message_lists: List[List[Dict[str, str]]],
                  max_workers: int = 4, as_json: bool = False, **overrides) -> List[Any]:
        """
        Run several chat requests in parallel, preserving input order.

        Failed/unparsable calls resolve to ``None`` so a single bad item does not
        sink the whole batch.
        """
        if not message_lists:
            return []
        method = self.chat_json if as_json else self.chat
        workers = max(1, min(max_workers, len(message_lists)))

        def _one(msgs):
            try:
                return method(msgs, **overrides)
            except Exception as e:  # pragma: no cover - exercised via monkeypatch
                logger.warning(f"chat_many item failed: {e}")
                return None

        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_one, message_lists))

    def test_connection(self) -> Dict[str, Any]:
        """Probe the endpoint with a tiny chat request. Never raises."""
        try:
            content = self.chat(
                [{"role": "user", "content": "Reply with the single word: ok"}],
                max_tokens=8,
            )
            return {"ok": True, "model": self.model, "sample": content.strip()[:120]}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def _extract_json(text: str) -> Any:
    """Parse JSON from model output, tolerating ```json fences and prose."""
    if text is None:
        raise ValueError("Empty model response")
    cleaned = text.strip()
    # Strip a leading/trailing markdown code fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} or [...] span.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        end = cleaned.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from model response: {text[:200]!r}")
