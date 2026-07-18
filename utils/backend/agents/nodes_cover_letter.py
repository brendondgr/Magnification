"""
Cover-letter graph nodes (design §2): strategize → write → style → refine_flow → critique.

The design bet is to **separate strategy from prose from voice**: the angle (``strategize``) is
decided — and optionally approved — before a word is written (``write_letter``), then the voice
agent (``style_letter``) applies the writing style, a flow pass (``refine_flow``) audits and
rewrites forced-fit sentences (company flattery / asserted rather than shown fit), and a critic
(``critique_letter``) scores the result. Each node degrades to a deterministic fallback when no
LLM endpoint is configured.
"""

from typing import Any, Dict

from loguru import logger

from . import prompts
from .nodes_shared import (
    _chat_json, _chat_text, candidate_facts, evaluation_json, guidance_preamble,
)
from .orchestrator import MAX_FLOW_PASSES

# A minimal built-in letter body used only when no cover-letter template exists at all.
_DEFAULT_LETTER_BODY = (
    "Dear {{hiring_manager}},\n\n{{hook}}\n\n{{why_them}}\n\n{{why_you}}\n\n{{close}}\n\n"
    "Sincerely,\n{{candidate_name}}\n"
)

# Slots the graph fills from context (never asked of the LLM).
_CONTEXT_SLOTS = ("candidate_name", "hiring_manager", "company", "contact_line")

_CLICHES = (
    "i am writing to apply", "to whom it may concern", "team player", "hard worker",
    "think outside the box", "perfect fit", "passionate about", "hit the ground running",
)


# ==================== strategize ====================

def strategize(state: Dict[str, Any], orch) -> None:
    orch.report("strategize", 45, "Choosing the angle…")
    evaluation = state.get("evaluation") or {}
    fallback_hooks = evaluation.get("talking_points") or evaluation.get("emphasize") or []
    strategy = {"thesis": "", "hooks": list(fallback_hooks), "confidence": 0.5}

    client = state.get("client")
    if client:
        try:
            user = (guidance_preamble(state) +
                    prompts.guidance_block(state.get("instructions", "")) +
                    f"Application-fit evaluation:\n{evaluation_json(evaluation)}\n\n"
                    f"{candidate_facts(state.get('profile'))}")
            strategy = prompts.normalize_strategy(
                _chat_json(client, prompts.STRATEGIZE_PROMPT, user))
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"strategize failed: {e}")

    if not strategy.get("thesis"):
        top = (strategy.get("hooks") or fallback_hooks or ["your relevant experience"])[0]
        role = state["job"].get("title") or "this role"
        strategy["thesis"] = f"You are a strong match for {role} because of {top}."
    if not strategy.get("hooks"):
        strategy["hooks"] = list(fallback_hooks)[:3]
    state["strategy"] = strategy


# ==================== write ====================

def _context_slot_values(state: Dict[str, Any]) -> Dict[str, str]:
    job = state["job"]
    cand = state.get("candidate") or {}
    return {
        "candidate_name": cand.get("name") or "[Your Name]",
        "hiring_manager": "Hiring Manager",
        "company": job.get("company") or "",
        "contact_line": cand.get("contact") or "",
    }


def _fallback_slot(slot: str, state: Dict[str, Any]) -> str:
    """Deterministic slot text for the no-LLM / endpoint-down path.

    Kept deliberately plain and honest. It must NOT (a) parrot the job posting, (b) manufacture
    motivation ("What draws me to X is <JD phrase>"), or (c) splice the strategist's often
    third-person hooks into first-person prose ("I bring He has…"). Those were the artefacts a
    flaky endpoint shipped. When the LLM is unavailable this is what the user gets, so it errs
    toward generic-but-clean over specific-but-broken; the LLM path supplies the real specificity.
    """
    job = state["job"]
    role = job.get("title") or "this role"
    company = job.get("company") or "your team"
    mapping = {
        "hook": f"I'm applying for the {role} position at {company}.",
        "why_them": ("I'm interested in this role because it lines up with the kind of work I "
                     "want to keep doing and where I believe I can contribute."),
        "why_you": ("In my work I've taken on hands-on technical problems and carried them "
                    "through to working results, and I'd bring that same approach to your team."),
        "close": (f"I'd welcome the chance to talk about how I could contribute to {company}. "
                  "Thank you for your time and consideration."),
        "story": ("A through-line in my background is turning open-ended technical problems into "
                  "systems that actually work."),
        "referral_intro": f"I'm reaching out about the {role} opening at {company}.",
    }
    return mapping.get(slot, "")


def write_letter(state: Dict[str, Any], orch) -> None:
    orch.report("write", 60, "Writing the draft…")
    body = _DEFAULT_LETTER_BODY
    slots = prompts.find_slots(body)

    values = _context_slot_values(state)
    prose_slots = [s for s in slots if s not in _CONTEXT_SLOTS]

    filled: Dict[str, str] = {}
    client = state.get("client")
    if client and prose_slots:
        try:
            strategy = state.get("strategy") or {}
            evaluation = state.get("evaluation") or {}
            job = state["job"]
            # Candidate first (primacy); the JD is context, not a vocabulary to mine. The
            # keyword-derived lists are reframed as competencies to EVIDENCE, not to name — so the
            # letter argues from real experience instead of echoing the posting.
            user = (f"Fill these template slots: {prose_slots}\n\n"
                    f"{candidate_facts(state.get('profile'))}\n\n"
                    f"Angle to take (in plain terms): {strategy.get('thesis', '')}\n"
                    f"Genuine connection points: {strategy.get('hooks')}\n"
                    f"Competencies to DEMONSTRATE through the candidate's real work (show them via "
                    f"concrete experience — do not name them verbatim or copy them as keywords): "
                    f"{evaluation.get('emphasize')}\n\n"
                    f"Job posting for {job.get('title', '')} at {job.get('company', '')} — CONTEXT "
                    f"ONLY, do not copy its wording:\n{(job.get('description') or '')[:1800]}")
            user = (guidance_preamble(state) +
                    prompts.guidance_block(state.get("instructions", ""),
                                           state.get("prior_content", "")) + user)
            raw = _chat_json(client, prompts.WRITE_LETTER_PROMPT, user)
            if isinstance(raw, dict):
                filled = {k: str(v) for k, v in raw.items() if k in prose_slots and v}
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"write_letter failed: {e}")

    for slot in prose_slots:
        if not filled.get(slot):
            filled[slot] = _fallback_slot(slot, state)
    values.update(filled)

    state["draft"] = prompts.fill_slots(body, values)
    state["draft_slots"] = values


