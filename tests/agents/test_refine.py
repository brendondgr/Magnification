"""
Tests for the Application-Mode refine plumbing: user ``instructions`` + ``prior_content`` must
thread through the graphs into the LLM prompts (so a steered re-run actually follows the guidance).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.agents import prompts, context, cover_letter, resume
from utils.backend.agents.orchestrator import Orchestrator


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(init_db, "SessionLocal",
                        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    yield engine
    engine.dispose()


class CapturingClient:
    """Fake client that records every user message so tests can assert what the nodes sent."""

    def __init__(self):
        self.user_msgs = []

    def chat_json(self, messages, **kw):
        self.user_msgs.append(messages[-1]["content"])
        s = messages[0]["content"].lower()
        if "research a company" in s:
            return {"mission": "m", "values": [], "angle": "a"}
        if "application-fit" in s:
            return {"verdict": "ok", "fit_score": 80, "emphasize": ["e"], "gaps": [],
                    "risks": "", "talking_points": ["tp"]}
        if "strategist" in s:
            return {"thesis": "t", "hooks": ["h"], "confidence": 0.9}
        if "filling the slots" in s:
            return {"hook": "x", "why_them": "y", "why_you": "z", "close": "c"}
        if "grounding checker" in s:
            return {"ok": True, "issues": []}
        if "cover-letter critic" in s:
            return {"score": 90, "generic_flags": [], "suggestions": []}
        if "identify which jd" in s:
            return {"missing_skills": [], "missing_keywords": [], "notes": ""}
        if "truth-preserving edits" in s:
            return {"edits": [], "cut_count": 0}
        if "ats-safe skeleton" in s:
            return {"summary": "s", "experience": "e", "skills": "Python", "education": ""}
        return {}

    def chat(self, messages, **kw):
        self.user_msgs.append(messages[-1]["content"])
        return "styled body with the requested changes"


def test_guidance_block():
    assert prompts.guidance_block("", "") == ""
    b = prompts.guidance_block("warmer tone", "an old draft")
    assert "USER GUIDANCE" in b and "warmer tone" in b
    assert "CURRENT DRAFT" in b and "an old draft" in b


def _seed_job():
    db_ops.upsert_active_profile({"name": "default", "resume_text": "I write Python.",
                                  "skills": ["Python"], "job_titles": ["ML Engineer"]})
    return db_ops.add_job({"title": "ML Engineer", "company": "Acme", "location": "Remote",
                           "description": "Python and ML."}, create_statuses=False)


def test_instructions_thread_into_cover_letter(temp_db):
    job_id = _seed_job()
    client = CapturingClient()
    state = context.load_context(job_id, "cover_letter", client=client,
                                 instructions="Make it warmer and mention leadership.",
                                 prior_content="An earlier draft to build on.")
    cover_letter.run(state, Orchestrator())
    joined = " ".join(client.user_msgs)
    assert "Make it warmer and mention leadership." in joined  # guidance reached strategize + writer
    assert "An earlier draft to build on." in joined            # prior_content reached the writer


def test_instructions_thread_into_resume(temp_db):
    job_id = _seed_job()
    client = CapturingClient()
    state = context.load_context(job_id, "resume", client=client,
                                 instructions="Emphasize distributed systems.",
                                 prior_content="Prior résumé text.")
    resume.run(state, Orchestrator())
    joined = " ".join(client.user_msgs)
    assert "Emphasize distributed systems." in joined
    assert "Prior résumé text." in joined
