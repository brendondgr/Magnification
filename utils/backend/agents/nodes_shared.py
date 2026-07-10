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
from typing import Any, Dict

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
