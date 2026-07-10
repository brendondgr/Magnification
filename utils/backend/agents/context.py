"""
``load_context`` — the graphs' Ingestion layer, which (per design §0) is a **database read**,
not a scrape. By the time the user asks for a document, the scrape+analyze pipeline has already
stored the JD, ``JobAnalysis`` (skill match, keyword hits, LLM fit rationale), and the active
Profile. This assembles all of it, plus the active Behavioral / Writing-Style records and the
chosen template, into the initial ``state`` dict both graphs run over.
"""

from typing import Any, Dict, Optional

from ..database import operations as db_ops
from ..database import documents_ops as docs_ops
from ..llm.client import OpenAIClient
from .orchestrator import GraphError

# Which template kind backs each generation kind.
_TEMPLATE_KIND = {"cover_letter": "cover_letter", "resume": "resume"}


def resolve_client(client=None) -> Optional[OpenAIClient]:
    """Return the injected client, or build one from config; ``None`` when no endpoint is enabled.

    Mirrors ``agents.ingestion.agent._resolve_client`` so every agent shares one no-LLM contract.
    """
    if client is not None:
        return client
    try:
        return OpenAIClient.from_config(require_enabled=True)
    except Exception:
        return None


def candidate_name(profile: Dict[str, Any]) -> str:
    """Best-effort candidate display name from the profile (its label, if the user set one)."""
    name = (profile or {}).get("name") or ""
    name = name.strip()
    if name and name.lower() != "default":
        return name
    return ""


def load_context(job_id: int, kind: str, template_id: Optional[int] = None,
                 client=None, instructions: str = "", prior_content: str = "") -> Dict[str, Any]:
    """
    Build the initial graph state for a job.

    Reads the job, its analysis (with the stored embedding, needed for the résumé match-lift),
    the active profile / behavioral / writing-style records, and the chosen (or default)
    template. ``instructions`` (Application-Mode user guidance) and ``prior_content`` (the current
    draft to build on) steer a refine re-run; both default empty for a first-pass generation.
    Raises :class:`GraphError` if the job does not exist.
    """
    job = db_ops.get_job_by_id(job_id)
    if not job:
        raise GraphError(f"Job {job_id} not found")

    analysis = db_ops.get_analysis_for_jobs([job_id], include_embedding=True).get(job_id) or {}
    profile = db_ops.get_active_profile() or {}
    behavioral = docs_ops.get_active_behavioral_profile() or {}
    writing = docs_ops.get_active_writing_style() or {}

    tpl_kind = _TEMPLATE_KIND.get(kind, "cover_letter")
    template = None
    if template_id is not None:
        template = docs_ops.get_template(template_id)
    if template is None:
        template = docs_ops.get_default_template(tpl_kind)
    template = template or {}

    return {
        "kind": kind,
        "job": job,
        "analysis": analysis,
        "profile": profile,
        "behavioral": behavioral,
        "writing": writing,
        "template": template,
        "candidate": {
            "name": candidate_name(profile),
            "contact": "",
        },
        "client": resolve_client(client),
        "instructions": instructions or "",
        "prior_content": prior_content or "",
        "revision": 0,
        "llm_used": False,
        "needs_review": False,
    }
