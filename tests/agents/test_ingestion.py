"""
Tests for the in-house ingestion agent (utils/backend/agents/ingestion).

Uses a fake LLM client (an object with ``chat``/``chat_json``) so nothing hits a real
endpoint, and verifies classification, each doc-type normalizer, graceful degradation
when no LLM is available, and error fallback.
"""

import pytest

import utils.backend.agents.ingestion.agent as agent_mod
from utils.backend.agents.ingestion import ingest_document, classify_document


class FakeClient:
    """Minimal stand-in for OpenAIClient with canned responses (or a raising flag)."""

    def __init__(self, json_response=None, text_response=None, raise_on=None):
        self._json = json_response
        self._text = text_response
        self._raise_on = raise_on  # "json" | "text" | None

    def chat_json(self, messages, **kw):
        if self._raise_on == "json":
            raise RuntimeError("llm boom")
        return self._json

    def chat(self, messages, **kw):
        if self._raise_on == "text":
            raise RuntimeError("llm boom")
        return self._text


def test_resume_uses_profile_builder():
    client = FakeClient(json_response={
        "interests_paragraph": "ML for healthcare.",
        "skills": ["python", "pytorch"],
        "job_titles": ["ML Engineer"],
        "keyword_groups": [],
    })
    res = ingest_document("jane_resume.pdf", b"ignored (client is faked)",
                          doc_type="resume", client=client)
    assert res["doc_type"] == "resume"
    assert res["target_table"] == "profiles"
    assert res["llm_used"] is True
    assert res["draft"]["skills"] == ["python", "pytorch"]
    assert res["draft"]["job_titles"] == ["ML Engineer"]


def test_behavioral_normalizes():
    client = FakeClient(json_response={
        "traits": {"influence": "high", "dominance": "moderate"},
        "strengths": ["clear writing", "ownership"],
        "work_style_paragraph": "Ships reviewable increments.",
    })
    res = ingest_document("disc.pdf", b"x", doc_type="behavioral", client=client)
    assert res["target_table"] == "behavioral_profiles"
    assert res["llm_used"] is True
    assert res["draft"]["traits"] == {"influence": "high", "dominance": "moderate"}
    assert res["draft"]["strengths"] == ["clear writing", "ownership"]
    assert res["draft"]["work_style_paragraph"] == "Ships reviewable increments."


def test_writing_fills_sample_when_missing():
    # LLM returns style labels but no sample_text -> agent backfills from the raw text.
    client = FakeClient(json_response={
        "tone": "warm", "dos": ["hook first"], "donts": ["generic openers"],
    })
    res = ingest_document("sample.txt", b"This is my distinctive writing sample voice.",
                          doc_type="writing", client=client)
    assert res["target_table"] == "writing_style_profiles"
    assert res["draft"]["tone"] == "warm"
    assert res["draft"]["dos"] == ["hook first"]
    assert "distinctive writing sample" in res["draft"]["sample_text"]


def test_reference_summary_with_llm():
    client = FakeClient(text_response="A strong recommendation from a former manager.")
    res = ingest_document("rec.txt", b"raw reference letter body",
                          doc_type="reference", client=client)
    assert res["doc_type"] == "reference"
    assert res["target_table"] is None
    assert res["llm_used"] is True
    assert res["summary"] == "A strong recommendation from a former manager."
    assert res["draft"] == {"summary": "A strong recommendation from a former manager."}


def test_degrades_without_llm(monkeypatch):
    # Force _resolve_client to find no endpoint.
    def _raise(*a, **k):
        raise RuntimeError("endpoint disabled")
    monkeypatch.setattr(agent_mod.OpenAIClient, "from_config", _raise)

    res = ingest_document("notes.txt", b"unspecified content", doc_type="behavioral", client=None)
    assert res["llm_used"] is False
    assert res["llm_error"] is None
    assert res["draft"] == {"traits": {}, "strengths": [], "work_style_paragraph": ""}

    # Writing still backfills the sample from raw text without an LLM.
    res_w = ingest_document("sample.txt", b"my raw voice here", doc_type="writing", client=None)
    assert res_w["llm_used"] is False
    assert res_w["draft"]["sample_text"] == "my raw voice here"


def test_llm_error_falls_back():
    client = FakeClient(raise_on="json")
    res = ingest_document("disc.pdf", b"x", doc_type="behavioral", client=client)
    assert res["llm_used"] is False
    assert res["llm_error"] is not None
    assert res["draft"] == {"traits": {}, "strengths": [], "work_style_paragraph": ""}


def test_classify_from_filename():
    assert classify_document("jane_resume.pdf", "text", None) == "resume"
    assert classify_document("DISC_assessment.pdf", "x", None) == "behavioral"
    assert classify_document("my_writing_sample.md", "x", None) == "writing"
    assert classify_document("reference_letter.txt", "x", None) == "reference"
    assert classify_document("random.bin", "x", None) == "other"
