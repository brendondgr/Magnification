"""
The editable **Document Guidance** — a single, user-editable house-style document that steers BOTH
the cover-letter and résumé generation graphs.

This replaces the previously hard-coded ``cover_letter_skill`` constant and the removed
Behavioral / Writing / Templates subsystems: instead of three separate DB-backed inputs, one plain
guidance document is the single source of truth for how generated documents should be structured
and written. It is injected into every generation node at call time, so a user edit takes effect on
the very next generation — first pass or Application-Mode refine alike.

The default (``DEFAULT_GUIDANCE``) ships the proven structure — the cover-letter *Winning Formula*
plus truth-preserving résumé-tailoring principles — and is the "Reset to default" baseline. Edits
persist to a gitignored ``config/document_guidance.json`` resolved through the shared project root
(same rule as the other ``config/*.json``), so the main checkout and every git worktree read one
document.
"""

import json
import os
from typing import Dict

from loguru import logger

from ..paths import get_project_root

# Shared root across the main checkout and every git worktree; see utils/backend/paths.py.
CONFIG_PATH = str(get_project_root() / "config" / "document_guidance.json")


# The reset baseline. One shared document with a clearly-labelled section per document kind; each
# generation graph is told which section applies, but the whole document is available to both.
DEFAULT_GUIDANCE = """\
# Document Guidance

This is the house style for every cover letter and résumé generated for you. Edit it to change how
your documents are written — it is referenced on every generation and every refinement.

## COVER LETTER — the Winning Formula

Follow this four-part structure (one page, ~350 words, 3-4 paragraphs):

1. OPENING HOOK (1 short paragraph): grab attention immediately and name the specific role. Lead
   with a concrete achievement, a genuine connection, or a referral — never "I am writing to apply
   for...". Show real, specific enthusiasm for THIS role.
2. VALUE PROPOSITION (2 paragraphs — the core): match real experience to what the role needs. Give
   specific, QUANTIFIED accomplishments (numbers, scale, outcomes) and show you understand the
   problems this team is solving. Most of the words go here.
3. WHY THIS COMPANY (1 paragraph): show genuine, researched interest in this specific employer —
   connect the candidate's stated values/goals to the company's work. Why HERE and why NOW.
4. STRONG CLOSE (1 paragraph): restate interest, make a clear call to action (a conversation), and
   end with forward-looking, confident enthusiasm.

## RÉSUMÉ — tailoring principles

- Mirror the job description's language where it is TRUE — reorder, re-emphasise, and rephrase real
  experience to surface JD-relevant skills. Never invent roles, employers, dates, or achievements.
- QUANTIFY accomplishments with the candidate's real numbers.
- Keep it ATS-clean and concise (ideally one page): plain sections, no tables or columns.
- Surface a skill only if the candidate already has it.

## WRITING RULES (both documents)

- Quantify achievements: "grew sales 45% YoY, adding $2M" beats "increased sales"; use REAL numbers.
- Strong, specific openers only — never "To whom it may concern" or "I believe I would be a great
  fit".
- Show real research; do not fabricate news, funding, or product facts.
- Avoid the classic mistakes: do not just restate the résumé; do not be generic; focus on what the
  candidate OFFERS; keep it to one page; stay positive; never misstate the company name.
- Sound like one specific human, not AI: no buzzword stacking, no clichés, vary sentence length.
"""


def default_guidance() -> str:
    """Return the built-in default guidance (the Reset-to-default baseline)."""
    return DEFAULT_GUIDANCE


def get_guidance() -> str:
    """Return the saved guidance if present and non-empty, else the built-in default."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            text = saved.get("guidance") if isinstance(saved, dict) else None
            if isinstance(text, str) and text.strip():
                return text
        except Exception as e:  # pragma: no cover - corrupt file fallback
            logger.error(f"Error loading document guidance: {e}")
    return DEFAULT_GUIDANCE


def set_guidance(text: str) -> bool:
    """Persist edited guidance. An empty/blank string clears the override (reverts to default)."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        payload: Dict[str, str] = {"guidance": text if isinstance(text, str) else ""}
        with open(CONFIG_PATH, "w") as f:
            json.dump(payload, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving document guidance: {e}")
        return False


def reset_guidance() -> bool:
    """Remove the saved override so ``get_guidance()`` returns the built-in default."""
    try:
        if os.path.exists(CONFIG_PATH):
            os.remove(CONFIG_PATH)
        return True
    except Exception as e:
        logger.error(f"Error resetting document guidance: {e}")
        return False


def is_default() -> bool:
    """True when no (non-empty) override is stored — i.e. the default is in effect."""
    return get_guidance() == DEFAULT_GUIDANCE
