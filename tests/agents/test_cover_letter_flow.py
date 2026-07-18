"""
Tests for the flow-refinement stage (the forced-fit fix): ``refine_flow`` audits the styled letter
for told-not-shown fit claims (company flattery, asserted fit, spliced transitions) and rewrites
the flagged sentences, looping until the audit comes back clean (capped at ``MAX_FLOW_PASSES``).

Covers the node's loop mechanics in isolation plus its wiring in the graph: it runs between style
and critique, and its output is what the critic, truthfulness check, LaTeX render, and final text
all consume.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.agents import context, cover_letter
from utils.backend.agents import nodes_cover_letter as cl
from utils.backend.agents.orchestrator import Orchestrator, MAX_FLOW_PASSES


_STYLED = ("Dear Hiring Manager,\n\nAcme's deployment of thousands of models shows a clear "
           "commitment to putting AI into practice. " + " ".join(["word"] * 320) +
           "\n\nSincerely,\n[Your Name]")
_FLAG = {"quote": "Acme's deployment of thousands of models shows a clear commitment to putting "
                  "AI into practice.",
         "problem": "company flattery — tells the fit instead of showing it",
         "fix": "connect through the candidate's own agentic-pipeline work"}
_REWRITTEN = ("Dear Hiring Manager,\n\nI build agentic pipelines and follow the model-deployment "
              "work your team publishes, which is the problem space I want to keep working in. "
              + " ".join(["word"] * 320) + "\n\nSincerely,\n[Your Name]")


class _FlowClient:
    """Programmable audit/rewrite client: pops one audit result per audit call."""

    def __init__(self, audits, rewrite=_REWRITTEN):
        self.audits = list(audits)          # each item: list of flags to return, in call order
        self.rewrite = rewrite
        self.audit_users = []
        self.rewrite_users = []

    def chat_json(self, messages, **kw):
        s = messages[0]["content"].lower()
        if "forced-fit detector" in s:
            self.audit_users.append(messages[1]["content"])
            flags = self.audits.pop(0) if self.audits else []
            return {"flags": flags}
        return {}

    def chat(self, messages, **kw):
        assert "line editor" in messages[0]["content"].lower()
        self.rewrite_users.append(messages[1]["content"])
        return self.rewrite


def _state(client, styled=_STYLED, **extra):
    state = {"styled_draft": styled, "client": client,
             "profile": {"interests_paragraph": "I build agentic LLM pipelines.",
                         "resume_text": "Built agentic pipelines."},
             "guidance": "GUIDANCE_SENTINEL: show, don't tell.",
             "job": {"title": "ML Engineer", "company": "Acme"}}
    state.update(extra)
    return state


# ==================== node in isolation ====================

def test_clean_first_audit_leaves_letter_untouched():
    client = _FlowClient(audits=[[]])
    state = _state(client)
    cl.refine_flow(state, Orchestrator())
    assert state["smoothed_draft"] == _STYLED
    assert state["flow"] == {"passes": 0, "flags": []}
    assert len(client.audit_users) == 1 and not client.rewrite_users


def test_flagged_letter_is_rewritten_until_audit_is_clean():
    client = _FlowClient(audits=[[_FLAG], []])
    state = _state(client)
    cl.refine_flow(state, Orchestrator())
    assert state["smoothed_draft"] == _REWRITTEN
    assert state["flow"]["passes"] == 1 and state["flow"]["flags"] == []
    assert len(client.audit_users) == 2 and len(client.rewrite_users) == 1
    # The rewriter gets the flag (verbatim quote + fix), the candidate's real material to ground
    # the rewrite in, and the house guidance.
    rewrite_user = client.rewrite_users[0]
    assert _FLAG["quote"] in rewrite_user
    assert _FLAG["fix"] in rewrite_user
    assert "agentic LLM pipelines" in rewrite_user
    assert "GUIDANCE_SENTINEL" in rewrite_user
    assert "GUIDANCE_SENTINEL" in client.audit_users[0]


def test_flow_loop_is_capped_and_reports_remaining_flags():
    # The audit never comes back clean: exactly MAX_FLOW_PASSES rewrites happen, plus a final
    # audit that records the flags still standing.
    client = _FlowClient(audits=[[_FLAG]] * (MAX_FLOW_PASSES + 1))
    state = _state(client)
    cl.refine_flow(state, Orchestrator())
    assert state["flow"]["passes"] == MAX_FLOW_PASSES
    assert len(client.audit_users) == MAX_FLOW_PASSES + 1
    assert len(client.rewrite_users) == MAX_FLOW_PASSES
    assert state["flow"]["flags"] and state["flow"]["flags"][0]["quote"] == _FLAG["quote"]


def test_offline_passes_the_styled_draft_through():
    state = _state(client=None)
    cl.refine_flow(state, Orchestrator())
    assert state["smoothed_draft"] == _STYLED
    assert state["flow"] == {"passes": 0, "flags": []}


def test_audit_failure_passes_the_styled_draft_through():
    class _Broken:
        def chat_json(self, messages, **kw):
            raise RuntimeError("endpoint down")
    state = _state(client=_Broken())
    cl.refine_flow(state, Orchestrator())
    assert state["smoothed_draft"] == _STYLED


def test_blank_rewrite_keeps_the_letter():
    client = _FlowClient(audits=[[_FLAG], []], rewrite="   ")
    state = _state(client)
    cl.refine_flow(state, Orchestrator())
    assert state["smoothed_draft"] == _STYLED
    assert state["flow"]["passes"] == 0


# ==================== graph wiring ====================

@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def _seed():
    db_ops.upsert_active_profile({
        "name": "default",
        "resume_text": "Built agentic pipelines in Python.",
        "interests_paragraph": "I build agentic LLM pipelines.",
        "skills": ["Python"], "job_titles": ["ML Engineer"],
    })
    job_id = db_ops.add_job({
        "title": "ML Engineer", "company": "Acme", "location": "Remote",
        "description": "Python and ML for production systems.",
    }, create_statuses=False)
    db_ops.save_job_analysis(job_id, {
        "rag_score": 0.6, "skill_match": {"matched": ["Python"], "missing": []},
        "extracted_skills": ["Python"],
    }, profile_id=db_ops.get_active_profile()["id"])
    return job_id


class _GraphClient(_FlowClient):
    """The full graph's node fan-in, on top of the programmable flow behaviour."""

    def __init__(self, audits):
        super().__init__(audits)
        self.call_order = []

    def chat_json(self, messages, **kw):
        s = messages[0]["content"].lower()
        if "forced-fit detector" in s:
            self.call_order.append("flow_audit")
            return super().chat_json(messages, **kw)
        if "cover-letter strategist" in s:
            return {"thesis": "You fit.", "hooks": ["Python"], "confidence": 0.9}
        if "filling the slots" in s:
            return {"hook": "Hi.", "why_them": "Acme.", "why_you": "Python.", "close": "Thanks."}
        if "research a company" in s:
            return {"mission": "ML", "values": [], "angle": "ML work"}
        if "application-fit evaluator" in s:
            return {"verdict": "strong fit", "fit_score": 88, "emphasize": ["Python"],
                    "gaps": [], "risks": "", "talking_points": ["Python"]}
        if "grounding checker" in s:
            self.call_order.append("truthfulness")
            return {"ok": True, "issues": []}
        if "cover-letter critic" in s:
            self.call_order.append("critique")
            return {"score": 95, "generic_flags": [], "suggestions": []}
        return {}

    def chat(self, messages, **kw):
        s = messages[0]["content"].lower()
        if "voice editor" in s:
            self.call_order.append("style")
            return _STYLED
        self.call_order.append("flow_rewrite")
        return super().chat(messages, **kw)


def test_graph_runs_flow_between_style_and_critique_and_ships_the_smoothed_letter(temp_db):
    job_id = _seed()
    client = _GraphClient(audits=[[_FLAG], []])
    state = context.load_context(job_id, "cover_letter", client=client)
    result = cover_letter.run(state, Orchestrator())
    # Order within the revision: style → audit → rewrite → audit → critique → truthfulness.
    assert client.call_order[:6] == ["style", "flow_audit", "flow_rewrite", "flow_audit",
                                    "critique", "truthfulness"]
    # The smoothed letter is what gets scored, finalized, and rendered.
    assert state["current_document"] == _REWRITTEN
    assert result["final_text"] == _REWRITTEN
    assert "shows a clear commitment" not in result["final_text"]
    assert "I build agentic pipelines" in result["final"]  # the LaTeX body carries the fix
    assert result["needs_review"] is False
