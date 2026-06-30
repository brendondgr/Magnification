"""
End-to-end recommendation test: analyze jobs against a profile and read the report +
`with_analysis` projection. The embedding model is replaced with a deterministic fake so
the test runs offline. All rows created are cleaned up afterwards.
"""

import pytest

from app import application
from utils.backend.database.init_db import init_database
from utils.backend.database import operations as db_ops
from utils.backend.recommend import embedder, service

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
