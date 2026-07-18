"""
Nodes shared by both generation graphs: company research, the Job Evaluator, and the
truthfulness/grounding check.

``research_company`` and ``evaluate_fit`` front both graphs (design §2.1). ``evaluate_fit`` is the
"job evaluation system" — a richer, application-oriented read than ``JobAnalysis`` — seeded from the
already-computed ``skill_match`` + ``llm_rationale`` and persisted to ``job_evaluations``.

Every node follows the project's no-LLM contract: when ``state["client"]`` is ``None`` it produces a
deterministic fallback (for ``evaluate_fit``, the ``JobAnalysis`` seed) instead of raising.
"""

import json
import re
from typing import Any, Dict, List

from loguru import logger

from ..database import documents_ops as docs_ops
from ..recommend import ranker
from . import prompts


def _chat_json(client, system: str, user: str) -> Any:
    return client.chat_json([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


def _chat_text(client, system: str, user: str, **overrides) -> str:
    return client.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], **overrides)


def profile_summary(profile: Dict[str, Any]) -> str:
    """Flatten the profile into a compact query string (reusing the ranker's builder)."""
    return ranker.build_profile_query(profile or {})[:2000]


def guidance_preamble(state: Dict[str, Any]) -> str:
    """The user-editable Document Guidance, as a labelled preamble for a generation node's user
    message. Returns ``""`` when no guidance is present. Injected at call time (not baked into the
    prompt constants) so a user's edit takes effect on the very next generation or refine."""
    guidance = (state.get("guidance") or "").strip()
    if not guidance:
        return ""
    return ("DOCUMENT GUIDANCE (the house style to follow — the user maintains this; obey it):\n"
            + guidance + "\n\n")


def letter_word_count(text: str) -> int:
    """Word count of letter prose, excluding the salutation/signature scaffold lines.

    Used by the revision loop and critic to judge whether a cover letter reached its target
    length. Strips ``{{slot}}`` markers so an unfilled template body counts as empty.
    """
    body = re.sub(r"\{\{\s*\w+\s*\}\}", " ", text or "")
    return len(body.split())


def candidate_facts(profile: Dict[str, Any]) -> str:
    """
    A labelled, ground-truth block of the candidate's OWN words for the writer/strategist.

    Unlike :func:`profile_summary` (a flattened query string for embedding), this keeps the
    profile's *stated interests* distinct and prominent so the letter argues motivation from what
    the user actually wrote — not invented aspirations. Only real, present fields are included.
    """
    profile = profile or {}
    parts: List[str] = []
    interests = (profile.get("interests_paragraph") or "").strip()
    if interests:
        parts.append("Candidate's stated interests & goals (use ONLY these for motivation — do "
                     "not invent interests):\n" + interests)
    skills = [s for s in (profile.get("skills") or []) if s]
    if skills:
        parts.append("Skills: " + ", ".join(str(s) for s in skills[:30]))
    titles = [t for t in (profile.get("job_titles") or []) if t]
    if titles:
        parts.append("Target roles: " + ", ".join(str(t) for t in titles[:8]))
    resume = (profile.get("resume_text") or "").strip()
    if resume:
        parts.append("Résumé (source of truth for experience):\n" + resume[:2500])
    return "\n\n".join(parts)


# ==================== research_company ====================

def research_company(state: Dict[str, Any], orch) -> None:
    job = state["job"]
    orch.report("research", 20, f"Researching {job.get('company') or 'the company'}…")
    research = {"mission": "", "values": [], "angle": ""}
    client = state.get("client")
    if client:
        try:
            user = (f"Company: {job.get('company', '')}\n\n"
                    f"Job description:\n{(job.get('description') or '')[:4000]}")
            research = prompts.normalize_research(
                _chat_json(client, prompts.RESEARCH_COMPANY_PROMPT, user))
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"research_company failed: {e}")
    if not research["angle"]:
        research["angle"] = (f"the work {job.get('title') or 'this role'} focuses on at "
                             f"{job.get('company') or 'your team'}")
    state["research"] = research


# ==================== evaluate_fit (the Job Evaluator) ====================

