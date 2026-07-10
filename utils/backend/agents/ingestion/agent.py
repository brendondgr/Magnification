"""
The ingestion / summarization agent — an in-house (plain-Python) pipeline.

    extract_text  → classify → summarize/normalize → drafted record (NOT persisted)

Reuses the existing résumé machinery (``profile_builder.extract_resume_text`` and
``build_profile_from_text``) and ``OpenAIClient``. Like the résumé builder, it degrades
gracefully when no LLM endpoint is configured: it returns an empty, user-editable draft
with ``llm_used=False`` instead of raising. Nothing is written to the database here — the
caller (the documents blueprint) persists only after the user approves the draft.
"""

from typing import Any, Dict, Optional

from loguru import logger

from ...llm.client import OpenAIClient
from ...recommend.profile_builder import (
    extract_resume_text,
    build_profile_from_text,
    EMPTY_PROFILE,
)
from .prompts import (
    DOC_TYPES,
    CLASSIFY_SYSTEM_PROMPT,
    BEHAVIORAL_SYSTEM_PROMPT,
    WRITING_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    normalize_behavioral,
    normalize_writing,
    empty_behavioral,
    empty_writing,
)

# Map each doc type to the DB table its saved record lands in (None → summary-only).
TARGET_TABLE = {
    "resume": "profiles",
    "behavioral": "behavioral_profiles",
    "writing": "writing_style_profiles",
    "reference": None,
    "other": None,
}

# Filename hints → doc type (fast path before any LLM classification).
_FILENAME_HINTS = (
    (("resume", "cv", "curriculum"), "resume"),
    (("disc", "predictive", "personality", "behavior", "strengthsfinder", "enneagram", "assessment"), "behavioral"),
    (("writing", "sample", "essay", "portfolio"), "writing"),
    (("reference", "recommendation", "letter-of-rec", "letterofrec", "recletter"), "reference"),
)


def _resolve_client(client) -> Optional[OpenAIClient]:
    """Return the injected client, or build one from config; None when no endpoint is enabled."""
    if client is not None:
        return client
    try:
        return OpenAIClient.from_config(require_enabled=True)
    except Exception:
        return None


def classify_document(filename: str, text: str, client=None) -> str:
    """
    Infer the doc type. Filename hints first (deterministic), then the LLM if available,
    else ``other``.
    """
    name = (filename or "").lower()
    for needles, doc_type in _FILENAME_HINTS:
        if any(n in name for n in needles):
            return doc_type

    if client is not None and text.strip():
        try:
            out = client.chat(
                [
                    {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": text[:4000]},
                ],
                max_tokens=8,
            )
            guess = (out or "").strip().lower().split()[0] if out else ""
            guess = guess.strip(".,!;:")
            if guess in DOC_TYPES:
                return guess
        except Exception as e:  # pragma: no cover - network/parse errors fall through
            logger.warning(f"LLM classification failed: {e}")
    return "other"


def ingest_document(filename: str, data: bytes, doc_type: Optional[str] = None,
                    client=None) -> Dict[str, Any]:
    """
    Run the ingestion pipeline on an uploaded file's bytes and return a review draft.

    Args:
        filename: original upload filename (drives text extraction + classification hints).
        data: raw file bytes.
        doc_type: caller-supplied type (from the sidebar tab); inferred when absent/invalid.
        client: an object with ``chat``/``chat_json`` (real ``OpenAIClient`` or a test fake);
            built from config when None, or left None when no endpoint is enabled.

    Returns:
        dict: ``{doc_type, target_table, draft, summary, raw_text, llm_used, llm_error}``.
        Nothing is persisted — the caller saves the (possibly user-edited) draft.
    """
    try:
        text = extract_resume_text(filename, data) or ""
    except Exception as e:
        # A malformed/unsupported file must not 500 the ingest — fall back to an empty
        # draft the user can fill in, exactly like the no-LLM path.
        logger.warning(f"Text extraction failed for {filename!r}: {e}")
        text = ""
    client = _resolve_client(client)

    dt = (doc_type or "").strip().lower()
    if dt not in DOC_TYPES:
        dt = classify_document(filename, text, client)

    result: Dict[str, Any] = {
        "doc_type": dt,
        "target_table": TARGET_TABLE.get(dt),
        "draft": _empty_draft(dt, text),
        "summary": "",
        "raw_text": text,
        "llm_used": False,
        "llm_error": None,
    }

    try:
        if dt == "resume":
            if client is not None:
                result["draft"] = build_profile_from_text(text, client)
                result["llm_used"] = True
        elif dt == "behavioral":
            if client is not None:
                result["draft"] = normalize_behavioral(_chat_json(client, BEHAVIORAL_SYSTEM_PROMPT, text))
                result["llm_used"] = True
        elif dt == "writing":
            draft = dict(result["draft"])
            if client is not None:
                draft = normalize_writing(_chat_json(client, WRITING_SYSTEM_PROMPT, text))
                result["llm_used"] = True
            if not draft.get("sample_text"):
                draft["sample_text"] = text[:1500].strip()
            result["draft"] = draft
        else:  # reference / other → summary-only
            if client is not None:
                summary = (_chat_text(client, SUMMARY_SYSTEM_PROMPT, text) or "").strip()
                result["llm_used"] = True
            else:
                summary = text[:800].strip()
            result["summary"] = summary
            result["draft"] = {"summary": summary}
    except Exception as e:
        logger.warning(f"Ingestion summarize failed ({dt}): {e}")
        result["llm_error"] = str(e)
        result["llm_used"] = False
        result["draft"] = _empty_draft(dt, text)
        if dt in ("reference", "other"):
            result["summary"] = text[:800].strip()
            result["draft"] = {"summary": result["summary"]}

    return result


def _chat_json(client, system_prompt: str, text: str) -> Any:
    return client.chat_json([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ])


def _chat_text(client, system_prompt: str, text: str) -> str:
    return client.chat([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ])


def _empty_draft(doc_type: str, text: str) -> Dict[str, Any]:
    """The user-editable empty draft for a doc type (no-LLM / failure fallback)."""
    if doc_type == "resume":
        return dict(EMPTY_PROFILE)
    if doc_type == "behavioral":
        return empty_behavioral()
    if doc_type == "writing":
        draft = empty_writing()
        draft["sample_text"] = text[:1500].strip()
        return draft
    return {"summary": text[:800].strip()}
