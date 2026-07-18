"""
API tests for the Options blueprint. Backs up / restores the gitignored config
files so it never destroys real settings, and monkeypatches the network for /test.
"""

import os
import shutil

import pytest

from app import application
from utils.backend.llm import client as llm_client
from utils.backend.llm.config import CONFIG_PATH as LLM_CFG
from utils.backend.recommend.runtime_config import CONFIG_PATH as RUNTIME_CFG


@pytest.fixture
def client():
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _preserve_config_files():
    backups = {}
    for path in (LLM_CFG, RUNTIME_CFG):
        if os.path.exists(path):
            backups[path] = path + ".bak"
            shutil.copy2(path, backups[path])
            # Start each test from a clean slate (defaults) so round-trip assertions
            # don't depend on the user's ambient, tuned config values.
            os.remove(path)
    try:
        yield
    finally:
        for path in (LLM_CFG, RUNTIME_CFG):
            if path in backups:
                shutil.move(backups[path], path)
            elif os.path.exists(path):
                os.remove(path)  # created during the test


def test_llm_options_roundtrip(client):
    defaults = client.get("/api/options/llm").get_json()
    assert "base_url" in defaults and "enabled" in defaults

    save = client.post("/api/options/llm", json={
        "enabled": True, "base_url": "http://127.0.0.1:9999/v1",
        "api_key": "k", "model": "test-model",
    })
    assert save.status_code == 200 and save.get_json()["success"] is True

    loaded = client.get("/api/options/llm").get_json()
    assert loaded["enabled"] is True
    assert loaded["base_url"] == "http://127.0.0.1:9999/v1"
    assert loaded["model"] == "test-model"
    # Thinking budget defaults to 1024.
    assert loaded["thinking_token_budget"] == 1024


def test_thinking_token_budget_clamped_to_min(client):
    """The thinking budget can be raised but never persisted below 1024 ('at least 1024')."""
    client.post("/api/options/llm", json={"thinking_token_budget": 4096})
    assert client.get("/api/options/llm").get_json()["thinking_token_budget"] == 4096
    # Below-floor / garbage values clamp back up to 1024.
    client.post("/api/options/llm", json={"thinking_token_budget": 128})
    assert client.get("/api/options/llm").get_json()["thinking_token_budget"] == 1024
    client.post("/api/options/llm", json={"thinking_token_budget": "oops"})
    assert client.get("/api/options/llm").get_json()["thinking_token_budget"] == 1024


def test_llm_options_test_endpoint(client, monkeypatch):
    class _Resp:
        def raise_for_status(self): return None
        def json(self): return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(llm_client.requests, "post", lambda *a, **k: _Resp())
    resp = client.post("/api/options/llm/test", json={"base_url": "http://x/v1", "model": "m"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_runtime_options_roundtrip(client):
    defaults = client.get("/api/options/runtime").get_json()
    assert "weights" in defaults and "embed_workers" in defaults

    save = client.post("/api/options/runtime", json={
        "enable_llm_rerank": True, "llm_fraction": 0.5,
        "weights": {"semantic": 0.7},
    })
    assert save.status_code == 200 and save.get_json()["success"] is True

    loaded = client.get("/api/options/runtime").get_json()
    assert loaded["enable_llm_rerank"] is True
    assert loaded["llm_fraction"] == 0.5
    assert loaded["weights"]["semantic"] == 0.7
    # Unspecified weights keep their defaults (deep-merge).
    assert loaded["weights"]["bm25"] == 0.15