def _seed_evaluation(state: Dict[str, Any]) -> Dict[str, Any]:
    """A cheap first-pass evaluation from the stored ``JobAnalysis`` (design §2.2)."""
    analysis = state.get("analysis") or {}
    skill_match = analysis.get("skill_match") or {}
    matched = skill_match.get("matched") or []
    missing = skill_match.get("missing") or []
    rag = analysis.get("rag_score")
    llm_score = analysis.get("llm_score")
    fit = llm_score if llm_score is not None else (round(rag * 100, 1) if rag is not None else None)
    return {
        "verdict": analysis.get("llm_rationale") or "",
        "fit_score": fit,
        "emphasize": list(matched[:4]),
        "gaps": list(missing[:6]),
        "risks": "",
        "talking_points": list(matched[:3]),
    }


def _merge_eval(seed: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer the LLM's fields, falling back to the seed for anything it left empty."""
    out = dict(seed)
    for key in ("verdict", "risks"):
        if llm.get(key):
            out[key] = llm[key]
    for key in ("emphasize", "gaps", "talking_points"):
        if llm.get(key):
            out[key] = llm[key]
    if llm.get("fit_score"):  # 0.0/None → keep the seed's score
        out["fit_score"] = llm["fit_score"]
    return out


def evaluate_fit(state: Dict[str, Any], orch) -> None:
    orch.report("evaluate", 35, "Evaluating application fit…")
    seed = _seed_evaluation(state)
    evaluation = dict(seed)
    client = state.get("client")
    if client:
        try:
            job = state["job"]
            user = (f"Candidate profile:\n{profile_summary(state.get('profile'))}\n\n"
                    f"Job: {job.get('title', '')} at {job.get('company', '')}\n"
                    f"{(job.get('description') or '')[:4000]}\n\n"
                    f"Already matched skills: {', '.join(seed['emphasize']) or 'none'}\n"
                    f"Already missing skills: {', '.join(seed['gaps']) or 'none'}")
            llm_eval = prompts.normalize_evaluation(
                _chat_json(client, prompts.EVALUATE_FIT_PROMPT, user))
            evaluation = _merge_eval(seed, llm_eval)
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"evaluate_fit failed: {e}")
    state["evaluation"] = evaluation

    # Persist the application-fit read (seeded from JobAnalysis, refined by the LLM).
    try:
        profile = state.get("profile") or {}
        docs_ops.save_job_evaluation(state["job"]["id"], {
            "verdict": evaluation["verdict"],
            "fit_score": evaluation["fit_score"],
            "emphasize": evaluation["emphasize"],
            "gaps": evaluation["gaps"],
            "risks": evaluation["risks"],
            "talking_points": evaluation["talking_points"],
        }, profile_id=profile.get("id"))
    except Exception as e:  # persistence must not sink the graph
        logger.warning(f"persist job_evaluation failed: {e}")


# ==================== truthfulness_check ====================

def truthfulness_check(state: Dict[str, Any], orch) -> None:
    """Grounding check of ``state['current_document']`` against the résumé/profile source.

    Offline (no client) it cannot verify, so it passes with ``verified=False`` — never blocking
    the graph on a check it couldn't run, but signalling that grounding is unverified.
    """
    orch.report("truthfulness", 88, "Checking claims against your résumé…")
    document = state.get("current_document") or ""
    client = state.get("client")
    if not client or not document:
        state["truthful"] = {"ok": True, "issues": [], "verified": False}
        return
    try:
        profile = state.get("profile") or {}
        source = f"{profile.get('resume_text') or ''}\n\n{profile_summary(profile)}"
        user = f"SOURCE:\n{source[:6000]}\n\nDOCUMENT:\n{document[:6000]}"
        state["truthful"] = prompts.normalize_truthfulness(
            _chat_json(client, prompts.TRUTHFULNESS_PROMPT, user))
        state["llm_used"] = True
    except Exception as e:
        logger.warning(f"truthfulness_check failed: {e}")
        state["truthful"] = {"ok": True, "issues": [], "verified": False}


def evaluation_json(evaluation: Dict[str, Any]) -> str:
    """Compact JSON of the evaluation for prompt embedding (bounded length)."""
    return json.dumps(evaluation, ensure_ascii=False)[:2000]
