"""Hybrid ranker unit tests (fake vectors — no embedding model)."""

from utils.backend.recommend import ranker


PROFILE = {
    "interests_paragraph": "Machine learning for healthcare.",
    "skills": ["python", "pytorch"],
    "job_titles": ["ML Engineer"],
    "keyword_groups": [
        {"label": "AI/ML", "terms": ["machine learning", "ai"]},
        {"label": "Domain", "terms": ["healthcare", "medicine"]},
    ],
}


def test_build_profile_query_includes_all_parts():
    q = ranker.build_profile_query(PROFILE)
    for token in ["healthcare", "python", "ML Engineer", "machine learning"]:
        assert token.lower() in q.lower()


def test_keyword_group_and_or_semantics():
    # Both groups satisfied -> 1.0
    s, hits = ranker.keyword_group_score("machine learning role in healthcare", PROFILE["keyword_groups"])
    assert s == 1.0
    assert set(hits.keys()) == {"AI/ML", "Domain"}
    # Only one group satisfied -> 0.5
    s2, hits2 = ranker.keyword_group_score("machine learning role in finance", PROFILE["keyword_groups"])
    assert s2 == 0.5
    assert list(hits2.keys()) == ["AI/ML"]
    # No groups -> neutral 1.0
    assert ranker.keyword_group_score("anything", [])[0] == 1.0


def test_rank_batch_orders_relevant_job_first():
    pvec = [1.0, 1.0, 0.0]  # aligned with the "good" job vector
    jobs = [
        {"id": 1, "description": "machine learning healthcare role using python and pytorch",
         "embedding": [1.0, 1.0, 0.0], "extracted_skills": ["python", "pytorch", "aws"]},
        {"id": 2, "description": "retail sales associate, no tech",
         "embedding": [0.0, 0.0, 1.0], "extracted_skills": ["communication"]},
    ]
    out = ranker.rank_batch(PROFILE, pvec, jobs)
    by_id = {r["job_id"]: r for r in out}
    assert by_id[1]["rag_score"] > by_id[2]["rag_score"]
    # Good job: high semantic, full keyword groups, 2/3 skills covered.
    assert by_id[1]["semantic_score"] > 0.9
    assert by_id[1]["keyword_score"] == 1.0
    assert by_id[1]["skill_score"] == round(2 / 3, 4)
    assert set(by_id[1]["skill_match"]["matched"]) == {"python", "pytorch"}
    assert by_id[1]["skill_match"]["missing"] == ["aws"]


def test_weights_shift_ranking():
    pvec = [1.0, 0.0]
    jobs = [
        {"id": 1, "description": "x", "embedding": [1.0, 0.0], "extracted_skills": []},   # semantic only
        {"id": 2, "description": "x", "embedding": [0.0, 1.0], "extracted_skills": []},   # no semantic
    ]
    semantic_heavy = ranker.rank_batch({"keyword_groups": []}, pvec, jobs,
                                       weights={"semantic": 1.0, "bm25": 0, "keyword": 0, "skill": 0})
    by_id = {r["job_id"]: r for r in semantic_heavy}
    assert by_id[1]["rag_score"] > by_id[2]["rag_score"]
