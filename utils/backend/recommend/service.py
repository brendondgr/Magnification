"""
Recommendation orchestration: embed-on-retrieve + skill extraction + hybrid scoring,
persisted to JobAnalysis. Parallelized per the runtime config.

This is the glue between the pure helpers (embedder/bm25/ranker/skills) and the database.
LLM re-ranking (verdict + rationale on the top-N) is layered on in a later phase.
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from utils.backend.database import operations as db_ops
from . import embedder, ranker, skills
from .runtime_config import get_runtime_config
from utils.backend.llm.config import load_llm_endpoint_config
from utils.backend.llm.client import OpenAIClient


def analyze_jobs(job_ids: Optional[List[int]] = None,
                 profile: Optional[Dict[str, Any]] = None,
                 runtime: Optional[Dict[str, Any]] = None,
                 progress_callback=None) -> Dict[str, Any]:
    """
    Embed + score the given jobs (or all jobs) against the active profile and persist a
    JobAnalysis per job. Returns a summary dict.
    """
    profile = profile or db_ops.get_active_profile()
    if not profile:
        return {"success": False, "message": "No active profile to analyze against."}
    runtime = runtime or get_runtime_config()

    jobs = (db_ops.get_jobs_by_ids(job_ids) if job_ids
            else db_ops.get_all_jobs(include_ignored=True))
    if not jobs:
        return {"success": True, "analyzed": 0, "profile_id": profile["id"], "top": []}

    _report(progress_callback, "embedding", 10, f"Embedding {len(jobs)} jobs…")
    job_vecs = _ensure_embeddings(jobs, runtime)

    _report(progress_callback, "skills", 45, "Extracting skills…")
    skills_map = _extract_skills_for_jobs(jobs, profile, runtime)

    _report(progress_callback, "scoring", 75, "Scoring against profile…")
    profile_query = ranker.build_profile_query(profile)
    profile_vec = embedder.embed_text(profile_query) if profile_query else []

    rjobs = [{
        "id": j["id"],
        "description": j.get("description") or "",
        "embedding": job_vecs.get(j["id"], []),
        "extracted_skills": skills_map.get(j["id"], []),
    } for j in jobs]
    analyses = ranker.rank_batch(profile, profile_vec, rjobs, weights=runtime.get("weights"))

    for j, an in zip(jobs, analyses):
        vec = job_vecs.get(j["id"], [])
        payload = {
            "semantic_score": an["semantic_score"],
            "bm25_score": an["bm25_score"],
            "keyword_score": an["keyword_score"],
            "skill_score": an["skill_score"],
            "rag_score": an["rag_score"],
            "keyword_group_hits": an["keyword_group_hits"],
            "skill_match": an["skill_match"],
            "extracted_skills": skills_map.get(j["id"], []),
            "embedding": embedder.to_bytes(vec) if vec else None,
            "embedding_dim": len(vec) or None,
        }
        db_ops.save_job_analysis(j["id"], payload, profile_id=profile["id"])

    _report(progress_callback, "completed", 100, f"Analyzed {len(analyses)} jobs.")
    ranked = sorted(analyses, key=lambda a: a.get("rag_score") or 0.0, reverse=True)
    return {
        "success": True,
        "analyzed": len(analyses),
        "profile_id": profile["id"],
        "top": ranked[:10],
    }


def build_report(limit: int = 50, include_ignored: bool = False) -> List[Dict[str, Any]]:
    """Return jobs that have an analysis, merged with it, sorted by rag_score desc."""
    jobs = db_ops.get_all_jobs(include_ignored=include_ignored)
    analyses = db_ops.get_analysis_for_jobs([j["id"] for j in jobs])
    merged = [{**j, "analysis": analyses[j["id"]]} for j in jobs if j["id"] in analyses]
    merged.sort(key=lambda x: x["analysis"].get("rag_score") or 0.0, reverse=True)
    return merged[:limit]


# ---- internals ----

def _ensure_embeddings(jobs: List[Dict[str, Any]], runtime: Dict[str, Any]) -> Dict[int, list]:
    """Reuse stored embeddings; compute (in parallel) only for jobs missing one."""
    existing = db_ops.get_analysis_for_jobs([j["id"] for j in jobs], include_embedding=True)
    vecs: Dict[int, list] = {}
    to_embed_ids: List[int] = []
    to_embed_texts: List[str] = []
    for j in jobs:
        an = existing.get(j["id"])
        stored = embedder.from_bytes(an.get("embedding")) if an else None
        if stored:
            vecs[j["id"]] = stored
        else:
            to_embed_ids.append(j["id"])
            to_embed_texts.append(j.get("description") or j.get("title") or "")
    if to_embed_texts:
        computed = embedder.embed_texts(
            to_embed_texts,
            batch_size=int(runtime.get("embed_batch_size", 32)),
            parallel=runtime.get("embed_workers"),
        )
        for jid, v in zip(to_embed_ids, computed):
            vecs[jid] = v
    return vecs


def _extract_skills_for_jobs(jobs, profile, runtime) -> Dict[int, List[str]]:
    """Extract skills per job — LLM batch when enabled+configured, else the fast gazetteer."""
    profile_skills = profile.get("skills") or []
    if runtime.get("enable_llm_skills"):
        cfg = load_llm_endpoint_config()
        if cfg.get("enabled"):
            try:
                client = OpenAIClient.from_config(cfg)
                messages = [[
                    {"role": "system", "content": skills.LLM_SKILLS_PROMPT},
                    {"role": "user", "content": (j.get("description") or "")[:6000]},
                ] for j in jobs]
                results = client.chat_many(
                    messages, max_workers=int(runtime.get("llm_workers", 4)), as_json=True
                )
                out: Dict[int, List[str]] = {}
                for j, r in zip(jobs, results):
                    if isinstance(r, dict):
                        r = r.get("skills")
                    if isinstance(r, list) and r:
                        out[j["id"]] = [str(x).strip() for x in r if str(x).strip()]
                    else:  # fall back per-job
                        out[j["id"]] = skills.extract_skills(
                            j.get("description") or "", extra_skills=profile_skills)
                return out
            except Exception as e:
                logger.warning(f"LLM skill extraction failed, using gazetteer: {e}")
    return {
        j["id"]: skills.extract_skills(j.get("description") or "", extra_skills=profile_skills)
        for j in jobs
    }


def _report(cb, stage, percent, message):
    if cb:
        try:
            cb({"stage": stage, "percent": percent, "details": {"message": message}})
        except Exception:  # pragma: no cover
            pass
