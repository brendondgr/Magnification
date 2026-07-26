"""
Description-derived job enrichment: compensation + industry, pulled by one LLM pass.

The board listing is not a reliable source of pay — LinkedIn buries it in the description
prose, and Indeed hands JobSpy NaN amounts that used to format as ``"USDnan - USDnan
hourly"`` — so the **description is the authority**: every job with description text is asked
once (see :func:`needs_compensation_recovery`), in parallel via ``chat_many``. The model
returns ``null`` for postings that state no pay, so we never fabricate numbers, and one
:data:`INDUSTRIES` label per job so the card can color it deterministically.

This module holds the pure extraction layer (predicates, prompt, parsing). The DB-aware
orchestration that both the scrape workflow and "Analyze Matches" share lives in
``utils/backend/recommend/enrichment.py``.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# Values that mean "no real compensation" and should be treated as missing.
_EMPTY = {"", "null", "none", "n/a", "na", "not specified", "unspecified", "nan"}

# A pay string is only real if it contains a digit. Boards (Indeed especially) hand jobspy
# pandas ``NaN`` amounts, and ``float('nan')`` is truthy — so the salary formatter used to
# happily emit "USDnan - USDnan hourly" or "nannan - nannan nan". Anything carrying a bare
# ``nan`` token, or no digits at all, is garbage rather than compensation.
_NAN_TOKEN = re.compile(r"(?<![a-z0-9])nan(?![a-z0-9])", re.IGNORECASE)
_DIGIT = re.compile(r"\d")

# ---------------------------------------------------------------------------
# Industry taxonomy
#
# A FIXED label set is the source of truth for the per-industry card colors: the LLM must
# classify each job into one of these labels so the frontend can map label -> color
# deterministically and consistently (all "Health" jobs share one color, etc.). Anything the
# model returns that isn't a known label (or a known synonym) normalizes to "Other".
# ---------------------------------------------------------------------------
INDUSTRIES: List[str] = [
    "Tech", "Health", "Finance", "Business", "Industrial", "Science",
    "Education", "Government", "Retail", "Media", "Legal", "Energy", "Other",
]

# Lower-cased label / synonym -> canonical label. Keeps classification stable across the
# small wording differences a model produces (e.g. "healthcare" -> "Health").
_INDUSTRY_LOOKUP: Dict[str, str] = {c.lower(): c for c in INDUSTRIES}
_INDUSTRY_LOOKUP.update({
    "technology": "Tech", "software": "Tech", "it": "Tech", "information technology": "Tech",
    "healthcare": "Health", "medical": "Health", "biotech": "Health", "pharma": "Health",
    "pharmaceutical": "Health", "financial": "Finance", "banking": "Finance",
    "insurance": "Finance", "fintech": "Finance", "manufacturing": "Industrial",
    "engineering": "Industrial", "construction": "Industrial", "automotive": "Industrial",
    "aerospace": "Industrial", "research": "Science", "biology": "Science",
    "chemistry": "Science", "physics": "Science", "academia": "Education",
    "academic": "Education", "public sector": "Government", "nonprofit": "Government",
    "non-profit": "Government", "defense": "Government", "consumer": "Retail",
    "ecommerce": "Retail", "e-commerce": "Retail", "hospitality": "Retail",
    "marketing": "Media", "advertising": "Media", "entertainment": "Media",
    "law": "Legal", "utilities": "Energy", "oil": "Energy", "oil and gas": "Energy",
    "renewable": "Energy", "renewables": "Energy",
})

def clean_compensation(value: Any) -> Optional[str]:
    """
    The single normalizer for a pay string: return a usable value, or ``None``.

    Rejects the placeholder words in :data:`_EMPTY`, any string carrying a bare ``nan`` token,
    and any string with no digit in it (which is what a NaN-poisoned salary formats to —
    ``"USDnan - USDnan hourly"``, ``"nannan - nannan nan"``). Every producer and consumer of a
    compensation string routes through here so a malformed value can neither be stored nor be
    mistaken for real pay.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in _EMPTY:
        return None
    if _NAN_TOKEN.search(s) or not _DIGIT.search(s):
        return None
    return s[:255]


def has_compensation(job: Dict[str, Any]) -> bool:
    """True when the job carries a usable pay string."""
    return clean_compensation(job.get("compensation")) is not None


def needs_compensation(job: Dict[str, Any]) -> bool:
    """True when a job has a description but no usable compensation string."""
    desc = (str(job.get("description") or "")).strip()
    return bool(desc) and not has_compensation(job)


