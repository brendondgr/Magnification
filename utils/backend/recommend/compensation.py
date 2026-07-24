"""
LLM compensation extraction for jobs whose board listing has no parsed salary.

Many LinkedIn postings (and some on other boards) bury pay inside the description prose,
so JobSpy returns no structured salary and the UI shows "Not specified". When the LLM
endpoint is enabled, this module asks the model to pull a concise compensation string out
of each such description, in parallel via ``chat_many``. It returns ``None`` for jobs that
state no pay so we never fabricate numbers.
"""

from typing import Any, Dict, List, Optional, Tuple

# Values that mean "no real compensation" and should be treated as missing.
_EMPTY = {"", "null", "none", "n/a", "na", "not specified", "unspecified"}

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

_COMP_PROMPT = (
    "You extract compensation/salary information from a job description. Respond with ONLY "
    "a JSON object (no prose, no code fences): "
    '{"compensation": "<short pay string, e.g. \'$120,000 - $150,000 a year\' or '
    "'£45/hour'>\"} if the description explicitly states pay, otherwise "
    '{"compensation": null}. Do NOT guess, infer, or estimate — only report figures that '
    "are explicitly written in the text."
)


def needs_compensation(job: Dict[str, Any]) -> bool:
    """True when a job has a description but no usable compensation string."""
    comp = (str(job.get("compensation") or "")).strip().lower()
    desc = (str(job.get("description") or "")).strip()
    return bool(desc) and comp in _EMPTY


def needs_compensation_recovery(job: Dict[str, Any], force: bool = False) -> bool:
    """
    True when LLM compensation recovery should run for a job.

    A job qualifies when it still lacks a usable pay string (:func:`needs_compensation`) **and**
    the LLM has not already been asked for it (``compensation_checked`` is falsy). This stops
    jobs whose descriptions genuinely state no pay — which stay blank forever — from being
    re-queried on every "Analyze Matches"/scrape run. Pass ``force=True`` (a reanalyze) to
    re-attempt regardless of the checked flag.
    """
    if not needs_compensation(job):
        return False
    return force or not job.get("compensation_checked")


def _parse_comp(raw: Any) -> Optional[str]:
    """Coerce arbitrary LLM output into a clean compensation string, or None."""
    if isinstance(raw, dict):
        raw = raw.get("compensation")
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in _EMPTY:
        return None
    return s[:255]


def extract_compensation_llm(jobs: List[Dict[str, Any]], client,
                             max_workers: int = 4, max_chars: int = 6000) -> int:
    """
    Fill in ``compensation`` for jobs that lack it, using the LLM on the description.

    Mutates the provided job dicts in place (only when a value is found) and returns the
    number of jobs updated. ``client`` is any object with ``chat_many``. Only jobs that
    pass :func:`needs_compensation` are sent to the model.
    """
    targets = [j for j in (jobs or []) if needs_compensation(j)]
    if not targets:
        return 0

    message_lists = [
        [
            {"role": "system", "content": _COMP_PROMPT},
            {"role": "user", "content": (j.get("description") or "")[:max_chars]},
        ]
        for j in targets
    ]
    results = client.chat_many(message_lists, max_workers=max_workers, as_json=True)

    updated = 0
    for job, raw in zip(targets, results):
        if raw is None:
            continue
        comp = _parse_comp(raw)
        if comp:
            job["compensation"] = comp
            updated += 1
    return updated


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
