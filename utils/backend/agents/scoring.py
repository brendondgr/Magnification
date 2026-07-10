"""
The résumé Critic's objective yardstick — the differentiated feature (design §3.2).

Instead of asking an LLM "is this résumé better?", we build a **throwaway profile** from the
tailored résumé text and reuse Magnification's own recommender (``recommend/ranker.py``) against
the single target job, producing a real **match-lift** (before → after) that is both the loop's
stop criterion and the headline UI metric.

Offline-safe by construction: ``bm25 + keyword + skill`` are pure-Python and need no model, and
``ranker`` renormalizes over whichever signals are present, so a genuine (lexical + skill-coverage)
lift is measurable even when the embedding model is uncached; when embeddings are available the
semantic signal folds in too. Both *before* and *after* are scored through the identical path with
the same available signals, so the comparison is apples-to-apples.

The LLM fit *verdict* is intentionally excluded from this score: it is expensive and noisy to
re-issue per revision, and the point here is to measure how well the résumé text mirrors THIS JD.
"""

from typing import Any, Dict, Optional

from ..recommend import ranker, embedder, skills


def _throwaway_profile(text: str, base_profile: Dict[str, Any]) -> Dict[str, Any]:
    """A profile whose signal-bearing fields come from ``text`` (skills re-extracted from it),
    but which keeps the candidate's job titles + keyword groups so the keyword signal is stable."""
    found = skills.extract_skills(text or "", extra_skills=base_profile.get("skills"))
    return {
        "interests_paragraph": text or "",
        "skills": found,
        "job_titles": base_profile.get("job_titles") or [],
        "keyword_groups": base_profile.get("keyword_groups") or [],
    }


def score_text_against_job(job: Dict[str, Any], analysis: Optional[Dict[str, Any]],
                           base_profile: Dict[str, Any], text: str,
                           weights: Optional[Dict[str, float]] = None) -> float:
    """
    Score a résumé ``text`` (treated as a transient profile) against one job → ``rag_score`` (0..1).

    Reuses the job's stored embedding for the semantic signal when present; embeds the throwaway
    profile only if there is a job vector to compare against, and silently drops semantic when the
    embedder is unavailable.
    """
    prof = _throwaway_profile(text, base_profile or {})
    job_vec = embedder.from_bytes((analysis or {}).get("embedding")) or []

    profile_vec: list = []
    if job_vec:
        query = ranker.build_profile_query(prof)
        if query:
            try:
                profile_vec = embedder.embed_text(query)
            except Exception:  # pragma: no cover - model/network unavailable → lexical-only
                profile_vec = []

    job_dict = {
        "id": job.get("id"),
        "title": job.get("title") or "",
        "description": job.get("description") or "",
        "embedding": job_vec,
        "extracted_skills": ((analysis or {}).get("extracted_skills")
                             or skills.extract_skills(job.get("description") or "")),
    }
    results = ranker.rank_batch(prof, profile_vec, [job_dict], weights=weights)
    return float(results[0]["rag_score"]) if results else 0.0


def match_lift(job: Dict[str, Any], analysis: Optional[Dict[str, Any]],
               base_profile: Dict[str, Any], before_text: str, after_text: str,
               weights: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    """Score ``before_text`` and ``after_text`` through the identical path and return the lift."""
    before = score_text_against_job(job, analysis, base_profile, before_text, weights)
    after = score_text_against_job(job, analysis, base_profile, after_text, weights)
    return {
        "match_before": round(before, 4),
        "match_after": round(after, 4),
        "lift": round(after - before, 4),
    }
