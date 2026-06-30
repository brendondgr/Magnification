"""Tests for the gazetteer skill extractor and profile skill matching."""

from utils.backend.recommend.skills import (
    extract_skills,
    match_profile_skills,
    extract_skills_llm,
)

SAMPLE = """
We are hiring a Machine Learning engineer. You will build models in Python using
PyTorch and deploy on AWS with Docker. Experience with healthcare data is a plus.
JavaScript is not required.
"""


def test_extract_skills_finds_known_terms():
    found = extract_skills(SAMPLE)
    assert "Python" in found
    assert "PyTorch" in found
    assert "AWS" in found
    assert "Machine Learning" in found
    assert "Healthcare" in found


def test_extract_skills_boundary_aware():
    # "Java" must not match inside "JavaScript".
    found = extract_skills("We use JavaScript and TypeScript.")
    assert "JavaScript" in found
    assert "TypeScript" in found
    assert "Java" not in found


def test_extract_skills_merges_profile_terms():
    found = extract_skills("Strong background in clinical informatics.",
                           extra_skills=["clinical informatics"])
    assert "clinical informatics" in found


def test_match_profile_skills():
    job_skills = ["Python", "PyTorch", "AWS", "Kubernetes"]
    profile_skills = ["python", "pytorch", "docker"]
    result = match_profile_skills(job_skills, profile_skills)
    assert set(result["matched"]) == {"Python", "PyTorch"}
    assert set(result["missing"]) == {"AWS", "Kubernetes"}
    assert result["score"] == 0.5  # 2 of the job's 4 skills covered


def test_match_profile_skills_empty_job():
    assert match_profile_skills([], ["python"]) == {"matched": [], "missing": [], "score": 0.0}


def test_extract_skills_llm_with_fake_client():
    class FakeClient:
        def chat_json(self, messages, **kw):
            return ["Python", "RAG", "python"]  # dupes/casing handled

    out = extract_skills_llm("…", FakeClient())
    assert out == ["Python", "RAG"]
