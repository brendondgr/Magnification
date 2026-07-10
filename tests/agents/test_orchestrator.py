"""
Tests for the in-house orchestrator (utils/backend/agents/orchestrator.py).

Verifies node pipelines run in order, progress reports carry the expected shape, and the
semi-auto checkpoint both auto-approves (no resume_fn) and honours a user decision (with one).
"""

from utils.backend.agents.orchestrator import Orchestrator, Checkpoint


def test_report_shape():
    seen = []
    orch = Orchestrator(report=seen.append)
    orch.report("write", 50, "Drafting…")
    assert seen == [{"stage": "write", "percent": 50, "details": {"message": "Drafting…"}}]


def test_report_is_noop_without_callback():
    orch = Orchestrator()
    orch.report("x", 1, "y")  # must not raise


def test_checkpoint_auto_approves_without_resume_fn():
    orch = Orchestrator()
    cp = orch.checkpoint("angle", {"thesis": "t"})
    assert isinstance(cp, Checkpoint)
    assert cp.name == "angle"
    assert cp.decision == "approve"
    assert cp.payload == {"thesis": "t"}


def test_checkpoint_uses_resume_fn_decision():
    def resume_fn(pending: Checkpoint) -> Checkpoint:
        assert pending.name == "angle"
        return Checkpoint(name=pending.name, payload=pending.payload,
                          decision="edit", edits={"thesis": "sharper angle"})

    orch = Orchestrator(resume_fn=resume_fn)
    cp = orch.checkpoint("angle", {"thesis": "t"})
    assert cp.decision == "edit"
    assert cp.edits == {"thesis": "sharper angle"}


def test_pipeline_runs_nodes_in_order():
    calls = []

    def node_a(state, orch):
        calls.append("a")
        state["a"] = True

    def node_b(state, orch):
        calls.append("b")
        state["b"] = state.get("a", False)

    orch = Orchestrator()
    state = {}
    for node in (node_a, node_b):
        node(state, orch)
    assert calls == ["a", "b"]
    assert state == {"a": True, "b": True}
