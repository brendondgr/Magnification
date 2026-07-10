"""
Tests for the résumé match-lift scoring (utils/backend/agents/scoring.py).

Pure functions over plain dicts — no DB, no model. Exercises the offline path (no stored
embedding → lexical + skill signals only) and asserts the lift is monotone when the tailored
text mirrors more of the JD's skills.
"""

from utils.backend.agents import scoring


_JOB = {
    "id": 1,
    "title": "Machine Learning Engineer",
    "description": "We need Python, PyTorch, and Kubernetes for production ML systems.",
}
# Recommendation artifacts as the analyze pipeline would have stored them (no embedding here,
# so scoring stays purely lexical + skill-coverage — the offline path).
_ANALYSIS = {"extracted_skills": ["Python", "PyTorch", "Kubernetes"], "embedding": None}
_PROFILE = {"skills": ["Python", "PyTorch", "Kubernetes"], "job_titles": [], "keyword_groups": []}


def test_score_is_a_fraction():
    s = scoring.score_text_against_job(_JOB, _ANALYSIS, _PROFILE, "I write Python for ML.")
    assert isinstance(s, float)
    assert 0.0 <= s <= 1.0


def test_lift_is_monotone_when_jd_skills_added():
    before = "I have written some Python scripts."
    after = "I build production ML systems with Python, PyTorch, and Kubernetes."
    result = scoring.match_lift(_JOB, _ANALYSIS, _PROFILE, before, after)
    assert 0.0 <= result["match_before"] <= 1.0
    assert 0.0 <= result["match_after"] <= 1.0
    # Mirroring more of the JD's skills must not lower the objective match.
    assert result["match_after"] >= result["match_before"]
    assert result["lift"] == round(result["match_after"] - result["match_before"], 4)
    # This fixture genuinely improves coverage (1/3 → 3/3 skills), so the lift is positive.
    assert result["lift"] > 0.0


def test_handles_empty_analysis_and_text():
    s = scoring.score_text_against_job(_JOB, {}, {}, "")
    assert isinstance(s, float)
    assert 0.0 <= s <= 1.0
