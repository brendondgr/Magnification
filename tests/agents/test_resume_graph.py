"""
End-to-end tests for the résumé fine-tuner graph (utils/backend/agents/resume.py).

Isolated in-memory DB. Exercises:
  * the offline path — a truth-preserving rewrite that surfaces only skills the candidate has,
    producing a real match-lift from the reused recommender;
  * that a JD skill the candidate LACKS is never fabricated;
  * the LLM path with a prompt-routing fake;
  * the interactive Checkpoint 1 (plan) pause when cuts are large.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.agents import context, resume
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


def _force_no_endpoint(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("endpoint disabled")
    monkeypatch.setattr(context.OpenAIClient, "from_config", _raise)


def _seed():
    db_ops.upsert_active_profile({
        "name": "default",
        "resume_text": "Software engineer. I wrote Python services.",
        "interests_paragraph": "I build systems.",
        "skills": ["Python", "PyTorch", "Kubernetes"],   # NOTE: candidate does NOT have Rust
        "job_titles": ["ML Engineer"],
    })
    job_id = db_ops.add_job({
        "title": "ML Engineer", "company": "Acme", "location": "Remote",
        "description": "We need Python, PyTorch, and Kubernetes. Rust is a plus.",
    }, create_statuses=False)
    db_ops.save_job_analysis(job_id, {
        "rag_score": 0.5,
        "skill_match": {"matched": ["Python"], "missing": ["PyTorch", "Kubernetes", "Rust"]},
        "extracted_skills": ["Python", "PyTorch", "Kubernetes", "Rust"],
    }, profile_id=db_ops.get_active_profile()["id"])
    return job_id


class ResumeRoutingClient:
    def __init__(self):
        self.systems = []

    def chat_json(self, messages, **kw):
        s = messages[0]["content"].lower()
        self.systems.append(s[:80])
        if "identify which jd" in s:
            return {"missing_skills": ["PyTorch", "Kubernetes"], "missing_keywords": [], "notes": "thin on ML infra"}
        if "you plan truth-preserving edits" in s:
            return {"edits": [{"action": "rewrite", "target": "summary", "reason": "surface ML"}], "cut_count": 1}
        if "ats-safe skeleton" in s:
            return {"summary": "ML engineer fluent in Python, PyTorch, Kubernetes.",
                    "experience": "Built ML systems with Python, PyTorch, and Kubernetes.",
                    "skills": "Python, PyTorch, Kubernetes", "education": "BS CS"}
        if "grounding checker" in s:
            return {"ok": True, "issues": []}
        return {}

    def chat(self, messages, **kw):
        # Only rewrite_resume uses chat-text in this graph.
        return "Built production ML systems with Python, PyTorch, and Kubernetes."


def test_offline_truth_preserving_lift(temp_db, monkeypatch):
    _force_no_endpoint(monkeypatch)
    job_id = _seed()
    state = context.load_context(job_id, "resume", client=None)
    assert state["client"] is None

    result = resume.run(state, Orchestrator())

    # A real, objective lift from the reused recommender.
    assert isinstance(result["match_before"], float)
    assert isinstance(result["match_after"], float)
    assert result["match_after"] > result["match_before"]
    assert result["needs_review"] is False

    final = result["final"]
    assert "Kubernetes" in final          # a candidate-owned JD skill was surfaced
    assert "rust" not in final.lower()    # a skill the candidate LACKS was NOT fabricated


def test_llm_path_scores_and_formats(temp_db):
    job_id = _seed()
    client = ResumeRoutingClient()
    state = context.load_context(job_id, "resume", client=client)

    result = resume.run(state, Orchestrator())

    assert result["llm_used"] is True
    assert "Kubernetes" in result["final"]
    assert isinstance(result["match_after"], float)
    assert 0.0 <= result["match_after"] <= 1.0
    joined = " ".join(client.systems)
    for marker in ("identify which jd", "truth-preserving edits", "ats-safe skeleton"):
        assert marker in joined


def test_interactive_plan_checkpoint(temp_db):
    job_id = _seed()

    class BigCutClient(ResumeRoutingClient):
        def chat_json(self, messages, **kw):
            s = messages[0]["content"].lower()
            if "you plan truth-preserving edits" in s:
                return {"edits": [{"action": "cut", "target": "old role", "reason": "irrelevant"}],
                        "cut_count": 4}
            return super().chat_json(messages, **kw)

    state = context.load_context(job_id, "resume", client=BigCutClient())
    state["interactive"] = True

    seen = {}

    def resume_fn(pending: Checkpoint) -> Checkpoint:
        seen["checkpoint"] = pending.name
        return Checkpoint(name=pending.name, payload=pending.payload, decision="approve")

    result = resume.run(state, Orchestrator(resume_fn=resume_fn))
    assert seen.get("checkpoint") == "plan"   # cut_count 4 ≥ 3 → checkpoint fired
    assert result["final"]
