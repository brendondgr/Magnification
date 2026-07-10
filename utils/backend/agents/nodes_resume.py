"""
Résumé fine-tuner graph nodes (design §3): evaluate_gap → plan_edits → rewrite → ats_format.

The résumé flow is *analysis → rewrite → score → loop*, and its standout property is that the
Critic (in ``resume.run``) reuses Magnification's own recommender to measure improvement
objectively (see ``scoring.py``). These nodes prepare the tailored text; every one is
**truth-preserving** — the fallback path only ever surfaces skills the candidate actually lists,
never invents experience — and degrades deterministically without an LLM.
"""

import json
from typing import Any, Dict, List

from loguru import logger

from . import prompts
from .nodes_shared import _chat_json, _chat_text, profile_summary

_DEFAULT_RESUME_BODY = (
    "# {{candidate_name}}\n{{contact_line}}\n\n## Summary\n{{summary}}\n\n"
    "## Experience\n{{experience}}\n\n## Skills\n{{skills}}\n\n## Education\n{{education}}\n"
)
_RESUME_CONTEXT_SLOTS = ("candidate_name", "contact_line")


# ==================== evaluate_gap ====================

def _seed_gap(state: Dict[str, Any]) -> Dict[str, Any]:
    """Seed the gap from stored recommendation artifacts (design §3.1)."""
    analysis = state.get("analysis") or {}
    missing_skills = list((analysis.get("skill_match") or {}).get("missing") or [])
    # Keyword groups the job did NOT satisfy → under-weighted keywords for this JD.
    satisfied = set(analysis.get("keyword_group_hits") or {})
    missing_keywords: List[str] = []
    for group in (state.get("profile") or {}).get("keyword_groups") or []:
        if group.get("label") not in satisfied:
            missing_keywords.extend(group.get("terms") or [])
    return {"missing_skills": missing_skills, "missing_keywords": missing_keywords[:10], "notes": ""}


def _merge_gap(seed: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
    def _union(a, b):
        out = list(a)
        for x in b:
            if x not in out:
                out.append(x)
        return out
    return {
        "missing_skills": _union(seed["missing_skills"], llm.get("missing_skills") or []),
        "missing_keywords": _union(seed["missing_keywords"], llm.get("missing_keywords") or [])[:12],
        "notes": llm.get("notes") or seed.get("notes") or "",
    }


def evaluate_gap(state: Dict[str, Any], orch) -> None:
    orch.report("evaluate_gap", 30, "Finding gaps vs the job…")
    gap = _seed_gap(state)
    client = state.get("client")
    if client:
        try:
            job = state["job"]
            resume_text = (state.get("profile") or {}).get("resume_text") or ""
            user = (f"Résumé:\n{resume_text[:4000]}\n\n"
                    f"Job description:\n{(job.get('description') or '')[:3000]}\n\n"
                    f"Already-missing skills: {', '.join(gap['missing_skills']) or 'none'}")
            llm_gap = prompts.normalize_gap(_chat_json(client, prompts.EVALUATE_GAP_PROMPT, user))
            gap = _merge_gap(gap, llm_gap)
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"evaluate_gap failed: {e}")
    state["gap"] = gap


# ==================== plan_edits ====================

def _fallback_plan(state: Dict[str, Any], gap: Dict[str, Any]) -> Dict[str, Any]:
    """A truth-preserving plan: only surface skills the candidate ALREADY has."""
    profile_skills = {s.lower() for s in (state.get("profile") or {}).get("skills") or []}
    edits = []
    for skill in gap.get("missing_skills") or []:
        if skill.lower() in profile_skills:
            edits.append({"action": "rewrite", "target": "summary + bullets",
                          "reason": f"surface {skill}, which the JD asks for and you already have"})
    return {"edits": edits, "cut_count": 0}


def plan_edits(state: Dict[str, Any], orch) -> None:
    orch.report("plan_edits", 45, "Planning the tailoring…")
    gap = state.get("gap") or {}
    plan = _fallback_plan(state, gap)
    client = state.get("client")
    if client:
        try:
            job = state["job"]
            resume_text = (state.get("profile") or {}).get("resume_text") or ""
            user = (prompts.guidance_block(state.get("instructions", "")) +
                    f"Résumé:\n{resume_text[:4000]}\n\n"
                    f"Job description:\n{(job.get('description') or '')[:2500]}\n\n"
                    f"Missing skills: {', '.join(gap.get('missing_skills') or [])}\n"
                    f"Missing keywords: {', '.join(gap.get('missing_keywords') or [])}")
            llm_plan = prompts.normalize_plan(_chat_json(client, prompts.PLAN_EDITS_PROMPT, user))
            if llm_plan["edits"]:
                plan = llm_plan
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"plan_edits failed: {e}")
    state["plan"] = plan


