"""
The Résumé Fine-Tuner graph (design §3.1) — assembled as an in-house node pipeline:

    evaluate_gap → plan_edits
        → [CHECKPOINT 1: approve the rewrite/cut plan, when interactive and cuts are large]
        → (rewrite → ats_format → score → truthfulness → decide) × up to MAX_REVISIONS
        → finalize

The ``score`` step is the differentiator (design §3.2): it treats the tailored résumé as a
throwaway profile and reuses Magnification's own recommender against THIS job, yielding a real
``match_before`` → ``match_after`` lift that is both the loop's stop criterion and the headline UI
metric. Persistence to ``generated_documents`` (with the match-lift) is the service layer's job.
"""

from typing import Any, Dict

from . import nodes_shared as shared
from . import nodes_resume as rz
from . import scoring
from . import latex
from .orchestrator import Checkpoint, MAX_REVISIONS, MATCH_MIN_LIFT


def _apply_plan_decision(state: Dict[str, Any], cp: Checkpoint) -> None:
    if cp.decision == "reject":
        return
    edits = cp.edits or {}
    plan = state.get("plan") or {}
    if edits.get("plan"):
        plan = edits["plan"]
    state["plan"] = plan


def run(state: Dict[str, Any], orch) -> Dict[str, Any]:
    rz.evaluate_gap(state, orch)
    rz.plan_edits(state, orch)

    # Checkpoint 1 (proactive): approve the plan when interactive and the cuts are large.
    plan = state.get("plan") or {}
    if state.get("interactive") and plan.get("cut_count", 0) >= 3:
        cp = orch.checkpoint("plan", {"plan": plan, "gap": state.get("gap")})
        _apply_plan_decision(state, cp)

    base_profile = state.get("profile") or {}
    before_text = base_profile.get("resume_text") or shared.profile_summary(base_profile)

    accepted = False
    for revision in range(1, MAX_REVISIONS + 1):
        state["revision"] = revision
        rz.rewrite_resume(state, orch)
        rz.ats_format(state, orch)
        final_text = state.get("ats") or state.get("rewrite") or ""

        # ★ Objective match-lift via the recommender (the differentiated feature).
        orch.report("score", 82, "Scoring the tailored résumé against the job…")
        lift = scoring.match_lift(state["job"], state.get("analysis"), base_profile,
                                  before_text, final_text)
        state["match_before"] = lift["match_before"]
        state["match_after"] = lift["match_after"]
        state["lift"] = lift["lift"]

        state["current_document"] = final_text
        shared.truthfulness_check(state, orch)

        lift_ok = lift["match_after"] >= lift["match_before"] + MATCH_MIN_LIFT
        truthful_ok = (state.get("truthful") or {}).get("ok", True)
        if lift_ok and truthful_ok:
            accepted = True
            break

    state["needs_review"] = not accepted
    # Plain tailored text is what the match-lift scored on; the persisted document is LaTeX.
    orch.report("render", 94, "Rendering the résumé as LaTeX…")
    state["final_text"] = state.get("ats") or state.get("rewrite") or ""
    state["final"] = latex.build_resume_tex(state)
    state["format"] = "latex"
    orch.report("finalize", 96, "Finalizing the résumé…")
    return state
