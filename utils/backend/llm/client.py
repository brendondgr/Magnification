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


_UNSET = object()

# Sent to suppress a reasoning model's hidden chain-of-thought (vLLM/Qwen/Gemma convention).
_NO_THINKING = {"enable_thinking": False}


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
        disable_thinking: bool = True,
    ):
        if not base_url:
            raise LLMConfigError("LLM base_url is not configured.")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or None
        self.model = model or None
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        # When True, ask the endpoint to skip "thinking" so it emits the answer instead of
        # exhausting max_tokens on reasoning. Flipped off for the rest of this client's life
        # if the endpoint rejects the parameter (see _request_content).
        self.disable_thinking = disable_thinking
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
            disable_thinking=cfg.get("disable_thinking", True),
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

        When ``disable_thinking`` is on (and the caller hasn't overridden
        ``chat_template_kwargs``), the request asks the endpoint to skip reasoning so it
        emits the answer directly — reasoning models otherwise spend the whole ``max_tokens``
        budget thinking and return empty/truncated content. An empty response is retried once.
        """
        payload = {
            "model": overrides.get("model", self.model),
            "messages": messages,
            "temperature": overrides.get("temperature", self.temperature),
            "max_tokens": overrides.get("max_tokens", self.max_tokens),
            "stream": False,
        }
        # Thinking suppression: a caller-supplied chat_template_kwargs wins (pass None to opt
        # out entirely); otherwise inject enable_thinking=False when configured + supported.
        ctk = overrides.get("chat_template_kwargs", _UNSET)
        if ctk is not _UNSET:
            if ctk is not None:
                payload["chat_template_kwargs"] = ctk
        elif self.disable_thinking and self._thinking_param_ok:
            payload["chat_template_kwargs"] = dict(_NO_THINKING)

        timeout = overrides.get("timeout", self.timeout)
        content, finish = self._request_content(payload, timeout)
        # Reasoning models occasionally still burn the budget (finish_reason == "length")
        # and return nothing; a single retry recovers the common transient case.
        if content is None or not str(content).strip():
            content, finish = self._request_content(payload, timeout)
        return content or ""

    def _request_content(self, payload: Dict[str, Any], timeout: int):
        """
        POST one chat-completion and return ``(content, finish_reason)``.

        If the endpoint rejects the ``chat_template_kwargs`` suppression hint (HTTP 400),
        drop it, remember not to send it again on this client, and retry once so a strict
        endpoint (e.g. hosted OpenAI) still works.
        """
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=timeout)
        if (getattr(resp, "status_code", 200) == 400
                and "chat_template_kwargs" in payload):
            logger.warning("Endpoint rejected chat_template_kwargs; retrying without thinking suppression.")
            self._thinking_param_ok = False
            payload = {k: v for k, v in payload.items() if k != "chat_template_kwargs"}
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
