"""
Prompts + normalizers for the ingestion agent.

Each doc type has a system prompt that asks the LLM for ONLY a JSON object with a
fixed key set, and a ``normalize_*`` helper that coerces arbitrary model output into
the canonical record shape with safe defaults (mirrors ``profile_builder.normalize_profile``).
"""

from typing import Any, Dict, List

# The fixed set of ingestion doc types, plus a free "other/reference → summary-only" bucket.
DOC_TYPES = ("resume", "behavioral", "writing", "reference", "other")


# ---- classification -----------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = (
    "You classify a supporting document for a job-application assistant. Given the "
    "document text, respond with ONLY one lowercase word from this set: resume, "
    "behavioral, writing, reference, other.\n"
    "  resume     — a CV / résumé of the candidate.\n"
    "  behavioral — a work-style / personality assessment (DISC, Predictive Index, "
    "StrengthsFinder, Enneagram, etc.).\n"
    "  writing    — a writing sample / essay whose voice should be imitated.\n"
    "  reference  — a recommendation / reference letter about the candidate.\n"
    "  other      — anything else.\n"
    "Respond with the single word only, no punctuation."
)


# ---- behavioral profile -------------------------------------------------------

BEHAVIORAL_SYSTEM_PROMPT = (
    "You analyze a work-style / behavioral assessment. Respond with ONLY a JSON object, "
    "no prose, no code fences, with exactly these keys:\n"
    '  "traits": an object mapping work-style dimensions to short values '
    '(e.g. {"dominance":"moderate","influence":"high"}); use the assessment\'s own '
    "dimensions when present;\n"
    '  "strengths": an array of concise strength strings the candidate can lean on;\n'
    '  "work_style_paragraph": a single cohesive paragraph (3-5 sentences) describing how '
    "this person works best, to guide the tone and framing of their application documents."
)


# ---- writing style ------------------------------------------------------------

WRITING_SYSTEM_PROMPT = (
    "You analyze a writing sample to capture the author's voice for later imitation. "
    "Respond with ONLY a JSON object, no prose, no code fences, with exactly these keys:\n"
    '  "tone": a short label for the overall tone (e.g. "warm-professional");\n'
    '  "formality": a short formality label (e.g. "semi-formal");\n'
    '  "sentence_length": a short cadence label (e.g. "medium, varied");\n'
    '  "dos": an array of concrete stylistic do\'s that reproduce this voice;\n'
    '  "donts": an array of concrete stylistic don\'ts to avoid;\n'
    '  "sample_text": a short representative excerpt (1-3 sentences) of the strongest writing.'
)


# ---- reference / other --------------------------------------------------------

SUMMARY_SYSTEM_PROMPT = (
    "Summarize the following document for later use as context in a job application. "
    "Write 2-4 sentences capturing who/what it is about and the most useful, concrete "
    "points. Plain prose, no preamble."
)


# ---- normalizers --------------------------------------------------------------

def normalize_behavioral(raw: Any) -> Dict[str, Any]:
    """Coerce LLM output into the behavioral-profile record shape."""
    out = empty_behavioral()
    if not isinstance(raw, dict):
        return out
    traits = raw.get("traits")
    if isinstance(traits, (dict, list)):
        out["traits"] = traits
    out["strengths"] = _as_str_list(raw.get("strengths"))
    para = raw.get("work_style_paragraph") or raw.get("summary") or ""
    out["work_style_paragraph"] = para.strip() if isinstance(para, str) else ""
    return out


def normalize_writing(raw: Any) -> Dict[str, Any]:
    """Coerce LLM output into the writing-style record shape."""
    out = empty_writing()
    if not isinstance(raw, dict):
        return out
    out["tone"] = _as_str(raw.get("tone"))
    out["formality"] = _as_str(raw.get("formality"))
    out["sentence_length"] = _as_str(raw.get("sentence_length"))
    out["sample_text"] = _as_str(raw.get("sample_text"))
    out["dos"] = _as_str_list(raw.get("dos"))
    out["donts"] = _as_str_list(raw.get("donts"))
    return out


def empty_behavioral() -> Dict[str, Any]:
    return {"traits": {}, "strengths": [], "work_style_paragraph": ""}


def empty_writing() -> Dict[str, Any]:
    return {
        "tone": "", "formality": "", "sentence_length": "",
        "sample_text": "", "dos": [], "donts": [],
    }


def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        s = str(item).strip()
        if s:
            out.append(s)
    return out
