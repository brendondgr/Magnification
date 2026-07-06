"""
Fast, on-page rescore (``service.rescore_jobs``): recompute sub-scores + rag_score from the
**stored** analysis artifacts against the current profile + weights, with no job re-embedding
and no LLM calls. LLM verdicts are preserved and folded back into rag_score. All db/embedder
access is monkeypatched — no real DB, no model, no network.
"""

from utils.backend.recommend import service, ranker


def _patch_db(monkeypatch, profile, jobs, stored, saves):
    monkeypatch.setattr(service.db_ops, "get_active_profile", lambda: profile)
    monkeypatch.setattr(service.db_ops, "get_all_jobs", lambda include_ignored=False: jobs)
    monkeypatch.setattr(service.db_ops, "get_analysis_for_jobs",
                        lambda ids, include_embedding=False: {k: v for k, v in stored.items() if k in ids})
    monkeypatch.setattr(service.db_ops, "save_job_analysis",
                        lambda jid, payload, profile_id=None: saves.append((jid, payload, profile_id)) or 1)
    monkeypatch.setattr(service, "get_runtime_config",
                        lambda: {"weights": {"semantic": 0.5, "bm25": 0.0, "keyword": 0.0,
                                             "skill": 0.5, "llm": 0.0}})


# ---- reweight-only path (embedder unavailable) ----

def test_reweight_only_recomputes_rag_from_stored_subscores(monkeypatch):
    """When the profile embedding is unavailable, rag_score is recomputed from the stored
    sub-scores with the current weights and ONLY rag_score is persisted."""
    profile = {"id": 7, "interests_paragraph": "python data"}
    jobs = [{"id": 1, "ignore": 0}]
    stored = {1: {"semantic_score": 0.8, "bm25_score": 0.2, "keyword_score": 0.4,
                  "skill_score": 0.6, "llm_score": None, "extracted_skills": [], "embedding": None}}
    saves = []
    _patch_db(monkeypatch, profile, jobs, stored, saves)
    # Force the reweight-only branch: embedding model unavailable.
    monkeypatch.setattr(service.embedder, "embed_text",
                        lambda t: (_ for _ in ()).throw(RuntimeError("no model")))

    res = service.rescore_jobs()
    assert res["success"] and res["rescored"] == 1
    jid, payload, pid = saves[0]
    assert jid == 1 and pid == 7
    assert set(payload.keys()) == {"rag_score"}          # only rag_score written
    # weights semantic 0.5 + skill 0.5 (others 0) → renormalized over present signals
    expected = ranker.combined_score(
        {"semantic": 0.8, "bm25": 0.2, "keyword": 0.4, "skill": 0.6},
        {"semantic": 0.5, "bm25": 0.0, "keyword": 0.0, "skill": 0.5, "llm": 0.0})
    assert payload["rag_score"] == round(expected, 4)


def test_reweight_only_preserves_and_folds_stored_llm(monkeypatch):
    """A stored LLM verdict is folded into the reweighted rag_score (llm weight applies)."""
    profile = {"id": 1, "interests_paragraph": "x"}
    jobs = [{"id": 5, "ignore": 0}]
    stored = {5: {"semantic_score": 1.0, "bm25_score": 0.0, "keyword_score": 0.0,
                  "skill_score": 0.0, "llm_score": 50.0, "llm_rationale": "ok",
                  "extracted_skills": [], "embedding": None}}
    saves = []
    _patch_db(monkeypatch, profile, jobs, stored, saves)
    monkeypatch.setattr(service, "get_runtime_config",
                        lambda: {"weights": {"semantic": 0.5, "bm25": 0.0, "keyword": 0.0,
                                             "skill": 0.0, "llm": 0.5}})
    monkeypatch.setattr(service.embedder, "embed_text", lambda t: [])   # empty → reweight-only

    res = service.rescore_jobs()
    _, payload, _ = saves[0]
    # semantic 1.0 @0.5 and llm 0.5 @0.5 → (0.5*1.0 + 0.5*0.5)/1.0 = 0.75
    assert payload["rag_score"] == 0.75
    assert res["rescored"] == 1


