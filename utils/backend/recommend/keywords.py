"""
LLM-assisted keyword/search generation for the Find Jobs flow.

Given a seed (free text, or the active profile's interests + titles), the LLM proposes:
  * search_terms    - job titles to search for
  * keyword_groups  - [{label, terms:[...]}] (AND across groups, OR within) for filtering
  * job_type        - one of jobspy's types (fulltime/parttime/internship/contract) or null
"""

from typing import Any, Dict, List, Optional

from .profile_builder import _normalize_keyword_groups, _as_str_list

VALID_JOB_TYPES = {"fulltime", "parttime", "internship", "contract"}

_KEYWORDS_PROMPT = (
    "You help configure a job search. Given the seed text describing what the user wants, "
    "respond with ONLY a JSON object (no prose, no code fences) with keys:\n"
    '  "search_terms": array of 3-8 job titles to search job boards for;\n'
    '  "keyword_groups": array of {"label": str, "terms": [str,...]} used to filter results '
    "— treat groups as AND (each must match) and terms within a group as OR. Group the "
    "user's must-have themes (e.g. an AI/ML group AND a Healthcare group);\n"
    '  "job_type": one of "fulltime", "parttime", "internship", "contract", or null if unspecified.'
)


def generate_keywords(seed: str, client) -> Dict[str, Any]:
    """
    Ask the LLM to produce search terms + AND/OR keyword groups + a job type.

    ``client`` is any object with ``chat_json``. Returns a normalized dict; raises on
    call/parse failure so the route can report it.
    """
    messages = [
        {"role": "system", "content": _KEYWORDS_PROMPT},
        {"role": "user", "content": f"Seed:\n{seed}"},
    ]
    raw = client.chat_json(messages)
    return normalize_keywords(raw)


def normalize_keywords(raw: Any) -> Dict[str, Any]:
    """Coerce arbitrary LLM output into {search_terms, keyword_groups, job_type}."""
    if not isinstance(raw, dict):
        return {"search_terms": [], "keyword_groups": [], "job_type": None}
    job_type = raw.get("job_type")
    if isinstance(job_type, str):
        job_type = job_type.strip().lower().replace("-", "").replace(" ", "")
        job_type = job_type if job_type in VALID_JOB_TYPES else None
    else:
        job_type = None
    return {
        "search_terms": _as_str_list(raw.get("search_terms") or raw.get("titles")),
        "keyword_groups": _normalize_keyword_groups(raw.get("keyword_groups")),
        "job_type": job_type,
    }


def seed_from_profile(profile: Optional[Dict[str, Any]]) -> str:
    """Build a seed string from a profile when the caller doesn't supply one."""
    if not profile:
        return ""
    parts: List[str] = []
    if profile.get("interests_paragraph"):
        parts.append(profile["interests_paragraph"])
    if profile.get("job_titles"):
        parts.append("Target titles: " + ", ".join(profile["job_titles"]))
    if profile.get("skills"):
        parts.append("Skills: " + ", ".join(profile["skills"]))
    return "\n".join(parts)
