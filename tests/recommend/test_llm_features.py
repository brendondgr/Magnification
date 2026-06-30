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

def test_llm_rerank_sets_score_on_top(monkeypatch):
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg, **kw: FakeClient(many_result=[{"score": 88, "rationale": "great fit"}])))
    jobs = [{"id": 1, "title": "ML Eng", "description": "ml"}, {"id": 2, "title": "Sales", "description": "x"}]
    analyses = [{"job_id": 1, "rag_score": 0.9}, {"job_id": 2, "rag_score": 0.2}]
    service._llm_rerank(jobs, analyses, {"interests_paragraph": "ml"}, {"top_n_llm": 1, "llm_workers": 2})
    assert analyses[0]["llm_score"] == 88.0
    assert analyses[0]["llm_rationale"] == "great fit"
    assert "llm_score" not in analyses[1]  # below top-N, untouched


def test_llm_rerank_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": False})
    analyses = [{"job_id": 1, "rag_score": 0.9}]
    service._llm_rerank([{"id": 1, "title": "x", "description": "x"}], analyses, {}, {"top_n_llm": 5})
    assert "llm_score" not in analyses[0]
