"""
Cover-letter graph nodes (design §2): strategize → write → style → critique.

The design bet is to **separate strategy from prose from voice**: the angle (``strategize``) is
decided — and optionally approved — before a word is written (``write_letter``), then the voice
agent (``style_letter``) applies the writing style, and a critic (``critique_letter``) scores the
result. Each node degrades to a deterministic fallback when no LLM endpoint is configured.
"""

from typing import Any, Dict, List

from loguru import logger

from . import prompts
from .nodes_shared import _chat_json, _chat_text, profile_summary, evaluation_json

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
            behavioral = state.get("behavioral") or {}
            user = (f"Application-fit evaluation:\n{evaluation_json(evaluation)}\n\n"
                    f"Candidate work-style: {behavioral.get('work_style_paragraph', '')}\n"
                    f"Strengths: {', '.join(behavioral.get('strengths') or [])}")
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
    job = state["job"]
    strategy = state.get("strategy") or {}
    evaluation = state.get("evaluation") or {}
    research = state.get("research") or {}
    hooks: List[str] = strategy.get("hooks") or evaluation.get("emphasize") or []
    role = job.get("title") or "this role"
    company = job.get("company") or "your team"
    mapping = {
        "hook": f"I'm excited to apply for {role} at {company}. {strategy.get('thesis', '')}".strip(),
        "why_them": f"What draws me to {company} is {research.get('angle') or 'the focus of this role'}.",
        "why_you": (("I bring " + ", ".join(hooks[:3]) + ".") if hooks
                    else "I bring directly relevant experience to what this role needs."),
        "close": (f"I would welcome the chance to discuss how I can contribute to {company}. "
                  "Thank you for your consideration."),
        "story": (hooks[0] if hooks else "My background maps closely to what this role needs."),
        "referral_intro": f"I was excited to see the {role} opening at {company}.",
    }
    return mapping.get(slot, "")


def write_letter(state: Dict[str, Any], orch) -> None:
    orch.report("write", 60, "Writing the draft…")
    template = state.get("template") or {}
    body = template.get("body") or _DEFAULT_LETTER_BODY
    slots = prompts.find_slots(body)

    values = _context_slot_values(state)
    prose_slots = [s for s in slots if s not in _CONTEXT_SLOTS]

    filled: Dict[str, str] = {}
    client = state.get("client")
    if client and prose_slots:
        try:
            strategy = state.get("strategy") or {}
            evaluation = state.get("evaluation") or {}
            research = state.get("research") or {}
            job = state["job"]
            user = (f"Template slots to fill: {prose_slots}\n\n"
                    f"Thesis: {strategy.get('thesis', '')}\n"
                    f"Hooks: {strategy.get('hooks')}\n"
                    f"Emphasize: {evaluation.get('emphasize')}\n"
                    f"Company angle: {research.get('angle', '')}\n\n"
                    f"Candidate profile:\n{profile_summary(state.get('profile'))}\n\n"
                    f"Job: {job.get('title', '')} at {job.get('company', '')}\n"
                    f"{(job.get('description') or '')[:3000]}")
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

def _describe_style(writing: Dict[str, Any]) -> str:
    parts = []
    for key in ("tone", "formality", "sentence_length"):
        if writing.get(key):
            parts.append(f"{key.replace('_', ' ')}: {writing[key]}")
    if writing.get("dos"):
        parts.append("do: " + "; ".join(writing["dos"]))
    if writing.get("donts"):
        parts.append("don't: " + "; ".join(writing["donts"]))
    if writing.get("sample_text"):
        parts.append(f"sample of the target voice:\n{writing['sample_text'][:800]}")
    return "\n".join(parts) or "warm-professional, specific, concise"


def style_letter(state: Dict[str, Any], orch) -> None:
    orch.report("style", 75, "Matching your writing voice…")
    draft = state.get("draft") or ""
    styled = draft
    client = state.get("client")
    if client and draft:
        try:
            user = f"Target writing style:\n{_describe_style(state.get('writing') or {})}\n\nLetter:\n{draft}"
            out = _chat_text(client, prompts.STYLE_PROMPT, user, max_tokens=1200)
            if out and out.strip():
                styled = out.strip()
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"style_letter failed: {e}")
    state["styled_draft"] = styled


# ==================== critique ====================

def _heuristic_critique(letter: str) -> Dict[str, Any]:
    """Offline critic: penalize clichés + too-short letters. Passes a clean draft on rev 1."""
    low = (letter or "").lower()
    flags = [c for c in _CLICHES if c in low]
    score = 85.0 - 10.0 * len(flags) - (15.0 if len(low) < 200 else 0.0)
    return {"score": max(40.0, score), "generic_flags": flags, "suggestions": []}


def critique_letter(state: Dict[str, Any], orch) -> None:
    orch.report("critique", 85, "Critiquing the draft…")
    letter = state.get("styled_draft") or state.get("draft") or ""
    client = state.get("client")
    if not client:
        state["critique"] = _heuristic_critique(letter)
        return
    try:
        job = state["job"]
        user = f"Job description:\n{(job.get('description') or '')[:3000]}\n\nLetter:\n{letter}"
        state["critique"] = prompts.normalize_critique(
            _chat_json(client, prompts.CRITIQUE_PROMPT, user))
        state["llm_used"] = True
    except Exception as e:
        logger.warning(f"critique_letter failed: {e}")
        state["critique"] = _heuristic_critique(letter)