# ---- full rescore path (embedder available) ----

def test_full_rescore_threads_stored_artifacts_and_persists_subscores(monkeypatch):
    """With the embedder available, stored embedding + extracted_skills are threaded into
    rank_batch, the recomputed sub-scores are persisted (skill_score included), the stored LLM
    verdict is preserved + folded, and the embedding is NOT rewritten."""
    profile = {"id": 3, "interests_paragraph": "ml", "skills": ["python", "sql"]}
    jobs = [{"id": 9, "ignore": 0}]
    stored = {9: {"semantic_score": 0.1, "bm25_score": 0.1, "keyword_score": 0.1,
                  "skill_score": 0.1, "llm_score": 80.0, "llm_rationale": "great",
                  "extracted_skills": ["python", "sql", "spark"],
                  "embedding": b"vec-bytes"}}
    saves = []
    _patch_db(monkeypatch, profile, jobs, stored, saves)
    monkeypatch.setattr(service.embedder, "embed_text", lambda t: [1.0, 0.0])
    monkeypatch.setattr(service.embedder, "from_bytes", lambda b: [0.5, 0.5])

    seen = {}
    def fake_rank_batch(prof, pvec, rjobs, weights=None):
        seen["rjobs"] = rjobs
        seen["weights"] = weights
        return [{"job_id": 9, "semantic_score": 0.9, "bm25_score": 0.3,
                 "keyword_score": 0.2, "skill_score": 0.7,
                 "keyword_group_hits": {}, "skill_match": {"matched": ["python"], "missing": []}}]
    monkeypatch.setattr(service.ranker, "rank_batch", fake_rank_batch)

    res = service.rescore_jobs()
    assert res["success"] and res["rescored"] == 1
    # stored artifacts threaded through
    assert seen["rjobs"][0]["embedding"] == [0.5, 0.5]
    assert seen["rjobs"][0]["extracted_skills"] == ["python", "sql", "spark"]
    assert seen["weights"]["skill"] == 0.5
    _, payload, _ = saves[0]
    assert payload["skill_score"] == 0.7                 # recomputed sub-score persisted
    assert payload["llm_score"] == 80.0                  # stored verdict preserved
    assert payload["llm_rationale"] == "great"
    assert "embedding" not in payload                    # embedding not rewritten
    # rag folds semantic/bm25/keyword/skill/llm at the configured weights
    expected = ranker.combined_score(
        {"semantic": 0.9, "bm25": 0.3, "keyword": 0.2, "skill": 0.7, "llm": 0.8},
        seen["weights"])
    assert payload["rag_score"] == round(expected, 4)


# ---- guards ----

def test_no_active_profile_is_failure(monkeypatch):
    monkeypatch.setattr(service.db_ops, "get_active_profile", lambda: None)
    res = service.rescore_jobs()
    assert res["success"] is False


def test_no_analyzed_jobs_is_zero(monkeypatch):
    profile = {"id": 1, "interests_paragraph": "x"}
    # Two jobs exist but neither has a stored analysis → nothing to rescore.
    _patch_db(monkeypatch, profile,
              [{"id": 1, "ignore": 0}, {"id": 2, "ignore": 0}], {}, [])
    res = service.rescore_jobs()
    assert res["success"] and res["rescored"] == 0


def test_ignored_jobs_excluded(monkeypatch):
    profile = {"id": 1, "interests_paragraph": "x"}
    jobs = [{"id": 1, "ignore": 1}, {"id": 2, "ignore": 0}]
    stored = {2: {"semantic_score": 0.5, "bm25_score": 0.0, "keyword_score": 0.0,
                  "skill_score": 0.0, "llm_score": None, "extracted_skills": [], "embedding": None}}
    saves = []
    _patch_db(monkeypatch, profile, jobs, stored, saves)
    monkeypatch.setattr(service.embedder, "embed_text", lambda t: [])
    res = service.rescore_jobs()
    assert res["rescored"] == 1
    assert [s[0] for s in saves] == [2]                  # ignored job 1 never rescored
