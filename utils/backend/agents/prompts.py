"""
System prompts, output normalizers, and template-slot helpers for the generation graphs.

Every LLM node pairs a strict "return ONLY JSON / plain text" prompt with a tolerant normalizer,
so malformed model output degrades to a safe shape instead of raising. Kept here (separate from
the node functions) so prose and control flow stay readable, mirroring
``agents/ingestion/prompts.py``.
"""

import re
from typing import Any, Dict, List

# ==================== template-slot rendering ====================

_SLOT_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def find_slots(body: str) -> List[str]:
    """Return the distinct ``{{slot}}`` names in a template body, in first-seen order."""
    seen: List[str] = []
    for m in _SLOT_RE.finditer(body or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill_slots(body: str, values: Dict[str, Any]) -> str:
    """Replace ``{{slot}}`` with ``values[slot]`` (blank for anything unfilled)."""
    def _sub(m):
        return str(values.get(m.group(1), "") or "")
    return _SLOT_RE.sub(_sub, body or "")


# ==================== small coercion helpers ====================

def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value))


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [s.strip() for s in (str(x) for x in value) if s.strip()]


def _as_score(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ==================== cover-letter prompts ====================

RESEARCH_COMPANY_PROMPT = (
    "You research a company for a job applicant. Given the company name and the job description, "
    "infer what the company does and what this role emphasizes. Return ONLY a JSON object "
    '{"mission": "<1 sentence>", "values": ["<value>", ...], "angle": "<1 sentence on the single '
    'most compelling reason a strong candidate would want THIS role at THIS company>"}. '
    "Do not invent specific facts (funding, headcount, news) you cannot infer from the text. "
    "No prose, no code fences."
)

EVALUATE_FIT_PROMPT = (
    "You are an application-fit evaluator (distinct from a recommendation score). Given the "
    "candidate profile, the job description, and the already-computed matched/missing skills, judge "
    "how well the candidate fits THIS job for the purpose of APPLYING. Return ONLY a JSON object "
    '{"verdict": "<one line: strong fit | stretch | reach | poor fit, with a clause of why>", '
    '"fit_score": <integer 0-100>, "emphasize": ["<2-4 strengths this JD rewards>", ...], '
    '"gaps": ["<requirements the candidate under-covers>", ...], "risks": "<red flags, or empty>", '
    '"talking_points": ["<2-3 concrete candidate-to-role hooks>", ...]}. '
    "Ground every point in the profile; never invent experience. No prose, no code fences."
)

STRATEGIZE_PROMPT = (
    "You are a cover-letter strategist. Decide the ANGLE before any prose is written. Given the "
    "application-fit evaluation and the candidate's work-style, pick the 2-3 strongest "
    "candidate-to-role connection points and state a one-sentence thesis the letter will argue. "
    "Return ONLY a JSON object {\"thesis\": \"<1 sentence>\", \"hooks\": [\"<hook>\", ...], "
    "\"confidence\": <number 0-1 for how strong the angle is>}. No prose, no code fences."
)

WRITE_LETTER_PROMPT = (
    "You write a cover letter by filling the slots of a template. You are given the template's "
    "slot names, the thesis + hooks to argue, the candidate profile, and the job. Fill EACH slot "
    "with 1-3 sentences of concrete, specific prose grounded in the candidate's real background — "
    "no fabricated experience, no generic filler. Return ONLY a JSON object mapping each requested "
    "slot name to its filled text. No prose, no code fences."
)

STYLE_PROMPT = (
    "You are a voice editor. Rewrite the letter to match the target writing style (tone, formality, "
    "sentence length, do's and don'ts) WITHOUT changing any factual claim, adding experience, or "
    "altering the structure. Return ONLY the rewritten letter text — no commentary, no code fences."
)

CRITIQUE_PROMPT = (
    "You are a demanding cover-letter critic. Score the letter against the job description on "
    "specificity and persuasiveness, and flag any generic, cliché, or filler sentences. Return "
    'ONLY a JSON object {"score": <integer 0-100>, "generic_flags": ["<quoted phrase>", ...], '
    '"suggestions": ["<concrete fix>", ...]}. No prose, no code fences.'
)

# ==================== résumé prompts ====================

EVALUATE_GAP_PROMPT = (
    "You analyze a résumé against a job description. Identify which JD skills/keywords the résumé "
    "is missing or under-weights relative to what the role asks for. Return ONLY a JSON object "
    '{"missing_skills": ["<skill>", ...], "missing_keywords": ["<term>", ...], '
    '"notes": "<1-2 sentences on where the résumé is thin for THIS role>"}. '
    "No prose, no code fences."
)

PLAN_EDITS_PROMPT = (
    "You plan truth-preserving edits to tailor a résumé to a job, weighting each change by "
    "JD-relevance. Return ONLY a JSON object {\"edits\": [{\"action\": \"rewrite|reorder|cut|add\", "
    "\"target\": \"<bullet or section>\", \"reason\": \"<why, tied to the JD>\"}, ...], "
    "\"cut_count\": <integer number of bullets to cut>}. Never plan to add experience the "
    "candidate does not have. No prose, no code fences."
)

REWRITE_RESUME_PROMPT = (
    "You rewrite a résumé to mirror a job description's language while preserving the truth: you may "
    "reorder, re-emphasize, and rephrase existing experience to surface JD-relevant skills, but you "
    "must NOT invent roles, employers, dates, or accomplishments. Keep it concise (ideally one "
    "page). Return ONLY the rewritten résumé as Markdown — no commentary, no code fences."
)

ATS_FORMAT_PROMPT = (
    "You format a résumé into an ATS-safe skeleton by filling the template's slots. You are given "
    "the slot names and the tailored résumé text. Fill each slot with the appropriate content "
    "(plain text / simple Markdown, no tables or columns). Return ONLY a JSON object mapping each "
    "requested slot name to its text. No prose, no code fences."
)

# ==================== shared ====================

TRUTHFULNESS_PROMPT = (
    "You are a grounding checker. Given a candidate's SOURCE material (résumé text + profile) and a "
    "generated DOCUMENT, decide whether every factual claim in the document is supported by the "
    "source. Return ONLY a JSON object {\"ok\": <true|false>, \"issues\": [\"<unsupported claim>\", "
    "...]}. Be strict: a specific accomplishment, metric, employer, or skill not present in the "
    "source is an issue. No prose, no code fences."
)


# ==================== normalizers ====================

def normalize_research(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "mission": _as_str(raw.get("mission")),
        "values": _as_str_list(raw.get("values")),
        "angle": _as_str(raw.get("angle")),
    }


def normalize_evaluation(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    score = _as_score(raw.get("fit_score"), 0.0)
    return {
        "verdict": _as_str(raw.get("verdict")),
        "fit_score": max(0.0, min(100.0, score)),
        "emphasize": _as_str_list(raw.get("emphasize")),
        "gaps": _as_str_list(raw.get("gaps")),
        "risks": _as_str(raw.get("risks")),
        "talking_points": _as_str_list(raw.get("talking_points")),
    }


def normalize_strategy(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    conf = _as_score(raw.get("confidence"), 0.5)
    return {
        "thesis": _as_str(raw.get("thesis")),
        "hooks": _as_str_list(raw.get("hooks")),
        "confidence": max(0.0, min(1.0, conf)),
    }


def normalize_critique(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    score = _as_score(raw.get("score"), 0.0)
    return {
        "score": max(0.0, min(100.0, score)),
        "generic_flags": _as_str_list(raw.get("generic_flags")),
        "suggestions": _as_str_list(raw.get("suggestions")),
    }


def normalize_truthfulness(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    issues = _as_str_list(raw.get("issues"))
    ok = raw.get("ok")
    if not isinstance(ok, bool):
        ok = not issues
    return {"ok": bool(ok), "issues": issues, "verified": True}


def normalize_gap(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "missing_skills": _as_str_list(raw.get("missing_skills")),
        "missing_keywords": _as_str_list(raw.get("missing_keywords")),
        "notes": _as_str(raw.get("notes")),
    }


def normalize_plan(raw: Any) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    edits: List[Dict[str, str]] = []
    for e in (raw.get("edits") or []):
        if isinstance(e, dict):
            edits.append({
                "action": _as_str(e.get("action")) or "rewrite",
                "target": _as_str(e.get("target")),
                "reason": _as_str(e.get("reason")),
            })
    cut = raw.get("cut_count")
    try:
        cut = int(cut)
    except (TypeError, ValueError):
        cut = sum(1 for e in edits if e["action"] == "cut")
    return {"edits": edits, "cut_count": max(0, cut)}
