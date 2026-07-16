"""LLM-assisted keyword generation + LLM re-rank (fake clients, no network)."""

from utils.backend.recommend import keywords, service


class FakeClient:
    def __init__(self, json_result=None, many_result=None):
        self._json = json_result
        self._many = many_result

    def chat_json(self, messages, **kw):
        return self._json

    def chat_many(self, message_lists, **kw):
        return self._many


# ---- keyword generation ----

def test_normalize_keywords_coerces():
    raw = {
        "search_terms": ["ML Engineer", "", "Research Scientist"],
        "keyword_groups": [{"label": "AI", "terms": ["ml", "ai"]}, ["healthcare"]],
        "job_type": "Full-Time",
    }
    out = keywords.normalize_keywords(raw)
    assert out["search_terms"] == ["ML Engineer", "Research Scientist"]
    assert out["job_type"] == "fulltime"
    assert [g["label"] for g in out["keyword_groups"]] == ["AI", "Group 2"]


def test_normalize_keywords_invalid_job_type_is_none():
    assert keywords.normalize_keywords({"job_type": "wizard"})["job_type"] is None
    assert keywords.normalize_keywords("garbage") == {"search_terms": [], "keyword_groups": [], "job_type": None}


def test_generate_keywords_with_fake_client():
    fake = FakeClient(json_result={
        "search_terms": ["ML Engineer"],
        "keyword_groups": [{"label": "Domain", "terms": ["healthcare"]}],
        "job_type": "internship",
    })
    out = keywords.generate_keywords("ML for hospitals", fake)
    assert out["search_terms"] == ["ML Engineer"]
    assert out["job_type"] == "internship"


def test_seed_from_profile():
    seed = keywords.seed_from_profile({
        "interests_paragraph": "ML for healthcare.",
        "job_titles": ["ML Engineer"], "skills": ["python"],
    })
    assert "ML for healthcare." in seed and "ML Engineer" in seed and "python" in seed


# ---- LLM re-rank ----

def test_llm_rerank_sets_score_on_top_share(monkeypatch):
    """A <1.0 llm_fraction covers only the top share by semantic+bm25."""
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg, **kw: FakeClient(many_result=[{"score": 88, "rationale": "great fit"}])))
    jobs = [{"id": 1, "title": "ML Eng", "description": "ml"}, {"id": 2, "title": "Sales", "description": "x"}]
    # Job 1 is the top by semantic+bm25, so a 0.5 fraction covers only it.
    analyses = [{"job_id": 1, "rag_score": 0.9, "semantic_score": 0.9, "bm25_score": 0.9},
                {"job_id": 2, "rag_score": 0.2, "semantic_score": 0.1, "bm25_score": 0.1}]
    service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"}, {"llm_fraction": 0.5, "llm_workers": 2})
    assert analyses[0]["llm_score"] == 88.0
    assert analyses[0]["llm_rationale"] == "great fit"
    assert "llm_score" not in analyses[1]  # outside the top-share coverage, untouched


def test_llm_rerank_covers_all_jobs_by_default(monkeypatch):
    """With the default full coverage (llm_fraction 1.0/absent), EVERY analyzed job gets a verdict."""
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg, **kw: FakeClient(
                            many_result=[{"score": 70, "rationale": "a"}, {"score": 40, "rationale": "b"}])))
    jobs = [{"id": 1, "title": "ML Eng", "description": "ml"}, {"id": 2, "title": "Sales", "description": "x"}]
    analyses = [{"job_id": 1, "rag_score": 0.9, "semantic_score": 0.1, "bm25_score": 0.1},
                {"job_id": 2, "rag_score": 0.2, "semantic_score": 0.9, "bm25_score": 0.9}]
    # No llm_fraction key → full coverage → all jobs scored.
    service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"}, {"llm_workers": 2})
    assert analyses[0]["llm_score"] == 70.0
    assert analyses[1]["llm_score"] == 40.0
    # Explicit llm_fraction 1.0 is equivalent to absent.
    analyses2 = [{"job_id": 1, "rag_score": 0.9}, {"job_id": 2, "rag_score": 0.2}]
    service._llm_rerank(jobs, analyses2, {"interests_paragraph": "ml"}, {"llm_fraction": 1.0})
    assert "llm_score" in analyses2[0] and "llm_score" in analyses2[1]


