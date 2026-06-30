"""
Unit tests for the OpenAI-compatible client. No network: ``requests.post`` is
monkeypatched so we assert the request shape and exercise parsing/parallel paths.
"""

import pytest

from utils.backend.llm import client as llm_client
from utils.backend.llm.client import OpenAIClient, LLMConfigError, _extract_json


class _FakeResp:
    def __init__(self, content="ok"):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


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


def test_extract_json_variants():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('prose before {"a": 2} prose after') == {"a": 2}
    assert _extract_json("```\n[1, 2, 3]\n```") == [1, 2, 3]
    with pytest.raises(ValueError):
        _extract_json("no json here")
