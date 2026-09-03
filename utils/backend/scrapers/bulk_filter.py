"""
Ad-hoc bulk filtering for the New Jobs feed.

Where :mod:`utils.backend.scrapers.job_filter` re-applies the *saved* rule sets (the
``jobs_config.json`` keep-list and the active profile's blocklists), this module implements the
one-off criteria the **Filter** popup offers, so a feed that has grown to hundreds of rows can be
cut down without editing the profile first:

* **keywords** — a *kill* list: hide a job whose title and/or description contains any term.
  (Note the direction: the saved ``jobs_config`` keywords are a keep-list; these are the opposite.)
* **found_before** — hide jobs first seen before a date. The database stores no board "posted"
  date, only ``Job.created_at`` (surfaced as ``date_found``); each scrape is bounded to recently
  posted listings (``scraper_config.DEFAULT_HOURS_OLD``), so found-date is the available proxy and
  the UI labels it as such.
* **min_match** — hide jobs whose match percentage is below a threshold. The percentage is
  ``round(rag_score * 100)``, exactly what the cards display. Jobs with no analysis have no
  percentage and are kept unless ``hide_unscored`` is set.
* **industries** — hide jobs whose ``industry`` label is in the selected set. The sentinel
  ``"Unclassified"`` selects jobs with no label yet.

Criteria are **OR**-ed: a job is hidden if it matches any enabled criterion. That is what bulk
removal means; AND semantics would routinely hide nothing.

Scope and semantics match every other hide path in the app:

* only currently visible jobs are considered — already-hidden rows are left alone;
* jobs the user explicitly **saved** (``saved=1``) are an intentional keep and are never auto-hidden;
* one-directional — a job is only ever hidden, never un-hidden (``Show Ignored`` is the reverse).
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

# Sentinel industry label meaning "the LLM has not classified this job yet" (``industry`` is NULL).
UNCLASSIFIED = "Unclassified"

# The scopes a keyword term may be matched against.
VALID_SCOPES = ("title", "description")

# Criterion keys, in the order the UI reports them.
CRITERIA = ("keywords", "date", "match", "industry")


def _clean_terms(raw: Any) -> List[str]:
    """Lower-cased, de-duplicated, non-empty strings from a list-ish value."""
    if not isinstance(raw, (list, tuple)):
        return []
    seen, out = set(), []
    for item in raw:
        term = str(item or "").strip().lower()
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _parse_date(raw: Any) -> Optional[date]:
    """Parse a ``YYYY-MM-DD`` string. Blank/None -> None. Anything else -> ValueError."""
    if raw in (None, ""):
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"found_before must be a YYYY-MM-DD date, got {raw!r}")


def normalize_bulk_rules(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate and normalize a rules payload from the client.

    Returns a dict with every key present and normalized:
    ``{keywords, keyword_scopes, found_before, min_match, hide_unscored, industries}``.

    Raises:
        ValueError: if ``found_before`` is present but is not a ``YYYY-MM-DD`` date.
    """
    raw = raw or {}

    scopes = [s for s in _clean_terms(raw.get("keyword_scopes")) if s in VALID_SCOPES]
    if not scopes:
        scopes = list(VALID_SCOPES)

    min_match = raw.get("min_match")
    if min_match in (None, ""):
        min_match = None
    else:
        try:
            min_match = max(0, min(100, int(round(float(min_match)))))
        except (TypeError, ValueError):
            min_match = None

    # Industry labels keep their original casing for display but are compared case-insensitively.
    industries = []
    seen = set()
    for item in raw.get("industries") or []:
        label = str(item or "").strip()
        key = label.lower()
        if label and key not in seen:
            seen.add(key)
            industries.append(label)

    return {
        "keywords": _clean_terms(raw.get("keywords")),
        "keyword_scopes": scopes,
        "found_before": _parse_date(raw.get("found_before")),
        "min_match": min_match,
        "hide_unscored": bool(raw.get("hide_unscored")),
        "industries": industries,
    }


def rules_are_empty(rules: Dict[str, Any]) -> bool:
    """True when no criterion is enabled, so the pass would be a no-op."""
    return not (
        rules.get("keywords")
        or rules.get("found_before")
        or rules.get("min_match") is not None
        or rules.get("industries")
    )


def match_percent(analysis: Optional[Dict[str, Any]]) -> Optional[int]:
    """The match percentage a card displays, or None when the job has never been analyzed."""
    if not analysis:
        return None
    score = analysis.get("rag_score")
    if not isinstance(score, (int, float)):
        return None
    return int(round(score * 100))


