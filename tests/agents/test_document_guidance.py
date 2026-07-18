"""
Tests for the editable Document Guidance store (``agents/document_guidance.py``) and its API.

The store is exercised against an isolated temp config path (never the real
``config/document_guidance.json``) so the developer's live guidance is untouched. The route test
runs on the same isolated path via monkeypatch.
"""

import json

import pytest

from utils.backend.agents import document_guidance as dg


@pytest.fixture()
def temp_config(tmp_path, monkeypatch):
    path = tmp_path / "document_guidance.json"
    monkeypatch.setattr(dg, "CONFIG_PATH", str(path))
    return path


def test_default_when_no_override(temp_config):
    assert dg.get_guidance() == dg.DEFAULT_GUIDANCE
    assert dg.is_default() is True
    # The default carries both document kinds' guidance (one shared doc).
    assert "COVER LETTER" in dg.DEFAULT_GUIDANCE
    assert "RÉSUMÉ" in dg.DEFAULT_GUIDANCE
    assert "Winning Formula" in dg.DEFAULT_GUIDANCE


def test_set_and_get_override(temp_config):
    assert dg.set_guidance("My custom house style.") is True
    assert dg.get_guidance() == "My custom house style."
    assert dg.is_default() is False
    # Persisted as JSON on disk.
    assert json.loads(temp_config.read_text())["guidance"] == "My custom house style."


def test_blank_override_falls_back_to_default(temp_config):
    dg.set_guidance("   ")  # blank → treated as no override
    assert dg.get_guidance() == dg.DEFAULT_GUIDANCE
    assert dg.is_default() is True


def test_reset_removes_override(temp_config):
    dg.set_guidance("Custom.")
    assert dg.is_default() is False
    assert dg.reset_guidance() is True
    assert not temp_config.exists()
    assert dg.get_guidance() == dg.DEFAULT_GUIDANCE
    assert dg.is_default() is True


def test_api_round_trip(temp_config):
    """GET → PUT → GET → reset through the Flask test client on the isolated config."""
    import app as app_module
    client = app_module.application.test_client()

    r = client.get("/api/document-guidance")
    assert r.status_code == 200
    body = r.get_json()
    assert body["is_default"] is True
    assert "Winning Formula" in body["guidance"]

    r = client.put("/api/document-guidance", json={"guidance": "Edited guidance."})
    assert r.status_code == 200
    assert r.get_json()["is_default"] is False
    assert dg.get_guidance() == "Edited guidance."

    r = client.put("/api/document-guidance", json={"guidance": 123})  # wrong type
    assert r.status_code == 400

    r = client.post("/api/document-guidance/reset")
    assert r.status_code == 200
    assert r.get_json()["is_default"] is True
    assert dg.get_guidance() == dg.DEFAULT_GUIDANCE
