"""
Build a structured user profile from a resume.

Resume input is a PDF, LaTeX (.tex), or Markdown (.md) file. We extract plain text
(pypdf for PDF, light cleanup for tex/md) and then ask the configured LLM to produce
the four profile sections used by the recommendation system:

  * interests_paragraph - open-body paragraph (used by the LLM matching pass)
  * skills              - list of skills (matched against job descriptions)
  * job_titles          - list of search-query titles (drive Find Jobs)
  * keyword_groups      - [{label, terms:[...]}] (AND across groups, OR within)

The LLM step is optional: when no endpoint is configured the caller falls back to an
empty draft the user fills in manually.
"""

import io
import re
from typing import Any, Dict, List

from loguru import logger

# Empty profile skeleton (used as the manual-entry fallback / normalization base).
EMPTY_PROFILE: Dict[str, Any] = {
    "interests_paragraph": "",
    "skills": [],
    "job_titles": [],
    "keyword_groups": [],
}

_BUILD_SYSTEM_PROMPT = (
    "You are a careful resume analyst. Given the plain text of a resume, extract a "
    "structured job-search profile. Respond with ONLY a JSON object, no prose, no code "
    "fences. The JSON must have exactly these keys:\n"
    '  "interests_paragraph": a single cohesive paragraph (3-6 sentences) describing the '
    "candidate's research/job interests, background, and what kind of work they want;\n"
    '  "skills": an array of concise skill strings (tools, languages, methods, domains);\n'
    '  "job_titles": an array of 4-10 realistic job titles to search for;\n'
    '  "keyword_groups": an array of objects, each {"label": str, "terms": [str, ...]}, '
    "grouping the candidate's must-have themes. Treat groups as AND (every group should "
    "match) and terms within a group as OR (any term satisfies the group). For example a "
    'candidate wanting AI work only in healthcare yields two groups: {"label":"AI/ML","terms":'
    '["machine learning","ai","deep learning"]} and {"label":"Domain","terms":["healthcare",'
    '"medicine","clinical"]}.'
)


def extract_resume_text(filename: str, data: bytes) -> str:
    """
    Extract plain text from a resume file's bytes, dispatching on extension.

    Supports .pdf (pypdf), .tex (comment-stripped), and .md / .markdown / .txt (raw).
    """
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf_text(data)
    text = data.decode("utf-8", errors="replace")
    if name.endswith(".tex"):
        return _clean_latex(text)
    return text.strip()


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # imported lazily so non-PDF paths don't need it

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:  # pragma: no cover - malformed page
            logger.warning(f"PDF page extraction failed: {e}")
    return "\n".join(parts).strip()


def _clean_latex(text: str) -> str:
    """Light LaTeX cleanup: drop comment lines and collapse blank runs (keep content)."""
    lines = []
    for line in text.splitlines():
        # Strip unescaped % comments.
        stripped = re.sub(r"(?<!\\)%.*$", "", line)
        lines.append(stripped)
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_profile_from_text(text: str, client) -> Dict[str, Any]:
    """
    Ask the LLM to turn resume text into a structured profile dict.

    ``client`` is any object with a ``chat_json(messages, **kw)`` method (the real
    ``OpenAIClient`` or a test fake). Raises if the LLM call/parse fails; callers
    decide whether to fall back to a manual empty draft.
    """
    messages = [
        {"role": "system", "content": _BUILD_SYSTEM_PROMPT},
        {"role": "user", "content": f"Resume text:\n\n{text}"},
    ]
    raw = client.chat_json(messages)
    return normalize_profile(raw)


def normalize_profile(raw: Any) -> Dict[str, Any]:
    """Coerce arbitrary LLM output into the canonical profile shape with safe defaults."""
    profile = dict(EMPTY_PROFILE)
    if not isinstance(raw, dict):
        return profile

    interests = raw.get("interests_paragraph") or raw.get("interests") or ""
    profile["interests_paragraph"] = interests.strip() if isinstance(interests, str) else ""
    profile["skills"] = _as_str_list(raw.get("skills"))
    profile["job_titles"] = _as_str_list(raw.get("job_titles") or raw.get("titles"))
    profile["keyword_groups"] = _normalize_keyword_groups(raw.get("keyword_groups"))
    return profile


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


def _normalize_keyword_groups(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    groups = []
    for idx, group in enumerate(value):
        if isinstance(group, dict):
            label = str(group.get("label") or f"Group {idx + 1}").strip()
            terms = _as_str_list(group.get("terms") or group.get("keywords"))
        elif isinstance(group, list):  # tolerate a bare list of terms
            label = f"Group {idx + 1}"
            terms = _as_str_list(group)
        else:
            continue
        if terms:
            groups.append({"label": label, "terms": terms})
    return groups
