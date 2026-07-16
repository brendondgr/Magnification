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


# ---- reuse of stored extracted_skills (service._extract_skills_for_jobs) ----

def test_extract_skills_reuses_stored_and_only_fills_gaps(monkeypatch):
    """Jobs with stored skills are reused verbatim; only jobs missing them are (re)extracted."""
    from utils.backend.recommend import service

    calls = []

    def _spy_extract(desc, extra_skills=None):
        calls.append(desc)
        return ["Gazetteer"]

    monkeypatch.setattr(service.skills, "extract_skills", _spy_extract)

    jobs = [{"id": 1, "description": "job one"}, {"id": 2, "description": "job two"}]
    stored = {1: {"extracted_skills": ["Python", "AWS"]}}  # job 1 already has skills; job 2 doesn't

    out = service._extract_skills_for_jobs(jobs, {"skills": []}, {}, stored=stored)
    assert out[1] == ["Python", "AWS"]     # reused, not recomputed
    assert out[2] == ["Gazetteer"]         # the only gap was extracted
    assert calls == ["job two"]            # extractor ran exactly once (job 2 only)


def test_extract_skills_force_reextracts_all(monkeypatch):
    """force=True (reanalyze_all) re-extracts every job even when stored skills exist."""
    from utils.backend.recommend import service

    calls = []
    monkeypatch.setattr(service.skills, "extract_skills",
                        lambda desc, extra_skills=None: calls.append(desc) or ["X"])

    jobs = [{"id": 1, "description": "one"}, {"id": 2, "description": "two"}]
    stored = {1: {"extracted_skills": ["Python"]}, 2: {"extracted_skills": ["Rust"]}}
    out = service._extract_skills_for_jobs(jobs, {"skills": []}, {}, stored=stored, force=True)
    assert out == {1: ["X"], 2: ["X"]}
    assert sorted(calls) == ["one", "two"]  # both re-extracted
