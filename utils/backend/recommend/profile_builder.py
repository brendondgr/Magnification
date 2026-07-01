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

# Valid keyword-group scopes and the default (both) applied when a group omits them.
VALID_SCOPES = ("title", "description")
DEFAULT_SCOPES = list(VALID_SCOPES)

# Empty profile skeleton (used as the manual-entry fallback / normalization base).
EMPTY_PROFILE: Dict[str, Any] = {
    "interests_paragraph": "",
    "skills": [],
    "job_titles": [],
    "keyword_groups": [],
    "blocked_companies": [],
    "title_blocklist": [],
    "llm_instructions": "",
}

_BUILD_SYSTEM_PROMPT = (
    "You are a careful resume analyst. Given the plain text of a resume, extract a "
    "structured job-search profile. If the user provides explicit instructions about what "
    "they are looking for, treat those instructions as the highest priority and let them "
    "override or refine what the resume alone would suggest (e.g. which job titles, search "
    "queries, skills to emphasize, and how to frame the interests). Respond with ONLY a JSON "
    "object, no prose, no code fences. The JSON must have exactly these keys:\n"
    '  "interests_paragraph": a single cohesive paragraph (3-6 sentences) describing the '
    "candidate's research/job interests, background, and what kind of work they want;\n"
    '  "skills": an array of concise skill strings (tools, languages, methods, domains);\n'
    '  "job_titles": an array of 4-10 realistic job titles to search for;\n'
    '  "keyword_groups": an array of objects, each {"label": str, "terms": [str, ...], '
    '"scopes": [str, ...]}, grouping the candidate\'s must-have themes. Treat groups as AND '
    "(every group should match) and terms within a group as OR (any term satisfies the group). "
    '"scopes" is a subset of ["title","description"] saying WHERE the group\'s terms must appear: '
    'use ["title"] for role/seniority words that belong in the job title itself (e.g. a group '
    'requiring "intern" or "research" in the title), and ["title","description"] (the default '
    "when unsure) for domain/skill themes that may appear anywhere. For example a candidate "
    'wanting AI work only in healthcare yields {"label":"AI/ML","terms":["machine learning",'
    '"ai","deep learning"],"scopes":["title","description"]} and {"label":"Domain","terms":'
    '["healthcare","medicine","clinical"],"scopes":["title","description"]};\n'
    '  "title_blocklist": an array of lowercase words that, if present in a job TITLE, should '
    "exclude that job. Populate this from the user's instructions about roles to avoid (e.g. "
    '"no senior or management roles" -> ["senior","staff","principal","manager","director",'
    '"lead"]). Use an empty array [] when nothing should be excluded;\n'
    '  "blocked_companies": an array of company names to always hide. ONLY include a company '
    "when the user's instructions EXPLICITLY name companies to block or avoid; otherwise return "
    "an empty array []. Never guess, infer, or invent company names."
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


def build_profile_from_text(text: str, client, instructions: str = "") -> Dict[str, Any]:
    """
    Ask the LLM to turn resume text into a structured profile dict.

    ``client`` is any object with a ``chat_json(messages, **kw)`` method (the real
    ``OpenAIClient`` or a test fake). ``instructions`` is optional free-text guidance from the
    user (what roles/skills to emphasize, what to avoid); when present it is injected ahead of
    the resume as a high-priority instruction so the generated sections reflect the user's
    intent, not just the resume. Raises if the LLM call/parse fails; callers decide whether to
    fall back to a manual empty draft.
    """
    guidance = (instructions or "").strip()
    user_content = (
        f"User instructions (prioritize these):\n{guidance}\n\nResume text:\n\n{text}"
        if guidance else f"Resume text:\n\n{text}"
    )
    messages = [
        {"role": "system", "content": _BUILD_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
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
    profile["blocked_companies"] = _as_str_list(raw.get("blocked_companies"))
    profile["title_blocklist"] = _as_str_list(raw.get("title_blocklist"))
    return profile


def _normalize_scopes(value: Any) -> List[str]:
    """Coerce a group's scopes into an ordered subset of {'title','description'}.

    Missing/empty/invalid input defaults to both scopes so an under-specified group never
    silently blocks everything.
    """
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return list(DEFAULT_SCOPES)
    out = [s for s in VALID_SCOPES if s in {str(v).strip().lower() for v in value}]
    return out or list(DEFAULT_SCOPES)


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
            scopes = _normalize_scopes(group.get("scopes"))
        elif isinstance(group, list):  # tolerate a bare list of terms
            label = f"Group {idx + 1}"
            terms = _as_str_list(group)
            scopes = list(DEFAULT_SCOPES)
        else:
            continue
        if terms:
            groups.append({"label": label, "terms": terms, "scopes": scopes})
    return groups
