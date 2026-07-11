"""
Tests for the cover-letter quality upgrade (design: grounded-in-stated-interests + length target).

Covers the three levers added so the letter stops inventing interests and stops running short:
  * ``candidate_facts`` surfaces the profile's stated ``interests_paragraph`` (+ résumé/skills);
  * the strategize/write nodes actually put that block into their LLM user messages;
  * the cover-letter prompts carry the 300-400 word target + no-invented-interests rule;
  * the graph's revision loop enforces a minimum length on the LLM path (and does NOT on the
    offline fallback, which cannot grow).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.seed_documents import seed_documents_if_empty
from utils.backend.database.models import Base
from utils.backend.agents import context, cover_letter, prompts
from utils.backend.agents import nodes_shared as shared
from utils.backend.agents.orchestrator import Orchestrator, COVER_MIN_WORDS


# ==================== helpers (pure) ====================

def test_candidate_facts_surfaces_stated_interests():
    facts = shared.candidate_facts({
        "interests_paragraph": "I want to work on reinforcement learning for robotics.",
        "skills": ["Python", "PyTorch"],
        "job_titles": ["ML Engineer"],
        "resume_text": "Built RL agents.",
    })
    assert "reinforcement learning for robotics" in facts
    assert "do not invent interests" in facts.lower()
    assert "Python" in facts and "Built RL agents." in facts


def test_candidate_facts_omits_missing_fields():
    assert shared.candidate_facts({}) == ""
    facts = shared.candidate_facts({"skills": ["Go"]})
    assert "interests" not in facts.lower() and "Go" in facts


def test_letter_word_count_ignores_template_slots():
    # Slots contribute nothing; only the real scaffold words ("Dear" + the stray comma) remain.
    assert shared.letter_word_count("Dear {{hiring_manager}},\n\n{{hook}}\n\n{{close}}") == 2
    assert shared.letter_word_count("one two three four five") == 5
    assert shared.letter_word_count(None) == 0


def test_prompts_target_length_and_forbid_invented_interests():
    assert "300-400" in prompts.WRITE_LETTER_PROMPT
    assert "never invent" in prompts.WRITE_LETTER_PROMPT.lower()
    assert "stated interests" in prompts.WRITE_LETTER_PROMPT.lower()
    # The strategist must ground motivation in stated interests, not invent it.
    assert "never invent interests" in prompts.STRATEGIZE_PROMPT.lower()
    # The voice pass must not compress the letter back down.
    assert "300-400" in prompts.STYLE_PROMPT


# ==================== graph integration ====================

@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


_INTERESTS = "I am driven by building privacy-preserving ML systems for healthcare."


def _seed():
    seed_documents_if_empty()
    db_ops.upsert_active_profile({
        "name": "default",
        "resume_text": "Built ML systems in Python.",
        "interests_paragraph": _INTERESTS,
        "skills": ["Python", "ML"],
        "job_titles": ["ML Engineer"],
    })
    job_id = db_ops.add_job({
        "title": "ML Engineer", "company": "Acme", "location": "Remote",
        "description": "Python and ML for production systems.",
    }, create_statuses=False)
    db_ops.save_job_analysis(job_id, {
        "rag_score": 0.6, "skill_match": {"matched": ["Python"], "missing": ["Kubernetes"]},
        "extracted_skills": ["Python", "Kubernetes"],
    }, profile_id=db_ops.get_active_profile()["id"])
    return job_id


class _CapturingClient:
    """Records the user message routed to each node; returns a styled letter of a chosen length."""

    def __init__(self, styled_words: int):
        self.user_by_node = {}
        self._styled = "Dear Hiring Manager,\n\n" + " ".join(["word"] * styled_words) + \
                       "\n\nSincerely,\n[Your Name]"

    def chat_json(self, messages, **kw):
        s = messages[0]["content"].lower()
        user = messages[1]["content"]
        if "cover-letter strategist" in s:
            self.user_by_node["strategist"] = user
            return {"thesis": "You fit this ML role.", "hooks": ["Python"], "confidence": 0.9}
        if "filling the slots" in s:
            self.user_by_node["writer"] = user
            return {"hook": "Excited.", "why_them": "Acme.", "why_you": "Python.", "close": "Thanks."}
        if "research a company" in s:
            return {"mission": "ML", "values": [], "angle": "ML work"}
        if "application-fit evaluator" in s:
            return {"verdict": "strong fit", "fit_score": 88, "emphasize": ["Python"],
                    "gaps": [], "risks": "", "talking_points": ["Python"]}
        if "grounding checker" in s:
            return {"ok": True, "issues": []}
        if "cover-letter critic" in s:
            return {"score": 95, "generic_flags": [], "suggestions": []}
        return {}

    def chat(self, messages, **kw):
        if "voice editor" in messages[0]["content"].lower():
            return self._styled
        return "ok"


def test_strategize_and_writer_receive_stated_interests(temp_db):
    job_id = _seed()
    client = _CapturingClient(styled_words=350)
    state = context.load_context(job_id, "cover_letter", client=client)
    cover_letter.run(state, Orchestrator())
    # The candidate's own interests reach BOTH the angle and the prose nodes.
    assert _INTERESTS in client.user_by_node["strategist"]
    assert _INTERESTS in client.user_by_node["writer"]


def test_long_letter_is_accepted_without_review(temp_db):
    job_id = _seed()
    client = _CapturingClient(styled_words=350)  # comfortably over COVER_MIN_WORDS
    state = context.load_context(job_id, "cover_letter", client=client)
    result = cover_letter.run(state, Orchestrator())
    assert shared.letter_word_count(state["current_document"]) >= COVER_MIN_WORDS
    assert result["needs_review"] is False


def test_short_letter_triggers_review_on_llm_path(temp_db):
    job_id = _seed()
    client = _CapturingClient(styled_words=20)  # far under the length floor
    state = context.load_context(job_id, "cover_letter", client=client)
    result = cover_letter.run(state, Orchestrator())
    # Length gate refuses to accept a half-length letter even with a clean critic + truthfulness.
    assert result["needs_review"] is True
