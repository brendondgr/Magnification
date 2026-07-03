"""Unit tests for the LLM reachability probe (offline; ``requests`` mocked)."""

import requests as real_requests

from utils.backend.scheduler import llm_health


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code

    @property
    def ok(self):
        return 200 <= self.status_code < 300


def _patch_config(monkeypatch, base_url="http://localhost:9090/v1", api_key=""):
    monkeypatch.setattr(
        llm_health,
        "load_llm_endpoint_config",
        lambda: {"base_url": base_url, "api_key": api_key, "timeout": 5},
    )


def test_ready_on_200_and_hits_models_endpoint(monkeypatch):
    _patch_config(monkeypatch)
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["timeout"] = timeout
        return _Resp(200)

    monkeypatch.setattr(llm_health.requests, "get", fake_get)
    assert llm_health.check_llm_ready() is True
    assert captured["url"] == "http://localhost:9090/v1/models"
    # timeout is capped even when config asks for a small value
    assert captured["timeout"] == 5


def test_api_key_sent_as_bearer(monkeypatch):
    _patch_config(monkeypatch, api_key="secret")
    seen = {}

    def fake_get(url, headers=None, timeout=None):
        seen["headers"] = headers or {}
        return _Resp(200)

    monkeypatch.setattr(llm_health.requests, "get", fake_get)
    assert llm_health.check_llm_ready() is True
    assert seen["headers"].get("Authorization") == "Bearer secret"


def test_not_ready_on_connection_error(monkeypatch):
    _patch_config(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        raise real_requests.ConnectionError("connection refused")

    monkeypatch.setattr(llm_health.requests, "get", fake_get)
    assert llm_health.check_llm_ready() is False


def test_not_ready_on_timeout(monkeypatch):
    _patch_config(monkeypatch)

    def fake_get(url, headers=None, timeout=None):
        raise real_requests.Timeout("timed out")

    monkeypatch.setattr(llm_health.requests, "get", fake_get)
    assert llm_health.check_llm_ready() is False


def test_not_ready_on_5xx(monkeypatch):
    _patch_config(monkeypatch)
    monkeypatch.setattr(
        llm_health.requests, "get", lambda url, headers=None, timeout=None: _Resp(503)
    )
    assert llm_health.check_llm_ready() is False


def test_not_ready_without_base_url(monkeypatch):
    _patch_config(monkeypatch, base_url="")
    # Should short-circuit without calling requests at all.
    def explode(*a, **k):
        raise AssertionError("requests.get should not be called")

    monkeypatch.setattr(llm_health.requests, "get", explode)
    assert llm_health.check_llm_ready() is False