def test_llm_rerank_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": False})
    analyses = [{"job_id": 1, "rag_score": 0.9}]
    service._llm_rerank([{"id": 1, "title": "x", "description": "x"}], analyses, {}, {"llm_workers": 2})
    assert "llm_score" not in analyses[0]


# ---- LLM coverage fraction (llm_fraction, default 1.0 = every final job) ----

def _enable_fake(monkeypatch, many_result):
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg, **kw: FakeClient(many_result=many_result)))


def _four_jobs_analyses():
    jobs = [{"id": i, "title": f"J{i}", "description": "d"} for i in range(1, 5)]
    # Distinct semantic+bm25 so the top share is deterministic: job 4 > 3 > 2 > 1.
    analyses = [
        {"job_id": 1, "rag_score": 0.1, "semantic_score": 0.1, "bm25_score": 0.1},
        {"job_id": 2, "rag_score": 0.2, "semantic_score": 0.3, "bm25_score": 0.3},
        {"job_id": 3, "rag_score": 0.3, "semantic_score": 0.6, "bm25_score": 0.6},
        {"job_id": 4, "rag_score": 0.4, "semantic_score": 0.9, "bm25_score": 0.9},
    ]
    return jobs, analyses


def test_llm_fraction_default_covers_all(monkeypatch):
    """llm_fraction absent / 1.0 → every candidate gets an LLM verdict (the default)."""
    _enable_fake(monkeypatch, [{"score": 50, "rationale": "r"}] * 4)
    jobs, analyses = _four_jobs_analyses()
    n = service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"}, {"llm_workers": 2})
    assert n == 4
    assert all("llm_score" in a for a in analyses)

    jobs2, analyses2 = _four_jobs_analyses()
    n2 = service._llm_rerank(jobs2, analyses2, {"interests_paragraph": "ml"},
                             {"llm_fraction": 1.0, "llm_workers": 2})
    assert n2 == 4 and all("llm_score" in a for a in analyses2)


def test_llm_fraction_half_keeps_top_share(monkeypatch):
    """llm_fraction 0.5 of 4 candidates → the top 2 by semantic+bm25 (jobs 3 & 4)."""
    _enable_fake(monkeypatch, [{"score": 77, "rationale": "r"}] * 2)
    jobs, analyses = _four_jobs_analyses()
    n = service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"},
                            {"llm_fraction": 0.5, "llm_workers": 2})
    assert n == 2
    scored = {a["job_id"] for a in analyses if a.get("llm_score") is not None}
    assert scored == {3, 4}  # highest semantic+bm25


def test_llm_fraction_ceil_covers_at_least_one(monkeypatch):
    """A tiny non-zero fraction still covers at least one job (ceil), the top candidate."""
    _enable_fake(monkeypatch, [{"score": 60, "rationale": "r"}])
    jobs, analyses = _four_jobs_analyses()
    n = service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"},
                            {"llm_fraction": 0.01, "llm_workers": 2})
    assert n == 1
    assert analyses[3].get("llm_score") == 60.0  # job 4, the top by semantic+bm25


def test_llm_fraction_is_the_only_coverage_knob(monkeypatch):
    """A stale top_n_llm key is ignored: the coverage share is decided solely by llm_fraction."""
    _enable_fake(monkeypatch, [{"score": 88, "rationale": "r"}] * 3)
    jobs, analyses = _four_jobs_analyses()
    # fraction 0.75 → top 3 (jobs 2,3,4); a leftover top_n_llm no longer caps it.
    n = service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"},
                            {"llm_fraction": 0.75, "top_n_llm": 1, "llm_workers": 2})
    assert n == 3
    scored = {a["job_id"] for a in analyses if a.get("llm_score") is not None}
    assert scored == {2, 3, 4}
    assert analyses[0].get("llm_score") is None  # job 1, outside the top-75% share
