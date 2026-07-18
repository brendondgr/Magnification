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


def guidance_block(instructions: str = "", prior_content: str = "") -> str:
    """
    Build a high-priority guidance preamble for a steered / refine re-run.

    Returns ``""`` when neither is given (so a first-pass generation is unaffected). Used by the
    writer/strategist/planner nodes to fold the user's Application-Mode feedback — and the current
    draft it should build on — into their prompts.
    """
    parts = []
    if (instructions or "").strip():
        parts.append("USER GUIDANCE (highest priority — follow it):\n" + instructions.strip())
    if (prior_content or "").strip():
        parts.append("CURRENT DRAFT to improve (revise it to satisfy the guidance; keep what "
                     "already works, change what the guidance asks):\n" + prior_content.strip()[:4000])
    return ("\n\n".join(parts) + "\n\n") if parts else ""


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
    "You are a cover-letter strategist. Decide the ANGLE before any prose is written, working from "
    "the candidate's STATED interests & goals, their real strengths, and the fit evaluation. Pick "
    "the 2-3 GENUINE connection points between what the candidate actually cares about / has done "
    "and what the role needs — expressed in the candidate's own plain words, NOT in the job "
    "posting's vocabulary or keywords. The candidate's motivation must come from their stated "
    "interests: never invent interests, aspirations, or reasons they want the job, and never "
    "manufacture a reason by echoing a phrase from the job description.\n\n"
    "The angle you pick must set up the house structure the letter will be written in — a strong "
    "hook, a quantified value proposition, a genuine why-this-company, and a clear close — so favor "
    "hooks that can be evidenced with the candidate's real, quantifiable accomplishments. Follow the "
    "DOCUMENT GUIDANCE provided in the user message.\n\n"
    "Return ONLY a JSON object "
    "{\"thesis\": \"<1 plain-language sentence>\", \"hooks\": [\"<connection point>\", ...], "
    "\"confidence\": <number 0-1 for how strong the angle is>}. No prose, no code fences."
)

WRITE_LETTER_PROMPT = (
    "You write a cover letter by filling the slots of a template, in the FIRST PERSON as the "
    "candidate, the way a real person writes about their own work: plain, direct, specific. You are "
    "given the slot names, the angle, competencies to demonstrate, the candidate's stated interests "
    "& real background, and the job posting (as CONTEXT ONLY). The finished letter (all slots "
    "together) must be a substantial 300-400 words of developed paragraphs — not one-liners.\n\n"
    "Write the letter to the DOCUMENT GUIDANCE provided in the user message (its cover-letter "
    "structure and writing rules). Map the structure onto the slots you are given: the hook/opening "
    "slot carries the opening hook, the main body slot(s) carry the value proposition, the "
    "company/interest slot carries why-this-company, and the closing slot carries the close. If "
    "there are fewer slots, fold the parts in without dropping any.\n\n"
    "Hard rules:\n"
    "1. Do NOT quote or closely paraphrase the job posting. Do not echo its distinctive phrases, "
    "jargon, acronyms, or buzzwords back at the reader — describe the work in your own ordinary "
    "words. A reader should not be able to tell which phrases came from the posting.\n"
    "2. Do NOT manufacture motivation by naming a requirement or keyword as the reason you're "
    "interested (never write things like 'the challenge of <posting phrase> is what draws me to "
    "<company>'). State genuine interest ONLY from the candidate's stated interests, in plain "
    "language; if the interests do not cover it, keep the 'why this role' short and honest rather "
    "than inventing enthusiasm.\n"
    "3. Ground every specific claim in the candidate's REAL experience — concrete things they "
    "actually did — not in restating the job's requirement list. Show relevant competence by "
    "pointing to real work; do not merely name a skill or list keywords.\n"
    "4. Never fabricate experience, employers, metrics, or skills.\n"
    "5. Sound like one specific human, not AI. Avoid corporate/AI clichés and filler such as "
    "'passionate about', 'I am particularly drawn to', 'leverage', 'proven track record', 'hit the "
    "ground running', \"today's fast-paced\", 'high-stakes environments', 'excited about the "
    "opportunity', 'I am confident that'. Vary sentence length; do not stack tricolons or "
    "em-dashes.\n"
    "6. SHOW the fit, never assert it. Do not compliment the company or narrate what its work "
    "'shows', 'demonstrates', 'reflects', or 'is a testament to' (never sentences like '<Company>'s "
    "deployment of X shows a clear commitment to Y' — the hiring manager knows their own company, "
    "and it reads as pandering). Do not declare fit ('I would be a great fit/match because...'). "
    "Instead, connect through the candidate's own life: what they actually build, study, and read "
    "about, flowing naturally into the work this team does — 'I build X and follow Y, which is "
    "exactly the problem your team works on' — so the reader concludes the fit themselves. The "
    "connection must marinate across a sentence or two of real substance, not be bolted on.\n\n"
    "Return ONLY a JSON object mapping each requested slot name to its filled text. No prose, no "
    "code fences."
)