def needs_compensation_recovery(job: Dict[str, Any], force: bool = False) -> bool:
    """
    True when LLM compensation extraction should run for a job.

    Compensation is **always** extracted from the description itself, whatever the board
    reported: any job with a description qualifies, as long as the LLM has not already been
    asked (``compensation_checked`` is falsy). Board-supplied salaries are unreliable — Indeed
    in particular hands over NaN amounts — so the description is the authority, and the
    ``compensation_checked`` flag is what keeps this to one call per job rather than one per
    run. Pass ``force=True`` (a reanalyze) to re-attempt regardless of the flag.
    """
    if not (str(job.get("description") or "")).strip():
        return False
    return force or not job.get("compensation_checked")


def _parse_comp(raw: Any) -> Optional[str]:
    """Coerce arbitrary LLM output into a clean compensation string, or None."""
    if isinstance(raw, dict):
        raw = raw.get("compensation")
    return clean_compensation(raw)


# ---------------------------------------------------------------------------
# Combined enrichment: compensation + industry in one LLM pass
#
# Compensation and industry both come from the job description, so a single call pulls both.
# The pass runs for any job that still needs EITHER field (see :func:`needs_enrichment`); a job
# needing both costs one call. Each field is only requested/persisted when its toggle is on, so
# industry still fills when compensation extraction is disabled and vice-versa.
# ---------------------------------------------------------------------------

_ENRICH_PROMPT = (
    "You extract two facts from a job description. Respond with ONLY a JSON object (no prose, "
    "no code fences): "
    '{"compensation": <short pay string, e.g. "$120,000 - $150,000 a year" or "£45/hour", or '
    "null if the description does not explicitly state pay>, "
    '"industry": <ONE label naming the job\'s industry/genre, chosen from EXACTLY this list: '
    + ", ".join(INDUSTRIES)
    + ">}. For compensation, do NOT guess, infer, or estimate — only report figures explicitly "
    "written in the text; use null when none is stated. For industry, always pick the single "
    'best-fitting label from the list (use "Other" only when none fits).'
)


def normalize_industry(raw: Any) -> Optional[str]:
    """Coerce arbitrary LLM output into a canonical industry label, or None.

    Maps known synonyms (e.g. "healthcare" -> "Health"); an unrecognized non-empty value
    falls back to "Other" so a job the model *did* classify still gets a usable label.
    """
    if isinstance(raw, dict):
        raw = raw.get("industry")
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in _EMPTY:
        return None
    return _INDUSTRY_LOOKUP.get(s.lower(), "Other")


def needs_industry(job: Dict[str, Any]) -> bool:
    """True when a job has a description but no industry label yet."""
    industry = (str(job.get("industry") or "")).strip().lower()
    desc = (str(job.get("description") or "")).strip()
    return bool(desc) and industry in _EMPTY


def needs_industry_recovery(job: Dict[str, Any], force: bool = False) -> bool:
    """True when LLM industry classification should run for a job.

    Qualifies when the job still lacks an industry (:func:`needs_industry`) and has not been
    classified before (``industry_checked`` falsy). Pass ``force=True`` to re-attempt regardless.
    """
    if not needs_industry(job):
        return False
    return force or not job.get("industry_checked")


def needs_enrichment(job: Dict[str, Any], comp_on: bool = True,
                     industry_on: bool = True, force: bool = False) -> bool:
    """True when the combined enrichment pass should query this job.

    A job qualifies when an enabled field still needs recovery: compensation (when
    ``comp_on``) or industry (when ``industry_on``).
    """
    return bool(
        (comp_on and needs_compensation_recovery(job, force=force))
        or (industry_on and needs_industry_recovery(job, force=force))
    )


def extract_enrichment_llm(jobs: List[Dict[str, Any]], client, comp: bool = True,
                           industry: bool = True, max_workers: int = 4,
                           max_chars: int = 6000) -> Tuple[int, int]:
    """
    Fill in ``compensation`` and/or ``industry`` for the given jobs using one LLM call each.

    Mutates the provided job dicts in place (only when a value is found) and returns
    ``(compensation_updated, industry_updated)``. ``client`` is any object with ``chat_many``.
    Only fields whose flag is True are written back. Callers select which jobs to pass (e.g. via
    :func:`needs_enrichment`); this issues one call per job in ``jobs``.
    """
    if not jobs or not (comp or industry):
        return (0, 0)

    message_lists = [
        [
            {"role": "system", "content": _ENRICH_PROMPT},
            {"role": "user", "content": (j.get("description") or "")[:max_chars]},
        ]
        for j in jobs
    ]
    results = client.chat_many(message_lists, max_workers=max_workers, as_json=True)

    comp_updated = 0
    industry_updated = 0
    for job, raw in zip(jobs, results):
        if raw is None:
            continue
        if comp:
            pay = _parse_comp(raw)
            if pay:
                job["compensation"] = pay
                comp_updated += 1
        if industry:
            ind = normalize_industry(raw)
            if ind:
                job["industry"] = ind
                industry_updated += 1
    return (comp_updated, industry_updated)
