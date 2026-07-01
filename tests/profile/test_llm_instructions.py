"""
Tests for the profile Model Instructions field:
  * build_profile_from_text injects the user's instructions (prioritized) into the LLM prompt;
  * llm_instructions round-trips through the DB;
  * POST /api/profile/build falls back to the saved profile's llm_instructions.

DB/API tests use an isolated in-memory SQLite engine (never the real dev DB).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.recommend.profile_builder import (
    build_profile_from_text, _BUILD_SYSTEM_PROMPT,
)
from utils.backend.routes import profile_routes


class _FakeClient:
    """Captures the messages passed to chat_json and returns a fixed profile draft."""
    def __init__(self, reply=None):
        self.messages = None
        self._reply = reply or {"interests_paragraph": "x", "skills": ["python"],
                                "job_titles": ["ML Engineer"], "keyword_groups": []}

    def chat_json(self, messages, **kw):
        self.messages = messages
        return self._reply


def test_build_prompt_requests_new_fields():
    # The build prompt must ask the model for scopes, title_blocklist, and blocked_companies.
    for key in ('"scopes"', '"title_blocklist"', '"blocked_companies"'):
        assert key in _BUILD_SYSTEM_PROMPT
    # blocked_companies must be gated on explicit user request.
    assert "EXPLICITLY" in _BUILD_SYSTEM_PROMPT


def test_build_output_carries_scopes_blocklists():
    # A model reply with scopes/title_blocklist/blocked_companies flows through normalization.
    fake = _FakeClient({
        "interests_paragraph": "NLP research.",
        "skills": ["python"],
        "job_titles": ["Research Scientist"],
        "keyword_groups": [
            {"label": "Role", "terms": ["intern"], "scopes": ["title"]},
            {"label": "Domain", "terms": ["nlp"]},  # no scopes -> defaults to both
        ],
        "title_blocklist": ["Senior", "Manager"],
        "blocked_companies": ["Evil Corp"],
    })
    out = build_profile_from_text("resume", fake, instructions="avoid senior roles; block Evil Corp")
    assert out["keyword_groups"][0]["scopes"] == ["title"]
    assert out["keyword_groups"][1]["scopes"] == ["title", "description"]
    assert out["title_blocklist"] == ["Senior", "Manager"]
    assert out["blocked_companies"] == ["Evil Corp"]


def test_build_output_empty_blocklists_by_default():
    # When the model returns no companies (nothing requested), the profile has none.
    fake = _FakeClient({"interests_paragraph": "x", "skills": [], "job_titles": [],
                        "keyword_groups": [], "title_blocklist": [], "blocked_companies": []})
    out = build_profile_from_text("resume", fake)
    assert out["blocked_companies"] == []
    assert out["title_blocklist"] == []


def test_build_injects_instructions():
    fake = _FakeClient()
    build_profile_from_text("RESUME BODY", fake, instructions="Only NLP research roles, no management")
    user_msg = next(m["content"] for m in fake.messages if m["role"] == "user")
    assert "Only NLP research roles, no management" in user_msg
    assert "prioritize" in user_msg.lower()
    assert "RESUME BODY" in user_msg


def test_build_without_instructions_omits_block():
    fake = _FakeClient()
    build_profile_from_text("RESUME BODY", fake, instructions="   ")
    user_msg = next(m["content"] for m in fake.messages if m["role"] == "user")
    assert "prioritize" not in user_msg.lower()
    assert user_msg.startswith("Resume text:")


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def test_llm_instructions_roundtrip(temp_db):
    pid = db_ops.upsert_active_profile({"name": "default", "llm_instructions": "Prefer startups"})
    assert db_ops.get_profile_by_id(pid)["llm_instructions"] == "Prefer startups"
    # default empty string, not None, when unset
    pid2 = db_ops.upsert_active_profile({"name": "default"})
    assert db_ops.get_active_profile()["llm_instructions"] == "Prefer startups"  # unchanged


def test_build_falls_back_to_saved_instructions(temp_db, monkeypatch):
    db_ops.upsert_active_profile({"name": "default", "llm_instructions": "Saved guidance here"})

    captured = {}

    def _fake_build_draft(text, instructions=""):
        captured["instructions"] = instructions
        return {"interests_paragraph": "", "skills": [], "job_titles": [], "keyword_groups": []}, True, None

    monkeypatch.setattr(profile_routes, "_build_draft", _fake_build_draft)
    application.config["TESTING"] = True
    with application.test_client() as c:
        # No instructions in body -> should use the saved profile's llm_instructions.
        resp = c.post("/api/profile/build", json={"resume_text": "some resume"})
    assert resp.status_code == 200
    assert captured["instructions"] == "Saved guidance here"
