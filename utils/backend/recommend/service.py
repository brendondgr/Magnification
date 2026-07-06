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
                 progress_callback=None,
                 llm_only_missing: bool = True) -> Dict[str, Any]:
    """
    Embed + score the given jobs (or all non-ignored jobs) against the active profile and
    persist a JobAnalysis per job. Returns a summary dict.

    When ``llm_only_missing`` is True (the default, used by the "Analyze Matches" button),
    the LLM fit verdict is issued **only for jobs that do not yet have one** — existing
    verdicts are preserved and folded back into ``rag_score`` without another LLM call. This
    makes the action a gap-filler so every non-ignored job eventually gets an LLM fit
    percentage. Pass ``llm_only_missing=False`` to force a fresh verdict on every job (e.g.
    after a profile change). Missing compensation is likewise recovered from the description.
    """
    profile = profile or db_ops.get_active_profile()
    if not profile:
        return {"success": False, "message": "No active profile to analyze against."}
    runtime = runtime or get_runtime_config()

    jobs = (db_ops.get_jobs_by_ids(job_ids) if job_ids
            else db_ops.get_all_jobs(include_ignored=False))
    # Only the keyword-filtered remainder is analyzed: ignored jobs (dropped by the
    # Title/Description keyword filter) are skipped, so we never embed or score them.
    jobs = [j for j in jobs if not j.get("ignore")]
    if not jobs:
        return {"success": True, "analyzed": 0, "profile_id": profile["id"], "top": []}

    weights = runtime.get("weights") or ranker.DEFAULT_WEIGHTS

    # Stored verdicts for these jobs: used to preserve existing LLM fit scores and to spend
    # LLM calls only on jobs that still lack one when ``llm_only_missing`` is set.
    stored = db_ops.get_analysis_for_jobs([j["id"] for j in jobs])

    _report(progress_callback, "embedding", 10, f"Embedding {len(jobs)} jobs…")
    job_vecs = _ensure_embeddings(jobs, runtime)

    _report(progress_callback, "compensation", 40, "Recovering missing compensation…")
    comp_recovered = _recover_compensation(jobs, runtime)

    _report(progress_callback, "skills", 45, "Extracting skills…")
    skills_map = _extract_skills_for_jobs(jobs, profile, runtime)

    _report(progress_callback, "scoring", 75, "Scoring against profile…")
    profile_query = ranker.build_profile_query(profile)
    profile_vec = embedder.embed_text(profile_query) if profile_query else []

    rjobs = [{
        "id": j["id"],
        "title": j.get("title") or "",
        "description": j.get("description") or "",
        "embedding": job_vecs.get(j["id"], []),
        "extracted_skills": skills_map.get(j["id"], []),
    } for j in jobs]
    # Preliminary scores from semantic/bm25/keyword/skill (llm folded in below).
    analyses = ranker.rank_batch(profile, profile_vec, rjobs, weights=weights)

    # Carry forward any existing LLM verdict so it survives re-scoring and folds into
    # rag_score even when we don't re-query the LLM for it.
    for j, an in zip(jobs, analyses):
        prev = stored.get(j["id"])
        if prev and prev.get("llm_score") is not None:
            an["llm_score"] = prev.get("llm_score")
            an["llm_rationale"] = prev.get("llm_rationale")

    llm_new = 0
    if runtime.get("enable_llm_rerank"):
        _report(progress_callback, "llm", 90, "LLM fit verdict on matches missing one…")
        llm_new = _llm_rerank(jobs, analyses, profile, runtime,
                              llm_only_missing=llm_only_missing)

    # Fold the LLM verdict into rag_score. Jobs with no verdict (offline, or excluded by an
    # optional top_n_llm cap) renormalize over the remaining signals (combined_score handles it).
    for an in analyses:
        signals = {
            "semantic": an["semantic_score"], "bm25": an["bm25_score"],
            "keyword": an["keyword_score"], "skill": an["skill_score"],
        }
        if an.get("llm_score") is not None:
            signals["llm"] = max(0.0, min(1.0, an["llm_score"] / 100.0))
        an["rag_score"] = round(ranker.combined_score(signals, weights), 4)

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
            "llm_score": an.get("llm_score"),
            "llm_rationale": an.get("llm_rationale"),
        }
        db_ops.save_job_analysis(j["id"], payload, profile_id=profile["id"])

    _report(progress_callback, "completed", 100, f"Analyzed {len(analyses)} jobs.")
    ranked = sorted(analyses, key=lambda a: a.get("rag_score") or 0.0, reverse=True)
    return {
        "success": True,
        "analyzed": len(analyses),
        "llm_analyzed": llm_new,
        "compensation_extracted": comp_recovered,
        "profile_id": profile["id"],
        "top": ranked[:30],
    }


