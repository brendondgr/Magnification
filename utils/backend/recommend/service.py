"""
Recommendation orchestration: embed-on-retrieve + skill extraction + hybrid scoring,
persisted to JobAnalysis. Parallelized per the runtime config.

This is the glue between the pure helpers (embedder/bm25/ranker/skills) and the database.
LLM re-ranking (verdict + rationale on the top-N) is layered on in a later phase.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

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

    from .compensation import needs_enrichment
    comp_force = not llm_only_missing
    comp_on = bool(runtime.get("enable_llm_compensation"))
    industry_on = bool(runtime.get("enable_llm_industry"))
    n_pending = sum(1 for j in jobs
                    if needs_enrichment(j, comp_on=comp_on, industry_on=industry_on, force=comp_force))
    _report(progress_callback, "enrichment", 40,
            (f"Extracting pay + industry for {n_pending} job(s)…" if n_pending
             else "Pay + industry already checked — nothing to recover."))
    comp_recovered, industry_recovered = _recover_enrichment(jobs, runtime, force=comp_force)

    # Reuse each job's stored extracted_skills (skills come from the description alone, so they
    # don't change between runs); only extract for jobs that lack them — or, on a forced
    # reanalyze, for every job. Mirrors how embeddings are reused by _ensure_embeddings.
    n_skill_missing = sum(
        1 for j in jobs
        if (not llm_only_missing) or not ((stored.get(j["id"]) or {}).get("extracted_skills")))
    _report(progress_callback, "skills", 45,
            (f"Extracting skills for {n_skill_missing} job(s)…" if n_skill_missing
             else "Skills already extracted — reusing stored."))
    skills_map = _extract_skills_for_jobs(
        jobs, profile, runtime, stored=stored, force=not llm_only_missing)

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
        n_for_llm = len(_select_llm_indices(analyses, runtime, llm_only_missing=llm_only_missing))
        _report(progress_callback, "llm", 90,
                (f"LLM fit verdict on {n_for_llm} of {len(analyses)} job(s)…" if n_for_llm
                 else f"All {len(analyses)} covered job(s) already have an LLM fit."))
        llm_new = _llm_rerank(jobs, analyses, profile, runtime,
                              llm_only_missing=llm_only_missing)

    # Fold the LLM verdict into rag_score. Jobs with no verdict (offline, or outside the
    # llm_fraction coverage share) renormalize over the remaining signals (combined_score handles it).
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

    summary_msg = (f"Analyzed {len(analyses)} jobs · {llm_new} new LLM fit"
                   f"{'' if llm_new == 1 else 's'} · {comp_recovered} pay recovered · "
                   f"{industry_recovered} industry tagged.")
    _report(progress_callback, "completed", 100, summary_msg)
    ranked = sorted(analyses, key=lambda a: a.get("rag_score") or 0.0, reverse=True)
    return {
        "success": True,
        "analyzed": len(analyses),
        "llm_analyzed": llm_new,
        "compensation_extracted": comp_recovered,
        "industry_extracted": industry_recovered,
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


def _extract_skills_for_jobs(jobs, profile, runtime, stored=None, force=False) -> Dict[int, List[str]]:
    """
    Return an ``{id: skills}`` map for every job, reusing prior work.

    Skills are derived from the job description alone, so a job's stored ``extracted_skills``
    stay valid across runs. Jobs that already have a non-empty stored list are reused as-is;
    only the remainder is (re)extracted — LLM batch when enabled+configured, else the fast
    gazetteer. Pass ``force=True`` to re-extract every job regardless of stored skills.
    """
    profile_skills = profile.get("skills") or []
    stored = stored or {}
    reused: Dict[int, List[str]] = {}
    pending = []
    for j in jobs:
        prev = (stored.get(j["id"]) or {}).get("extracted_skills")
        if prev and not force:
            reused[j["id"]] = prev
        else:
            pending.append(j)

    extracted: Dict[int, List[str]] = {}
    if pending:
        if runtime.get("enable_llm_skills"):
            cfg = load_llm_endpoint_config()
            if cfg.get("enabled"):
                try:
                    client = OpenAIClient.from_config(cfg)
                    messages = [[
                        {"role": "system", "content": skills.LLM_SKILLS_PROMPT},
                        {"role": "user", "content": (j.get("description") or "")[:6000]},
                    ] for j in pending]
                    results = client.chat_many(
                        messages, max_workers=int(runtime.get("llm_workers", 4)), as_json=True
                    )
                    for j, r in zip(pending, results):
                        if isinstance(r, dict):
                            r = r.get("skills")
                        if isinstance(r, list) and r:
                            extracted[j["id"]] = [str(x).strip() for x in r if str(x).strip()]
                        else:  # fall back per-job
                            extracted[j["id"]] = skills.extract_skills(
                                j.get("description") or "", extra_skills=profile_skills)
                except Exception as e:
                    logger.warning(f"LLM skill extraction failed, using gazetteer: {e}")
        for j in pending:
            if j["id"] not in extracted:
                extracted[j["id"]] = skills.extract_skills(
                    j.get("description") or "", extra_skills=profile_skills)

    reused.update(extracted)
    return reused


_LLM_VERDICT_PROMPT = (
    "You are a job-fit evaluator for a specific candidate. Carefully weigh what THIS job and "
    "company are specifically looking for (required skills, seniority, domain, responsibilities) "
    "against the candidate's background, and judge whether the candidate would be interested in "
    "and qualified for the role. Return ONLY a JSON object "
    "{\"score\": <integer 0-100>, \"rationale\": \"<2-3 sentences>\"} where score is the overall "
    "fit and rationale is 2-3 sentences explaining why or why not. No prose, no code fences."
)


def _select_llm_indices(analyses: List[Dict[str, Any]], runtime: Dict[str, Any],
                        llm_only_missing: bool = True) -> List[int]:
    """
    Choose which analyzed jobs receive an LLM fit verdict this run, honoring the Options →
    Runtime **"Jobs through the LLM"** coverage slider.

    Coverage is computed over the **full** analyzed set — not just the jobs still missing a
    verdict — so the fraction means what the Options copy says: 100% covers every job, 50% the
    top half. The single knob, read from ``runtime``:

    * ``llm_fraction`` (default ``1.0``) — keep the top ``ceil(fraction × N)`` of **all**
      analyses by **semantic + bm25**. ``1.0`` covers every job (manual searches and the daily
      bot alike); ``<1.0`` keeps only that top share. Clamped to ``[0, 1]``.

    The gap-fill filter is applied **last**: when ``llm_only_missing`` is True, jobs in the
    coverage set that already carry a verdict are dropped, so repeat runs stay cheap while 100%
    coverage still guarantees every job ends up with an LLM fit.
    """
    n = len(analyses)
    if n == 0:
        return []

    def _by_relevance(idxs):
        return sorted(
            idxs,
            key=lambda i: (analyses[i].get("semantic_score") or 0.0) + (analyses[i].get("bm25_score") or 0.0),
            reverse=True,
        )

    fraction = runtime.get("llm_fraction", 1.0)
    try:
        fraction = float(fraction)
    except (TypeError, ValueError):
        fraction = 1.0
    fraction = max(0.0, min(1.0, fraction))

    all_idx = list(range(n))
    if fraction < 1.0:
        keep = math.ceil(fraction * n)
        coverage = _by_relevance(all_idx)[:keep]
    else:
        coverage = all_idx

    if llm_only_missing:
        coverage = [i for i in coverage if analyses[i].get("llm_score") is None]
    return coverage


def _llm_rerank(jobs, analyses, profile, runtime, llm_only_missing: bool = True) -> int:
    """
    Add llm_score + llm_rationale (in place) to the analyzed jobs. Returns the number of new
    verdicts issued.

    Coverage (which jobs get a verdict) is decided by ``_select_llm_indices``: the
    ``llm_fraction`` "Jobs through the LLM" slider selects the top share of the **full**
    analyzed set, and — when ``llm_only_missing`` is True — jobs that already carry a verdict
    (e.g. seeded from a prior analysis) are skipped so "Analyze Matches" only fills the gaps
    within that coverage.
    """
    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return 0
    if not analyses:
        return 0
    order = _select_llm_indices(analyses, runtime, llm_only_missing=llm_only_missing)
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
            coerced = _coerce_verdict(verdict)
            if coerced is not None:
                analyses[idx]["llm_score"], analyses[idx]["llm_rationale"] = coerced
                updated += 1
            elif isinstance(verdict, dict):
                analyses[idx]["llm_score"] = None
    except Exception as e:
        logger.warning(f"LLM re-rank failed (non-fatal): {e}")
    return updated


def _coerce_verdict(verdict: Any):
    """
    Pull ``(score, rationale)`` out of a model verdict, tolerating common shape quirks, or
    return ``None`` when no usable score is present.

    Handles: the well-formed ``{"score": <num>, "rationale": <str>}``; a numeric string
    score; and one level of accidental nesting (``{"score": {"score": <num>, ...}}``), which
    some models emit. The score is clamped to ``[0, 100]``.
    """
    if not isinstance(verdict, dict):
        return None
    obj = verdict
    score = obj.get("score")
    # Unwrap a single level of nesting: {"score": {"score": .., "rationale": ..}}.
    if isinstance(score, dict):
        obj = score
        score = obj.get("score")
    if isinstance(score, bool):  # bool is an int subclass — reject it explicitly.
        return None
    if isinstance(score, str):
        try:
            score = float(score.strip())
        except ValueError:
            return None
    if not isinstance(score, (int, float)):
        return None
    return max(0.0, min(100.0, float(score))), obj.get("rationale")


def _recover_enrichment(jobs: List[Dict[str, Any]], runtime: Dict[str, Any],
                        force: bool = False) -> Tuple[int, int]:
    """
    Fill in missing compensation **and** industry for the given (non-ignored) jobs from their
    descriptions via a single LLM pass each, persisting the recovered values. Returns
    ``(compensation_recovered, industry_recovered)``.

    Compensation is gated by ``enable_llm_compensation`` and industry by ``enable_llm_industry``
    (each independent), plus the LLM endpoint being enabled; a no-op (returns ``(0, 0)``) when
    neither field is enabled or the endpoint is off. Mirrors the scraping-pipeline enrichment so
    "Analyze Matches" also backfills pay + industry the board listing never provided.

    Only jobs that still need an enabled field **and** have not been checked for it are queried
    (see :func:`needs_enrichment`); every attempted job is flagged ``compensation_checked`` /
    ``industry_checked`` for whichever fields were requested — whether or not a value was found —
    so they are not re-queried on later runs. Pass ``force=True`` (a reanalyze) to re-attempt
    regardless.
    """
    comp_on = bool(runtime.get("enable_llm_compensation"))
    industry_on = bool(runtime.get("enable_llm_industry"))
    if not (comp_on or industry_on):
        return (0, 0)
    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return (0, 0)
    from .compensation import extract_enrichment_llm, needs_enrichment
    pending = [j for j in jobs
               if needs_enrichment(j, comp_on=comp_on, industry_on=industry_on, force=force)]
    if not pending:
        return (0, 0)
    try:
        client = OpenAIClient.from_config(cfg)
        comp_n, industry_n = extract_enrichment_llm(
            pending, client, comp=comp_on, industry=industry_on,
            max_workers=int(runtime.get("llm_workers", 4)))
        for j in pending:
            updates: Dict[str, Any] = {}
            if comp_on:
                updates["compensation_checked"] = 1
                if j.get("compensation"):
                    updates["compensation"] = j["compensation"]
            if industry_on:
                updates["industry_checked"] = 1
                if j.get("industry"):
                    updates["industry"] = j["industry"]
            db_ops.update_job(j["id"], updates)
        return (comp_n, industry_n)
    except Exception as e:
        logger.warning(f"Enrichment (pay/industry) recovery failed (non-fatal): {e}")
        return (0, 0)


def _report(cb, stage, percent, message):
    if cb:
        try:
            cb({"stage": stage, "percent": percent, "details": {"message": message}})
        except Exception:  # pragma: no cover
            pass
