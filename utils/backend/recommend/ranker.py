"""
Hybrid relevance scoring (pure functions — no model or DB access).

Combines up to five signals into a single ``rag_score`` (0..1):
  * semantic — cosine(profile vector, job vector)
  * bm25     — normalized lexical overlap of the profile query vs the job corpus
  * keyword  — fraction of the profile's keyword groups the job satisfies (AND/OR)
  * skill    — fraction of the job's skills the profile covers
  * llm      — the LLM fit verdict (0..1), added by the service layer for the top candidates

The combine step **renormalizes over whichever signals are present**, so a job with no LLM
verdict (offline, or outside the top-N sent to the LLM) is scored over the remaining weights
— e.g. with ``llm`` weighted 0.40, such a job's score is computed out of the other 0.60.

The service layer (``service.py``) supplies embeddings + extracted skills + the LLM verdict;
this module is deliberately free of I/O so it can be unit-tested with fake vectors.
"""

from typing import Any, Dict, List, Optional, Sequence

from .embedder import cosine
from .bm25 import BM25Index
from .skills import match_profile_skills

# Weights sum to 1.0. The LLM verdict carries the largest share; when it is absent the
# combine step renormalizes over the remaining signals (see module docstring).
DEFAULT_WEIGHTS = {"semantic": 0.30, "bm25": 0.15, "keyword": 0.10, "skill": 0.05, "llm": 0.40}


def build_profile_query(profile: Dict[str, Any]) -> str:
    """Flatten a profile into one query string for embedding + BM25."""
    parts: List[str] = []
    if profile.get("interests_paragraph"):
        parts.append(profile["interests_paragraph"])
    parts.extend(profile.get("skills") or [])
    parts.extend(profile.get("job_titles") or [])
    for group in profile.get("keyword_groups") or []:
        parts.extend(group.get("terms") or [])
    return " ".join(p for p in parts if p)


def keyword_group_score(text: str, keyword_groups: Optional[List[Dict[str, Any]]]):
    """
    Score keyword-group preferences: AND across groups, OR within a group.

    Returns (score, hits) where score is the fraction of groups with at least one matching
    term (1.0 when there are no groups — no preference), and hits maps group label -> matched
    terms.
    """
    if not keyword_groups:
        return 1.0, {}
    t = (text or "").lower()
    hits: Dict[str, List[str]] = {}
    satisfied = 0
    for idx, group in enumerate(keyword_groups):
        label = group.get("label") or f"Group {idx + 1}"
        terms = group.get("terms") or []
        matched = [term for term in terms if term and term.lower() in t]
        if matched:
            satisfied += 1
            hits[label] = matched
    score = satisfied / len(keyword_groups)
    return score, hits


def _combine(signals: Dict[str, float], weights: Dict[str, float]) -> float:
    total = sum(weights.get(k, 0.0) for k in signals)
    if total <= 0:
        return 0.0
    return sum(signals[k] * weights.get(k, 0.0) for k in signals) / total


def combined_score(signals: Dict[str, float], weights: Optional[Dict[str, float]] = None) -> float:
    """
    Public weighted combine that renormalizes over the signals actually present.

    ``signals`` maps signal name -> value (0..1); omit a signal (e.g. ``llm``) to have its
    weight excluded and the remaining weights renormalized. Used by the service layer to fold
    the LLM verdict into ``rag_score`` after the top-N verdicts come back.
    """
    return _combine(signals, weights or DEFAULT_WEIGHTS)


def rank_batch(profile: Dict[str, Any],
               profile_vector: Sequence[float],
               jobs: List[Dict[str, Any]],
               weights: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """
    Score a batch of jobs against the profile.

    Each job dict should provide ``id``, ``description``, ``embedding`` (a float vector, may
    be empty), and ``extracted_skills`` (list). Returns a list of analysis dicts (same order)
    each containing the component scores, the combined ``rag_score``, ``keyword_group_hits``,
    and ``skill_match``.
    """
    weights = weights or DEFAULT_WEIGHTS
    profile_skills = profile.get("skills") or []
    keyword_groups = profile.get("keyword_groups") or []

    query = build_profile_query(profile)
    bm25 = BM25Index([j.get("description") or "" for j in jobs])
    bm25_norm = bm25.normalized_scores(query)

    results: List[Dict[str, Any]] = []
    for i, job in enumerate(jobs):
        job_vec = job.get("embedding") or []
        semantic = max(0.0, cosine(profile_vector, job_vec)) if (profile_vector and job_vec) else 0.0
        bm = bm25_norm[i] if i < len(bm25_norm) else 0.0
        kw_score, kw_hits = keyword_group_score(job.get("description") or "", keyword_groups)
        skill = match_profile_skills(job.get("extracted_skills") or [], profile_skills)

        signals = {
            "semantic": semantic,
            "bm25": bm,
            "keyword": kw_score,
            "skill": skill["score"],
        }
        rag = _combine(signals, weights)
        results.append({
            "job_id": job.get("id"),
            "semantic_score": round(semantic, 4),
            "bm25_score": round(bm, 4),
            "keyword_score": round(kw_score, 4),
            "skill_score": round(skill["score"], 4),
            "rag_score": round(rag, 4),
            "keyword_group_hits": kw_hits,
            "skill_match": skill,
        })
    return results
