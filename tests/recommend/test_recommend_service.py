"""
End-to-end recommendation test: analyze jobs against a profile and read the report +
`with_analysis` projection. The embedding model is replaced with a deterministic fake so
the test runs offline. All rows created are cleaned up afterwards.
"""

import pytest

from app import application
from utils.backend.database.init_db import init_database
from utils.backend.database import operations as db_ops
from utils.backend.recommend import embedder, service, ranker

# Tiny vocabulary -> count-vector "embedding" so cosine reflects keyword overlap.
_VOCAB = ["python", "ml", "healthcare", "sales", "finance", "rust"]


def _fake_vec(text):
    t = (text or "").lower()
    return [float(t.count(w)) for w in _VOCAB]


@pytest.fixture(autouse=True)
def _fake_embedder(monkeypatch):
    init_database()
    monkeypatch.setattr(embedder, "embed_texts", lambda texts, **kw: [_fake_vec(t) for t in texts])
    monkeypatch.setattr(embedder, "embed_text", lambda t: _fake_vec(t))
    # LLM rerank now defaults on; force the endpoint "disabled" so tests never hit the network
    # (individual tests re-enable it with a mocked client).
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": False})


@pytest.fixture
def client():
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


@pytest.fixture
def profile_and_jobs():
    prior = db_ops.get_active_profile()
    pid = db_ops.create_profile({
        "name": "_test_reco", "is_active": 1,
        "interests_paragraph": "machine learning for healthcare",
        "skills": ["python", "ml"],
        "job_titles": ["ML Engineer"],
        "keyword_groups": [{"label": "Domain", "terms": ["healthcare"]}],
    })
    good = db_ops.add_job({"title": "ML Engineer", "company": "HealthCo", "location": "Remote",
                           "description": "python ml healthcare role", "site": "indeed"})
    bad = db_ops.add_job({"title": "Sales Rep", "company": "SellCo", "location": "NY",
                          "description": "sales finance quota", "site": "indeed"})
    try:
        yield {"pid": pid, "good": good, "bad": bad}
    finally:
        db_ops.delete_job(good)
        db_ops.delete_job(bad)
        db_ops.delete_profile(pid)
        if prior:
            db_ops.set_active_profile(prior["id"])


def test_analyze_persists_and_ranks(profile_and_jobs):
    ids = [profile_and_jobs["good"], profile_and_jobs["bad"]]
    result = service.analyze_jobs(job_ids=ids)
    assert result["success"] is True
    assert result["analyzed"] == 2

    good_a = db_ops.get_analysis_for_job(profile_and_jobs["good"])
    bad_a = db_ops.get_analysis_for_job(profile_and_jobs["bad"])
    assert good_a["rag_score"] > bad_a["rag_score"]
    assert good_a["has_embedding"] is True
    assert "python" in [s.lower() for s in good_a["extracted_skills"]]
    assert good_a["keyword_group_hits"].get("Domain") == ["healthcare"]


def test_llm_verdict_folds_into_rag(profile_and_jobs, monkeypatch):
    # Re-enable the LLM with a mocked client (no network) and confirm the verdict is
    # persisted and folded into rag_score.
    monkeypatch.setattr(service, "load_llm_endpoint_config",
                        lambda: {"enabled": True, "base_url": "http://x/v1"})

    class FakeClient:
        def chat_many(self, message_lists, max_workers=4, as_json=False, **kw):
            return [{"score": 90, "rationale": "Strong healthcare ML fit."} for _ in message_lists]

    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, *a, **k: FakeClient()))

    ids = [profile_and_jobs["good"], profile_and_jobs["bad"]]
    runtime = {"enable_llm_rerank": True, "top_n_llm": 30, "embed_batch_size": 32,
               "embed_workers": 2, "llm_workers": 2, "weights": ranker.DEFAULT_WEIGHTS}
    service.analyze_jobs(job_ids=ids, runtime=runtime)

    good_a = db_ops.get_analysis_for_job(profile_and_jobs["good"])
    assert good_a["llm_score"] == 90
    assert good_a["llm_rationale"] == "Strong healthcare ML fit."
    # rag_score now blends the llm signal (0.9) with the rest → stays a valid 0..1 score.
    assert 0.0 < good_a["rag_score"] <= 1.0


def test_analyze_api_and_report(client, profile_and_jobs):
    ids = [profile_and_jobs["good"], profile_and_jobs["bad"]]
    resp = client.post("/api/recommend/analyze", json={"job_ids": ids})
    assert resp.status_code == 200 and resp.get_json()["success"] is True

    report = client.get("/api/recommend/report?include_ignored=1").get_json()
    assert report["success"] is True
    ranked_ids = [j["id"] for j in report["jobs"] if j["id"] in ids]
    assert ranked_ids[0] == profile_and_jobs["good"]  # best match first

    with_an = client.get("/api/jobs?with_analysis=1").get_json()
    good = next(j for j in with_an if j["id"] == profile_and_jobs["good"])
    assert good["analysis"]["rag_score"] is not None