# ==================== style ====================

# A fixed, sensible default voice. (The former per-user Writing-Style profile was retired; the
# editable Document Guidance now carries any voice preferences and is applied by the writer.)
_DEFAULT_VOICE = "warm-professional, specific, concise"


def style_letter(state: Dict[str, Any], orch) -> None:
    orch.report("style", 75, "Polishing the voice…")
    draft = state.get("draft") or ""
    styled = draft
    client = state.get("client")
    if client and draft:
        try:
            user = (guidance_preamble(state) +
                    f"Target writing style:\n{_DEFAULT_VOICE}\n\nLetter:\n{draft}")
            out = _chat_text(client, prompts.STYLE_PROMPT, user, max_tokens=1200)
            if out and out.strip():
                styled = out.strip()
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"style_letter failed: {e}")
    state["styled_draft"] = styled


# ==================== flow refinement (the forced-fit fix) ====================

def _format_flags(flags) -> str:
    lines = []
    for i, f in enumerate(flags, 1):
        line = f'{i}. "{f.get("quote", "")}"'
        if f.get("problem"):
            line += f' — problem: {f["problem"]}'
        if f.get("fix"):
            line += f' — fix: {f["fix"]}'
        lines.append(line)
    return "\n".join(lines)


def refine_flow(state: Dict[str, Any], orch) -> None:
    """Audit → rewrite loop that hunts down forced-fit writing (company flattery, asserted fit,
    spliced transitions) and rewrites each flagged sentence into a SHOWN, flowing connection
    grounded in the candidate's real work — the "write and relate it constantly" stage.

    Runs after ``style_letter``; the critic and truthfulness check score its output. Ends early the
    moment an audit comes back clean; a final audit after the last rewrite records the remaining
    flags. Offline (or on any error) it passes the styled draft through untouched.
    """
    orch.report("flow", 80, "Smoothing forced connections…")
    letter = state.get("styled_draft") or state.get("draft") or ""
    flow: Dict[str, Any] = {"passes": 0, "flags": []}
    client = state.get("client")
    if client and letter:
        try:
            for attempt in range(MAX_FLOW_PASSES + 1):
                audit = prompts.normalize_flow_audit(_chat_json(
                    client, prompts.AUDIT_FLOW_PROMPT,
                    guidance_preamble(state) + f"Letter:\n{letter}"))
                state["llm_used"] = True
                flow["flags"] = audit["flags"]
                if not audit["flags"] or attempt == MAX_FLOW_PASSES:
                    break
                orch.report("flow", 80,
                            f"Rewriting {len(audit['flags'])} forced claim(s)…")
                user = (guidance_preamble(state) +
                        f"Flagged sentences to fix:\n{_format_flags(audit['flags'])}\n\n"
                        f"{candidate_facts(state.get('profile'))}\n\n"
                        f"Letter:\n{letter}")
                out = _chat_text(client, prompts.REWRITE_FLOW_PROMPT, user, max_tokens=1200)
                if not (out and out.strip()):
                    break  # a blank rewrite must not eat the letter
                letter = out.strip()
                flow["passes"] += 1
        except Exception as e:
            logger.warning(f"refine_flow failed: {e}")
    state["smoothed_draft"] = letter
    state["flow"] = flow


# ==================== critique ====================

def _heuristic_critique(letter: str) -> Dict[str, Any]:
    """Offline critic: penalize clichés + a nearly-empty draft. Passes a clean draft on rev 1.

    Reports ``word_count`` so callers can see length, but does not fail the offline path for being
    under the 300-400 target — the deterministic fallback cannot lengthen itself, and the length
    target is enforced on the LLM path in the cover-letter graph instead.
    """
    from .nodes_shared import letter_word_count
    low = (letter or "").lower()
    words = letter_word_count(letter)
    flags = [c for c in _CLICHES if c in low]
    score = 85.0 - 10.0 * len(flags) - (15.0 if words < 40 else 0.0)
    return {"score": max(40.0, score), "generic_flags": flags, "suggestions": [],
            "word_count": words}


def critique_letter(state: Dict[str, Any], orch) -> None:
    orch.report("critique", 85, "Critiquing the draft…")
    letter = (state.get("smoothed_draft") or state.get("styled_draft")
              or state.get("draft") or "")
    client = state.get("client")
    if not client:
        state["critique"] = _heuristic_critique(letter)
        return
    try:
        job = state["job"]
        user = (guidance_preamble(state) +
                f"Job description:\n{(job.get('description') or '')[:3000]}\n\nLetter:\n{letter}")
        state["critique"] = prompts.normalize_critique(
            _chat_json(client, prompts.CRITIQUE_PROMPT, user))
        state["llm_used"] = True
    except Exception as e:
        logger.warning(f"critique_letter failed: {e}")
        state["critique"] = _heuristic_critique(letter)
