"""
Idempotent day-one seeding for the Agentic Document System (design §1.4).

Ships starter records so the Profile & Documents sidebar is useful immediately and
uploads can overwrite them. Called from ``init_database()`` after migrations. Every
insert is guarded ("insert only if empty / no active row"), so it is safe to run on
every startup and never duplicates or clobbers user edits.
"""

from loguru import logger

from . import documents_ops as docs_ops


# ---- Cover-letter templates (slots: {{hook}}, {{why_them}}, {{why_you}}, {{close}}) ----

_CLASSIC = """Dear {{hiring_manager}},

{{hook}}

{{why_them}}

{{why_you}}

{{close}}

Sincerely,
{{candidate_name}}
"""

_NARRATIVE = """Dear {{hiring_manager}},

{{hook}}

{{story}}

{{why_you}}

{{why_them}}

{{close}}

Warm regards,
{{candidate_name}}
"""

_REFERRAL = """Dear {{hiring_manager}},

{{referral_intro}}

{{hook}}

{{why_you}}

{{why_them}}

{{close}}

Best,
{{candidate_name}}
"""

_RESUME_SKELETON = """# {{candidate_name}}
{{contact_line}}

## Summary
{{summary}}

## Experience
{{experience}}

## Skills
{{skills}}

## Education
{{education}}
"""

_EVAL_RUBRIC = """# Application-Fit Rubric

Evaluate how well the candidate fits THIS job for the purpose of *applying* (distinct
from the recommendation match score). Produce:

- **verdict** — one line: strong fit / stretch / reach / poor fit, with a clause of why.
- **fit_score** — 0-100 application-fit.
- **emphasize** — 2-4 candidate strengths this JD most rewards (say them in the letter).
- **gaps** — requirements the candidate under-covers (address or reframe, never fabricate).
- **risks** — anything that could read as a red flag (gaps, seniority mismatch, location).
- **talking_points** — 2-3 concrete candidate↔role hooks worth building the letter around.

Ground every point in the résumé/profile; do not invent experience.
"""

_TEMPLATES = [
    {"kind": "cover_letter", "name": "Classic", "body": _CLASSIC, "format": "markdown", "is_default": 1},
    {"kind": "cover_letter", "name": "Narrative", "body": _NARRATIVE, "format": "markdown", "is_default": 0},
    {"kind": "cover_letter", "name": "Referral", "body": _REFERRAL, "format": "markdown", "is_default": 0},
    {"kind": "resume", "name": "ATS Skeleton", "body": _RESUME_SKELETON, "format": "markdown", "is_default": 1},
    {"kind": "job_evaluation", "name": "Default Rubric", "body": _EVAL_RUBRIC, "format": "markdown", "is_default": 1},
]

_EXAMPLE_BEHAVIORAL = {
    "name": "default",
    "traits": {
        "dominance": "moderate",
        "influence": "high",
        "steadiness": "moderate",
        "conscientiousness": "high",
    },
    "strengths": [
        "Clear written communication",
        "Structured problem-solving",
        "Collaborative ownership",
        "Bias toward shipping",
    ],
    "work_style_paragraph": (
        "Works best with a clear goal and the autonomy to reach it. Communicates decisions "
        "in writing, breaks ambiguous problems into concrete steps, and prefers to ship a "
        "reviewable increment over a perfect plan. Collaborates openly and takes ownership "
        "end-to-end."
    ),
}

_EXAMPLE_WRITING_STYLE = {
    "name": "default",
    "tone": "warm-professional",
    "formality": "semi-formal",
    "sentence_length": "medium, varied",
    "sample_text": (
        "I have spent the last three years turning messy, half-instrumented systems into ones "
        "a team can reason about. The part I enjoy most is the handoff: writing the doc that "
        "lets the next person move without me in the room."
    ),
    "dos": [
        "Lead with a concrete hook tied to the role",
        "Back every claim with specific evidence",
        "Keep it to one page",
        "Mirror the job description's language",
    ],
    "donts": [
        "Generic openers ('I am writing to apply for...')",
        "Unverifiable superlatives",
        "Buzzword stacking",
        "Repeating the résumé verbatim",
    ],
}


def seed_documents_if_empty() -> None:
    """Insert the §1.4 starter records only where nothing exists yet. Idempotent."""
    try:
        if not docs_ops.list_templates():
            for tpl in _TEMPLATES:
                docs_ops.create_template(tpl)
            logger.info(f"Seeded {len(_TEMPLATES)} document templates.")

        if docs_ops.get_active_behavioral_profile() is None:
            docs_ops.upsert_active_behavioral_profile(_EXAMPLE_BEHAVIORAL)
            logger.info("Seeded example behavioral profile.")

        if docs_ops.get_active_writing_style() is None:
            docs_ops.upsert_active_writing_style(_EXAMPLE_WRITING_STYLE)
            logger.info("Seeded example writing-style profile.")
    except Exception as e:  # pragma: no cover - seeding must never block startup
        logger.error(f"Document seeding skipped due to error: {e}")
