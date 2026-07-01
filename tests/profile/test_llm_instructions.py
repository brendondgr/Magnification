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
from utils.backend.recommend.profile_builder import build_profile_from_text
from utils.backend.routes import profile_routes


class _FakeClient:
    """Captures the messages passed to chat_json and returns a fixed profile draft."""
    def __init__(self):
        self.messages = None

    def chat_json(self, messages, **kw):
        self.messages = messages
        return {"interests_paragraph": "x", "skills": ["python"], "job_titles": ["ML Engineer"],
                "keyword_groups": []}


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
