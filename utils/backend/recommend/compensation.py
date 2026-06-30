"""
LLM compensation extraction for jobs whose board listing has no parsed salary.

Many LinkedIn postings (and some on other boards) bury pay inside the description prose,
so JobSpy returns no structured salary and the UI shows "Not specified". When the LLM
endpoint is enabled, this module asks the model to pull a concise compensation string out
of each such description, in parallel via ``chat_many``. It returns ``None`` for jobs that
state no pay so we never fabricate numbers.
"""

from typing import Any, Dict, List, Optional

# Values that mean "no real compensation" and should be treated as missing.
_EMPTY = {"", "null", "none", "n/a", "na", "not specified", "unspecified"}

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
