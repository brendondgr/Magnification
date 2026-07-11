"""
The Cover Letter graph (design §2.1) — assembled as an in-house node pipeline:

    research_company → evaluate_fit → strategize
        → [CHECKPOINT 1: approve the angle, when interactive]
        → (write → style → critique ‖ truthfulness → decide)  × up to MAX_REVISIONS
        → finalize

``run(state, orch)`` runs the pipeline over a ``state`` produced by :func:`context.load_context`
and returns the same ``state`` enriched with ``final`` (the letter text) and ``needs_review`` (the
"safety" Checkpoint 2 condition, surfaced as a flag rather than a hard block). Persistence to
``generated_documents`` is the service layer's job.
"""

from typing import Any, Dict

from . import nodes_shared as shared
from . import nodes_cover_letter as cl
from . import latex
from .orchestrator import Checkpoint, MAX_REVISIONS, COVER_SCORE_THRESHOLD, COVER_MIN_WORDS


def _apply_angle_decision(state: Dict[str, Any], cp: Checkpoint) -> None:
    """Fold a Checkpoint-1 decision into the strategy before any prose is written."""
    if cp.decision == "reject":
        return  # proceed with the current angle; the user can edit the final draft
    edits = cp.edits or {}
    strategy = state.get("strategy") or {}
    if edits.get("thesis"):
        strategy["thesis"] = edits["thesis"]
    if edits.get("hooks"):
        strategy["hooks"] = edits["hooks"]
    state["strategy"] = strategy


def run(state: Dict[str, Any], orch) -> Dict[str, Any]:
    shared.research_company(state, orch)
    shared.evaluate_fit(state, orch)
    cl.strategize(state, orch)

    # Checkpoint 1 (proactive): approve the angle before prose. Auto-skipped when the graph is
    # non-interactive or the strategist is confident; the orchestrator auto-approves when there
    # is no resume_fn wired.
    strategy = state.get("strategy") or {}
    if state.get("interactive") and strategy.get("confidence", 1.0) < 0.8:
        cp = orch.checkpoint("angle", {
            "thesis": strategy.get("thesis"),
            "hooks": strategy.get("hooks"),
            "evaluation": state.get("evaluation"),
        })
        _apply_angle_decision(state, cp)

    # Enforce the length target only on the LLM path; the deterministic fallback cannot grow, so
    # looping on it would just repeat the same short draft. `base_instructions` is the user's
    # guidance; a length note is appended per-revision without stacking.
    enforce_length = state.get("client") is not None
    base_instructions = state.get("instructions") or ""

    accepted = False
    for revision in range(1, MAX_REVISIONS + 1):
        state["revision"] = revision
        cl.write_letter(state, orch)
        cl.style_letter(state, orch)
        cl.critique_letter(state, orch)
        state["current_document"] = state.get("styled_draft") or state.get("draft") or ""
        shared.truthfulness_check(state, orch)

        critique_ok = (state.get("critique") or {}).get("score", 0) >= COVER_SCORE_THRESHOLD
        truthful_ok = (state.get("truthful") or {}).get("ok", True)
        words = shared.letter_word_count(state["current_document"])
        length_ok = (not enforce_length) or words >= COVER_MIN_WORDS
        if critique_ok and truthful_ok and length_ok:
            accepted = True
            break
        if enforce_length and not length_ok and revision < MAX_REVISIONS:
            note = (f"The previous draft was only {words} words — expand it to a full 300-400 "
                    "words with developed body paragraphs (do not pad with fluff or invent facts).")
            state["instructions"] = (base_instructions + "\n\n" + note).strip()

    state["needs_review"] = not accepted
    # The critic/truthfulness passes scored the plain prose; the persisted document is LaTeX.
    orch.report("render", 94, "Rendering the letter as LaTeX…")
    state["final_text"] = state.get("styled_draft") or state.get("draft") or ""
    state["final"] = latex.build_cover_letter_tex(state)
    state["format"] = "latex"
    orch.report("finalize", 96, "Finalizing the letter…")
    return state
