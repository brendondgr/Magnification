"""
Profile-driven block rules (pure predicates — no DB or model access).

The active profile is the single source of truth for user-defined blocking. Three rules,
any of which hides a job:

  * blocked_companies — the job's company matches (case-insensitive, exact) a blocked entry.
  * title_blocklist   — the job's title contains (case-insensitive substring) a blocked term.
  * keyword_groups    — a hard AND/OR filter with per-group scope: a group is *satisfied* when
                        at least one of its terms appears in at least one of its selected
                        locations ("title" and/or "description"); ALL groups must be satisfied.

These are kept free of I/O so they can be unit-tested and reused by both the scrape-time
filter (``job_filter``) and the retroactive on-demand apply (``job_filter.apply_profile_filters``).
Blocking is one-directional: callers only ever set ``ignore=1`` on a matching job; a job is never
un-hidden here.
"""

from typing import Any, Dict, List, Optional

# Kept in sync with recommend.profile_builder.VALID_SCOPES.
VALID_SCOPES = ("title", "description")


def company_blocked(company: str, blocked_companies: Optional[List[str]]) -> bool:
    """True when ``company`` exactly matches a blocked entry (case-insensitive, trimmed)."""
    if not blocked_companies:
        return False
    c = (company or "").strip().lower()
    if not c:
        return False
    return any(c == str(b).strip().lower() for b in blocked_companies if str(b).strip())


def title_blocked(title: str, title_blocklist: Optional[List[str]]) -> bool:
    """True when ``title`` contains any blocklisted substring (case-insensitive)."""
    if not title_blocklist:
        return False
    t = (title or "").lower()
    if not t:
        return False
    return any(str(term).strip() and str(term).strip().lower() in t for term in title_blocklist)


def _scope_text(title: str, description: str, scopes: Optional[List[str]]) -> str:
    """Concatenate the lowercased text for a group's selected scopes (defaults to both)."""
    selected = [s for s in VALID_SCOPES if not scopes or s in scopes]
    parts = []
    if "title" in selected:
        parts.append(title or "")
    if "description" in selected:
        parts.append(description or "")
    return " ".join(parts).lower()


def group_satisfied(title: str, description: str, group: Dict[str, Any]) -> bool:
    """A group is satisfied when any term appears in any selected scope. Empty group = no constraint."""
    terms = group.get("terms") or []
    if not terms:
        return True
    text = _scope_text(title, description, group.get("scopes"))
    return any(term and str(term).lower() in text for term in terms)


def keyword_groups_satisfied(title: str, description: str,
                             keyword_groups: Optional[List[Dict[str, Any]]]) -> bool:
    """AND across groups: every group must be satisfied (True when there are no groups)."""
    if not keyword_groups:
        return True
    return all(group_satisfied(title, description, g) for g in keyword_groups)


def job_blocked_by_profile(job: Dict[str, Any], profile: Optional[Dict[str, Any]]) -> bool:
    """
    True when the profile's block rules say this job should be hidden.

    ``job`` needs ``title``, ``company``, ``description``. ``profile`` may be None (nothing
    blocked). Company/title blocks short-circuit before the keyword-group AND check.
    """
    if not profile:
        return False
    if company_blocked(job.get("company", ""), profile.get("blocked_companies")):
        return True
    if title_blocked(job.get("title", ""), profile.get("title_blocklist")):
        return True
    if not keyword_groups_satisfied(job.get("title", ""), job.get("description", ""),
                                    profile.get("keyword_groups")):
        return True
    return False