STYLE_PROMPT = (
    "You are a voice editor. Rewrite the letter to match the target writing style (tone, formality, "
    "sentence length, do's and don'ts) WITHOUT changing any factual claim, adding experience, or "
    "altering the structure. Also strip anything that makes it read as AI-generated: lingering "
    "job-posting jargon, buzzwords, and clichés — replace them with plain, natural wording, without "
    "changing the meaning. Preserve the letter's full length (roughly 300-400 words); polish the "
    "voice, do not shorten or compress it. Return ONLY the rewritten letter text — no commentary, "
    "no code fences."
)

CRITIQUE_PROMPT = (
    "You are a demanding cover-letter critic. Score the letter on whether it reads as a specific "
    "real person writing about their own work AND follows the house structure. HEAVILY penalize a "
    "letter that (a) echoes the job posting's distinctive wording, jargon, acronyms, or buzzwords; "
    "(b) reads as AI-generated or generic; (c) manufactures motivation by naming a "
    "requirement/keyword as the reason for interest; or (d) flatters the company or TELLS the fit "
    "instead of showing it — sentences that narrate what the company's work 'shows a clear "
    "commitment to' / 'demonstrates' / 'reflects', or that assert 'I would be a great fit because' "
    "rather than demonstrating the overlap through the candidate's own concrete work and interests. "
    "Also penalize a letter that is MISSING any part "
    "of the structure in the DOCUMENT GUIDANCE (provided in the user message), that opens with a "
    "weak/templated line, or whose value proposition is vague and UNQUANTIFIED. Reward plain, "
    "specific, human writing grounded in the candidate's own experience with concrete, quantified "
    "accomplishments.\n\n"
    "Flag the offending phrases. Return ONLY a JSON object {\"score\": <integer 0-100>, "
    "\"generic_flags\": [\"<quoted phrase>\", ...], \"suggestions\": [\"<concrete fix>\", ...]}. "
    "No prose, no code fences."
)

AUDIT_FLOW_PROMPT = (
    "You are a forced-fit detector for cover letters. Read the letter sentence by sentence and flag "
    "every place where the candidate-to-company connection is TOLD instead of SHOWN — the writing a "
    "hiring manager reads as pandering or copy-pasted:\n"
    "(a) company flattery / narrated virtue: sentences about what the company's work 'shows a clear "
    "commitment to', 'demonstrates', 'reflects', 'is a testament to', or empty praise ('impressive', "
    "'industry-leading', 'aligns perfectly with');\n"
    "(b) asserted fit: 'I would be a great fit/match because ...', 'my skills align with ...' — fit "
    "declared rather than demonstrated through concrete work;\n"
    "(c) forced or spliced transitions: keyword lists posing as motivation ('because of this and "
    "this and this'), abrupt jumps between what the candidate does and what the company does, or "
    "claims that read pasted-in rather than flowing from the surrounding sentences.\n\n"
    "Do NOT flag sentences that already show the connection through the candidate's real work and "
    "interests, and do not flag ordinary courtesies (greeting, thanks, sign-off). If the letter is "
    "clean, return an empty flags list.\n\n"
    "Return ONLY a JSON object {\"flags\": [{\"quote\": \"<the offending sentence, verbatim>\", "
    "\"problem\": \"<which failure and why>\", \"fix\": \"<how to rewrite it as a shown, flowing "
    "connection>\"}, ...]}. No prose, no code fences."
)

REWRITE_FLOW_PROMPT = (
    "You are a line editor fixing the flagged sentences of a cover letter. You are given the "
    "letter, a list of flagged sentences (each with the problem and a fix direction), and the "
    "candidate's real background and stated interests. Rewrite the letter so that every flagged "
    "sentence is replaced by a SHOWN connection: state what the candidate actually builds, studies, "
    "or follows, and let that flow into the work this team does, so the reader concludes the fit "
    "themselves — never compliment the company, never narrate what its work 'shows' or "
    "'demonstrates', never declare 'I would be a great fit'. Weave each fix into the surrounding "
    "sentences so the paragraph reads as one continuous thought, not a patch.\n\n"
    "Change ONLY what the flags require (plus the minimal surrounding wording needed for flow). "
    "Keep everything else — facts, structure, paragraphing, voice, and length (roughly 300-400 "
    "words) — exactly as it is. Never fabricate experience, metrics, or interests: ground every "
    "rewritten claim in the candidate material provided. Return ONLY the rewritten letter text — "
    "no commentary, no code fences."
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


def normalize_flow_audit(raw: Any) -> Dict[str, Any]:
    """Coerce the forced-fit audit to ``{"flags": [{"quote", "problem", "fix"}, ...]}``.

    A malformed audit degrades to no flags (the flow pass then leaves the letter alone) rather
    than triggering a rewrite from garbage.
    """
    raw = raw if isinstance(raw, dict) else {}
    flags: List[Dict[str, str]] = []
    raw_flags = raw.get("flags")
    for f in (raw_flags if isinstance(raw_flags, list) else []):
        if isinstance(f, dict) and _as_str(f.get("quote")):
            flags.append({
                "quote": _as_str(f.get("quote")),
                "problem": _as_str(f.get("problem")),
                "fix": _as_str(f.get("fix")),
            })
        elif isinstance(f, str) and f.strip():
            flags.append({"quote": f.strip(), "problem": "", "fix": ""})
    return {"flags": flags}


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
