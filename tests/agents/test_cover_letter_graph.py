"""
End-to-end tests for the cover-letter graph (utils/backend/agents/cover_letter.py).

Runs against an isolated in-memory SQLite DB (never the real dev DB), exercising:
  * the offline path (no LLM) — deterministic fallback letter + a persisted job_evaluation
    seeded from JobAnalysis;
  * the LLM path with a prompt-routing fake client — filled slots + styled draft + critic loop;
  * the interactive Checkpoint 1 (angle) pause/resume.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.database.models import Base
from utils.backend.agents import context, cover_letter
from utils.backend.agents.orchestrator import Orchestrator, Checkpoint


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def _seed_job_and_profile():
    db_ops.upsert_active_profile({
        "name": "default",
        "resume_text": "Built ML systems in Python. Shipped production services.",
        "interests_paragraph": "I build ML systems.",
        "skills": ["Python", "ML"],
        "job_titles": ["ML Engineer"],
    })
    job_id = db_ops.add_job({
        "title": "ML Engineer", "company": "Acme", "location": "Remote",
        "description": "We need Python and ML for production systems. Kubernetes a plus.",
    }, create_statuses=False)
    db_ops.save_job_analysis(job_id, {
        "rag_score": 0.6,
        "skill_match": {"matched": ["Python"], "missing": ["Kubernetes"]},
        "extracted_skills": ["Python", "Kubernetes"],
    }, profile_id=db_ops.get_active_profile()["id"])
    return job_id


class RoutingClient:
    """Fake LLM client that returns a shape appropriate to each node's system prompt."""

    def __init__(self):
        self.systems = []

    def chat_json(self, messages, **kw):
        s = messages[0]["content"].lower()
        self.systems.append(s[:80])
        if "research a company" in s:
            return {"mission": "Build ML infra", "values": ["rigor"], "angle": "the ML platform work"}
        if "application-fit evaluator" in s:
            return {"verdict": "strong fit", "fit_score": 88, "emphasize": ["Python", "ML"],
                    "gaps": ["Kubernetes"], "risks": "", "talking_points": ["Python for ML"]}
        if "cover-letter strategist" in s:
            return {"thesis": "You fit this ML role.", "hooks": ["Python", "ML"], "confidence": 0.5}
        if "filling the slots" in s:
            return {"hook": "Excited to apply.", "why_them": "Acme's ML work.",
                    "why_you": "My Python/ML record.", "close": "Thank you."}
        if "grounding checker" in s:
            return {"ok": True, "issues": []}
        if "cover-letter critic" in s:
            return {"score": 90, "generic_flags": [], "suggestions": []}
        return {}

    def chat(self, messages, **kw):
        if "voice editor" in messages[0]["content"].lower():
            return "Dear Hiring Manager,\n\nA styled letter about Acme and my Python/ML record.\n\nSincerely,\n[Your Name]"
        return "ok"


def _force_no_endpoint(monkeypatch):
    """Make resolve_client() find no LLM endpoint, regardless of the shared config."""
    def _raise(*a, **k):
        raise RuntimeError("endpoint disabled")
    monkeypatch.setattr(context.OpenAIClient, "from_config", _raise)


def test_offline_path_fills_letter_and_persists_evaluation(temp_db, monkeypatch):
    _force_no_endpoint(monkeypatch)
    job_id = _seed_job_and_profile()
    state = context.load_context(job_id, "cover_letter", client=None)
    assert state["client"] is None  # forced no-endpoint path

    result = cover_letter.run(state, Orchestrator())

    # A filled letter mentioning the company, from the deterministic fallback.
    assert "Acme" in result["final"]
    assert result["needs_review"] is False  # clean fallback clears the heuristic critic
    assert result["llm_used"] is False

    # evaluate_fit persisted a job_evaluation seeded from JobAnalysis.skill_match.
    ev = docs_ops.get_job_evaluation(job_id)
    assert ev is not None
    assert ev["emphasize"] == ["Python"]
    assert ev["gaps"] == ["Kubernetes"]
    assert ev["fit_score"] == 60.0  # rag_score 0.6 → 60


def test_llm_path_uses_all_nodes(temp_db):
    job_id = _seed_job_and_profile()
    client = RoutingClient()
    state = context.load_context(job_id, "cover_letter", client=client)

    result = cover_letter.run(state, Orchestrator())

    assert result["llm_used"] is True
    assert "styled letter about Acme" in result["final"]
    # The LLM evaluation refined the seed (emphasize now has both skills).
    assert docs_ops.get_job_evaluation(job_id)["emphasize"] == ["Python", "ML"]
    # Every node's prompt was exercised.
    joined = " ".join(client.systems)
    for marker in ("research", "application-fit", "strategist", "filling the slots", "critic"):
        assert marker in joined


def test_interactive_checkpoint_pauses_and_resumes(temp_db):
    job_id = _seed_job_and_profile()
    client = RoutingClient()
    state = context.load_context(job_id, "cover_letter", client=client)
    state["interactive"] = True

    seen = {}

    def resume_fn(pending: Checkpoint) -> Checkpoint:
        seen["checkpoint"] = pending.name
        return Checkpoint(name=pending.name, payload=pending.payload,
                          decision="edit", edits={"thesis": "A sharper, edited angle."})

    orch = Orchestrator(resume_fn=resume_fn)
    result = cover_letter.run(state, orch)

    assert seen.get("checkpoint") == "angle"  # confidence 0.5 < 0.8 → checkpoint fired
    assert state["strategy"]["thesis"] == "A sharper, edited angle."
    assert result["final"]  # graph completed after resume