def _found_date(job: Dict[str, Any]) -> Optional[date]:
    """The job's found date (``created_at``), as a date."""
    raw = job.get("date_found") or job.get("created_at")
    if not raw:
        return None
    text = str(raw)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def job_matches_bulk_rules(job: Dict[str, Any],
                           analysis: Optional[Dict[str, Any]],
                           rules: Dict[str, Any]) -> List[str]:
    """
    Which criteria this job trips.

    Returns the list of criterion names (subset of :data:`CRITERIA`) the job matches — empty
    when the job survives. Returning the reasons (rather than a bool) lets the popup show a
    per-criterion breakdown of what a pass would remove.
    """
    reasons = []

    terms = rules.get("keywords") or []
    if terms:
        scopes = rules.get("keyword_scopes") or list(VALID_SCOPES)
        haystack = " \n ".join(
            str(job.get(field) or "").lower() for field in scopes
        )
        if any(term in haystack for term in terms):
            reasons.append("keywords")

    cutoff = rules.get("found_before")
    if cutoff:
        found = _found_date(job)
        if found is not None and found < cutoff:
            reasons.append("date")

    threshold = rules.get("min_match")
    if threshold is not None:
        pct = match_percent(analysis)
        if pct is None:
            if rules.get("hide_unscored"):
                reasons.append("match")
        elif pct < threshold:
            reasons.append("match")

    wanted = rules.get("industries") or []
    if wanted:
        label = str(job.get("industry") or "").strip()
        key = label.lower() if label else UNCLASSIFIED.lower()
        if key in {w.lower() for w in wanted}:
            reasons.append("industry")

    return reasons


def apply_bulk_filters(rules: Optional[Dict[str, Any]],
                       job_ids: Optional[List[int]] = None,
                       dry_run: bool = False) -> Dict[str, Any]:
    """
    Evaluate the ad-hoc rules over the visible feed, hiding what matches.

    The same function backs both the popup's live preview and its commit, so the number the user
    is shown can never disagree with the number that is hidden — the only difference is whether
    ``ignore=1`` is written.

    Args:
        rules: raw (un-normalized) rules payload; see :func:`normalize_bulk_rules`.
        job_ids: optional scope. When omitted, every visible job is checked.
        dry_run: when True, nothing is written — only counted.

    Returns:
        ``{checked, matched, hidden, breakdown, dry_run, job_ids}`` where ``breakdown`` counts
        how many of the matched jobs tripped each criterion (a job can trip several), ``hidden``
        is 0 on a dry run, and ``job_ids`` lists the matched jobs.

    Raises:
        ValueError: if the rules payload is malformed (e.g. a bad date).
    """
    from ..database.operations import (
        get_jobs_by_ids, get_all_jobs, get_analysis_for_jobs, set_job_ignore,
    )

    normalized = normalize_bulk_rules(rules)
    empty = {
        "checked": 0, "matched": 0, "hidden": 0, "job_ids": [],
        "breakdown": {name: 0 for name in CRITERIA},
        "dry_run": bool(dry_run),
    }
    if rules_are_empty(normalized):
        return empty

    jobs = get_jobs_by_ids(job_ids) if job_ids else get_all_jobs(include_ignored=False)
    candidates = [j for j in jobs if not j.get("saved") and not j.get("ignore")]

    # One query for every candidate's analysis; the match criterion needs rag_score.
    analyses = {}
    if normalized["min_match"] is not None:
        analyses = get_analysis_for_jobs([j["id"] for j in candidates])

    breakdown = {name: 0 for name in CRITERIA}
    matched_ids = []
    for job in candidates:
        reasons = job_matches_bulk_rules(job, analyses.get(job["id"]), normalized)
        if not reasons:
            continue
        matched_ids.append(job["id"])
        for reason in reasons:
            breakdown[reason] += 1

    hidden = 0
    if not dry_run:
        for job_id in matched_ids:
            if set_job_ignore(job_id, 1):
                hidden += 1

    logger.info(
        "Bulk filter %s: %d matched of %d checked (%s)",
        "preview" if dry_run else "applied", len(matched_ids), len(candidates), breakdown,
    )
    return {
        "checked": len(candidates),
        "matched": len(matched_ids),
        "hidden": hidden,
        "job_ids": matched_ids,
        "breakdown": breakdown,
        "dry_run": bool(dry_run),
    }