# ==================== rewrite ====================

def _fallback_rewrite(state: Dict[str, Any], resume_text: str) -> str:
    """Truth-preserving: append a 'Relevant skills' line drawn ONLY from the candidate's own
    skills that this JD wants. Never introduces a skill the candidate does not list."""
    profile = state.get("profile") or {}
    profile_skills = profile.get("skills") or []
    pset = {s.lower() for s in profile_skills}
    job_skills = (state.get("analysis") or {}).get("extracted_skills") or []
    desc = ((state.get("job") or {}).get("description") or "").lower()

    relevant: List[str] = [s for s in job_skills if s.lower() in pset]
    for s in profile_skills:  # also surface profile skills the JD text mentions
        if s.lower() in desc and s not in relevant:
            relevant.append(s)
    relevant = list(dict.fromkeys(relevant))
    if not relevant:
        return resume_text
    line = "Relevant skills for this role: " + ", ".join(relevant) + "."
    return (f"{resume_text.strip()}\n\n{line}").strip()


def rewrite_resume(state: Dict[str, Any], orch) -> None:
    orch.report("rewrite", 60, "Rewriting to mirror the job…")
    profile = state.get("profile") or {}
    resume_text = profile.get("resume_text") or profile_summary(profile)
    rewrite = resume_text
    client = state.get("client")
    if client and resume_text:
        try:
            job = state["job"]
            gap = state.get("gap") or {}
            plan = state.get("plan") or {}
            user = (prompts.guidance_block(state.get("instructions", ""),
                                           state.get("prior_content", "")) +
                    f"Original résumé:\n{resume_text[:5000]}\n\n"
                    f"Job description:\n{(job.get('description') or '')[:2500]}\n\n"
                    f"Tailoring plan: {json.dumps(plan, ensure_ascii=False)[:1500]}\n"
                    f"Skills to surface (only if already present): "
                    f"{', '.join(gap.get('missing_skills') or [])}")
            out = _chat_text(client, prompts.REWRITE_RESUME_PROMPT, user, max_tokens=1500)
            if out and out.strip():
                rewrite = out.strip()
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"rewrite_resume failed: {e}")
            rewrite = _fallback_rewrite(state, resume_text)
    else:
        rewrite = _fallback_rewrite(state, resume_text)
    state["rewrite"] = rewrite


# ==================== ats_format ====================

def _resume_context_slots(state: Dict[str, Any]) -> Dict[str, str]:
    cand = state.get("candidate") or {}
    return {"candidate_name": cand.get("name") or "[Your Name]", "contact_line": cand.get("contact") or ""}


def _fallback_resume_slot(slot: str, state: Dict[str, Any], rewrite: str) -> str:
    profile = state.get("profile") or {}
    paras = [p.strip() for p in (rewrite or "").split("\n\n") if p.strip()]
    mapping = {
        "summary": paras[0] if paras else "",
        "experience": rewrite,
        "skills": ", ".join(profile.get("skills") or []),
        "education": "",
    }
    return mapping.get(slot, "")


def ats_format(state: Dict[str, Any], orch) -> None:
    orch.report("ats_format", 70, "Formatting for ATS…")
    template = state.get("template") or {}
    body = template.get("body") or _DEFAULT_RESUME_BODY
    rewrite = state.get("rewrite") or ""
    slots = prompts.find_slots(body)

    values = _resume_context_slots(state)
    prose_slots = [s for s in slots if s not in values]

    filled: Dict[str, str] = {}
    client = state.get("client")
    if client and prose_slots:
        try:
            user = f"Template slots to fill: {prose_slots}\n\nTailored résumé:\n{rewrite[:5000]}"
            raw = _chat_json(client, prompts.ATS_FORMAT_PROMPT, user)
            if isinstance(raw, dict):
                filled = {k: str(v) for k, v in raw.items() if k in prose_slots and v}
            state["llm_used"] = True
        except Exception as e:
            logger.warning(f"ats_format failed: {e}")

    for slot in prose_slots:
        if not filled.get(slot):
            filled[slot] = _fallback_resume_slot(slot, state, rewrite)
    values.update(filled)

    formatted = prompts.fill_slots(body, values).strip()
    # Never let formatting drop the tailored content (which the match-lift is scored on).
    state["ats"] = formatted if formatted else rewrite