def rescore_jobs(profile: Optional[Dict[str, Any]] = None,
                 runtime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Cheaply recompute sub-scores + ``rag_score`` for already-analyzed jobs from their
    **stored** artifacts, against the current profile and score weights. No job re-embedding,
    no LLM calls, and no compensation recovery — this is the fast refresh used when only the
    score weights or the profile's skills/keywords changed.

    Reuses each job's stored embedding and ``extracted_skills``, and **preserves** the stored
    LLM verdict (``llm_score``/``llm_rationale``) — folding it back into ``rag_score`` — so the
    LLM-fit share survives a rescore without another call. Only jobs that already have an
    analysis are touched (unanalyzed jobs have no sub-scores to reweight).

    When the profile embedding is unavailable (e.g. the embedding model isn't cached and there
    is no network), it falls back to a **reweight-only** pass: ``rag_score`` is recomputed from
    the stored sub-scores so score-weight changes still take effect offline.
    """
    profile = profile or db_ops.get_active_profile()
    if not profile:
        return {"success": False, "message": "No active profile to rescore against."}
    runtime = runtime or get_runtime_config()
    weights = runtime.get("weights") or ranker.DEFAULT_WEIGHTS

    jobs = [j for j in db_ops.get_all_jobs(include_ignored=False) if not j.get("ignore")]
    stored = db_ops.get_analysis_for_jobs([j["id"] for j in jobs], include_embedding=True)
    jobs = [j for j in jobs if j["id"] in stored]
    if not jobs:
        return {"success": True, "rescored": 0, "profile_id": profile["id"], "top": []}

    def _fold_llm(an: Dict[str, Any], prev: Dict[str, Any]) -> None:
        """Carry the stored LLM verdict onto ``an`` and (re)compute ``rag_score``."""
        if prev and prev.get("llm_score") is not None:
            an["llm_score"] = prev.get("llm_score")
            an["llm_rationale"] = prev.get("llm_rationale")
        signals = {
            "semantic": an["semantic_score"], "bm25": an["bm25_score"],
            "keyword": an["keyword_score"], "skill": an["skill_score"],
        }
        if an.get("llm_score") is not None:
            signals["llm"] = max(0.0, min(1.0, an["llm_score"] / 100.0))
        an["rag_score"] = round(ranker.combined_score(signals, weights), 4)

    # Try a full rescore (needs the profile embedding for the semantic signal); fall back to a
    # reweight-only pass from the stored sub-scores when the embedder is unavailable.
    profile_query = ranker.build_profile_query(profile)
    profile_vec: list = []
    if profile_query:
        try:
            profile_vec = embedder.embed_text(profile_query)
        except Exception as e:  # pragma: no cover - depends on model/network availability
            logger.warning(f"rescore: profile embed unavailable, reweighting from stored sub-scores: {e}")

    if profile_vec:
        rjobs = [{
            "id": j["id"],
            "title": j.get("title") or "",
            "description": j.get("description") or "",
            "embedding": embedder.from_bytes(stored[j["id"]].get("embedding")) or [],
            "extracted_skills": stored[j["id"]].get("extracted_skills") or [],
        } for j in jobs]
        analyses = ranker.rank_batch(profile, profile_vec, rjobs, weights=weights)
        for j, an in zip(jobs, analyses):
            _fold_llm(an, stored.get(j["id"]) or {})
            db_ops.save_job_analysis(j["id"], {
                "semantic_score": an["semantic_score"],
                "bm25_score": an["bm25_score"],
                "keyword_score": an["keyword_score"],
                "skill_score": an["skill_score"],
                "rag_score": an["rag_score"],
                "keyword_group_hits": an["keyword_group_hits"],
                "skill_match": an["skill_match"],
                "llm_score": an.get("llm_score"),
                "llm_rationale": an.get("llm_rationale"),
            }, profile_id=profile["id"])
    else:
        # Reweight only: recompute rag_score from the stored sub-scores.
        analyses = []
        for j in jobs:
            prev = stored[j["id"]]
            an = {
                "semantic_score": prev.get("semantic_score") or 0.0,
                "bm25_score": prev.get("bm25_score") or 0.0,
                "keyword_score": prev.get("keyword_score") or 0.0,
                "skill_score": prev.get("skill_score") or 0.0,
            }
            _fold_llm(an, prev)
            analyses.append(an)
            db_ops.save_job_analysis(j["id"], {"rag_score": an["rag_score"]},
                                     profile_id=profile["id"])

    ranked = sorted(analyses, key=lambda a: a.get("rag_score") or 0.0, reverse=True)
    return {
        "success": True,
        "rescored": len(analyses),
        "profile_id": profile["id"],
        "top": ranked[:30],
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


_LLM_VERDICT_PROMPT = (
    "You are a job-fit evaluator for a specific candidate. Carefully weigh what THIS job and "
    "company are specifically looking for (required skills, seniority, domain, responsibilities) "
    "against the candidate's background, and judge whether the candidate would be interested in "
    "and qualified for the role. Return ONLY a JSON object "
    "{\"score\": <integer 0-100>, \"rationale\": \"<2-3 sentences>\"} where score is the overall "
    "fit and rationale is 2-3 sentences explaining why or why not. No prose, no code fences."
)


def _llm_rerank(jobs, analyses, profile, runtime, llm_only_missing: bool = True) -> int:
    """
    Add llm_score + llm_rationale (in place) to the analyzed jobs. Returns the number of new
    verdicts issued.

    When ``llm_only_missing`` is True, jobs that already carry a verdict (``llm_score`` set,
    e.g. seeded from a prior analysis) are skipped so "Analyze Matches" only fills the gaps.
    ``top_n_llm`` is an optional cost cap on the remaining candidates: ``0`` (or
    missing/negative) means no cap → all of them; a positive value limits the verdict to that
    many top candidates by **semantic + bm25** (the lexical/vector relevance).
    """
    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return 0
    if not analyses:
        return 0
    candidates = [
        i for i in range(len(analyses))
        if not (llm_only_missing and analyses[i].get("llm_score") is not None)
    ]
    top_n = int(runtime.get("top_n_llm", 0) or 0)
    if top_n > 0:
        order = sorted(
            candidates,
            key=lambda i: (analyses[i].get("semantic_score") or 0.0) + (analyses[i].get("bm25_score") or 0.0),
            reverse=True,
        )[:top_n]
    else:
        order = candidates
    if not order:
        return 0
    profile_summary = ranker.build_profile_query(profile)[:2000]
    updated = 0
    try:
        client = OpenAIClient.from_config(cfg)
        messages = [[
            {"role": "system", "content": _LLM_VERDICT_PROMPT},
            {"role": "user", "content": f"Candidate profile:\n{profile_summary}\n\n"
                                        f"Job: {jobs[i].get('title', '')}\n"
                                        f"{(jobs[i].get('description') or '')[:4000]}"},
        ] for i in order]
        results = client.chat_many(messages, max_workers=int(runtime.get("llm_workers", 4)),
                                   as_json=True)
        for idx, verdict in zip(order, results):
            if isinstance(verdict, dict):
                score = verdict.get("score")
                if isinstance(score, (int, float)):
                    analyses[idx]["llm_score"] = float(score)
                    analyses[idx]["llm_rationale"] = verdict.get("rationale")
                    updated += 1
                else:
                    analyses[idx]["llm_score"] = None
    except Exception as e:
        logger.warning(f"LLM re-rank failed (non-fatal): {e}")
    return updated


def _recover_compensation(jobs: List[Dict[str, Any]], runtime: Dict[str, Any]) -> int:
    """
    Fill in missing compensation for the given (non-ignored) jobs by extracting it from the
    description via the LLM, persisting each recovered value. Returns the number recovered.

    Gated by the ``enable_llm_compensation`` runtime toggle and the LLM endpoint being
    enabled; a no-op (returns 0) otherwise. Mirrors the scraping-pipeline recovery so the
    "Analyze Matches" action also backfills pay the board listing never provided.
    """
    if not runtime.get("enable_llm_compensation"):
        return 0
    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return 0
    from .compensation import extract_compensation_llm, needs_compensation
    pending = [j for j in jobs if needs_compensation(j)]
    if not pending:
        return 0
    try:
        client = OpenAIClient.from_config(cfg)
        extracted = extract_compensation_llm(
            jobs, client, max_workers=int(runtime.get("llm_workers", 4)))
        for j in pending:
            if j.get("compensation"):
                db_ops.update_job(j["id"], {"compensation": j["compensation"]})
        return extracted
    except Exception as e:
        logger.warning(f"Compensation recovery failed (non-fatal): {e}")
        return 0


def _report(cb, stage, percent, message):
    if cb:
        try:
            cb({"stage": stage, "percent": percent, "details": {"message": message}})
        except Exception:  # pragma: no cover
            pass
