"""
Unit tests for the OpenAI-compatible client. No network: ``requests.post`` is
monkeypatched so we assert the request shape and exercise parsing/parallel paths.
"""

import pytest

from utils.backend.llm import client as llm_client
from utils.backend.llm.client import OpenAIClient, LLMConfigError, _extract_json


class _FakeResp:
    def __init__(self, content="ok", status_code=200, finish_reason="stop"):
        self._content = content
        self.status_code = status_code
        self._finish = finish_reason

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"choices": [{"message": {"content": self._content},
                             "finish_reason": self._finish}]}


def test_chat_builds_openai_payload(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return _FakeResp("hello there")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)

    c = OpenAIClient(base_url="http://x/v1/", api_key="secret", model="m1", temperature=0.3)
    out = c.chat([{"role": "user", "content": "hi"}])

    assert out == "hello there"
    assert captured["url"] == "http://x/v1/chat/completions"  # trailing slash trimmed
    assert captured["headers"]["Authorization"] == "Bearer secret"
    body = captured["json"]
    assert body["model"] == "m1"
    assert body["temperature"] == 0.3
    assert body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_json_tolerates_fences(monkeypatch):
    monkeypatch.setattr(
        llm_client.requests, "post",
        lambda *a, **k: _FakeResp('```json\n{"skills": ["python"]}\n```'),
    )
    c = OpenAIClient(base_url="http://x/v1", model="m")
    assert c.chat_json([{"role": "user", "content": "x"}]) == {"skills": ["python"]}


def test_chat_many_preserves_order_and_tolerates_failure(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        text = json["messages"][0]["content"]
        if text == "boom":
            raise RuntimeError("upstream 500")
        return _FakeResp(f"echo:{text}")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    c = OpenAIClient(base_url="http://x/v1", model="m")
    msgs = [[{"role": "user", "content": t}] for t in ("a", "boom", "c")]
    results = c.chat_many(msgs, max_workers=3)
    assert results == ["echo:a", None, "echo:c"]


def test_from_config_requires_enabled():
    with pytest.raises(LLMConfigError):
        OpenAIClient.from_config({"enabled": False, "base_url": "http://x/v1"})
    # require_enabled=False bypasses the gate.
    c = OpenAIClient.from_config({"enabled": False, "base_url": "http://x/v1"},
                                 require_enabled=False)
    assert c.base_url == "http://x/v1"


def test_thinking_budget_sent_and_bumps_max_tokens(monkeypatch):
    """Default client sends thinking_token_budget and raises max_tokens by it (answer keeps room)."""
    captured = {}
    monkeypatch.setattr(
        llm_client.requests, "post",
        lambda url, headers=None, json=None, timeout=None: captured.update(json=json) or _FakeResp("ok"),
    )
    c = OpenAIClient(base_url="http://x/v1", model="m", max_tokens=1024)  # budget defaults 1024
    c.chat([{"role": "user", "content": "hi"}])
    assert captured["json"]["thinking_token_budget"] == 1024
    assert captured["json"]["max_tokens"] == 2048  # 1024 answer + 1024 thinking headroom

    # A per-call max_tokens override is still the answer budget; thinking is added on top.
    c.chat([{"role": "user", "content": "hi"}], max_tokens=200)
    assert captured["json"]["max_tokens"] == 1224


def test_thinking_budget_zero_omits_param(monkeypatch):
    """budget=0 sends no thinking param and does not touch max_tokens."""
    seen = {}
    monkeypatch.setattr(
        llm_client.requests, "post",
        lambda url, headers=None, json=None, timeout=None: seen.update(json=json) or _FakeResp("ok"),
    )
    OpenAIClient(base_url="http://x/v1", model="m", max_tokens=512, thinking_token_budget=0).chat(
        [{"role": "user", "content": "hi"}])
    assert "thinking_token_budget" not in seen["json"]
    assert seen["json"]["max_tokens"] == 512


def test_400_on_budget_drops_and_restores_max_tokens(monkeypatch):
    """An endpoint that 400s on thinking_token_budget → drop it, restore max_tokens, retry, latch off."""
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if "thinking_token_budget" in json:
            return _FakeResp("", status_code=400)
        return _FakeResp("recovered")

    monkeypatch.setattr(llm_client.requests, "post", fake_post)
    c = OpenAIClient(base_url="http://x/v1", model="m", max_tokens=1024)
    assert c.chat([{"role": "user", "content": "hi"}]) == "recovered"
    # First attempt carried the budget + bumped max_tokens (400); retry dropped it and restored max_tokens.
    assert calls[0]["thinking_token_budget"] == 1024 and calls[0]["max_tokens"] == 2048
    assert "thinking_token_budget" not in calls[1] and calls[1]["max_tokens"] == 1024
    assert c._thinking_param_ok is False
    # A subsequent call no longer sends the budget nor bumps max_tokens.
    calls.clear()
    c.chat([{"role": "user", "content": "again"}])
    assert "thinking_token_budget" not in calls[0] and calls[0]["max_tokens"] == 1024


def test_empty_content_retries_once(monkeypatch):
    """An empty response (reasoning-budget exhaustion) is retried once, then recovers."""
    responses = iter([_FakeResp("", finish_reason="length"), _FakeResp("finally")])
    monkeypatch.setattr(
        llm_client.requests, "post",
        lambda *a, **k: next(responses),
    )
    c = OpenAIClient(base_url="http://x/v1", model="m")
    assert c.chat([{"role": "user", "content": "hi"}]) == "finally"


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('prose before {"a": 2} prose after') == {"a": 2}
    assert _extract_json("```\n[1, 2, 3]\n```") == [1, 2, 3]
    with pytest.raises(ValueError):
        _extract_json("no json here")
