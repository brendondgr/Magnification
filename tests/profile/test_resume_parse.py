"""
Unit tests for resume text extraction + LLM->profile normalization. No network:
the LLM path is exercised with a fake client.
"""

from utils.backend.recommend.profile_builder import (
    extract_resume_text,
    build_profile_from_text,
    normalize_profile,
    EMPTY_PROFILE,
)


def test_extract_markdown_passthrough():
    md = b"# Jane Doe\n\nML engineer interested in healthcare.\n"
    out = extract_resume_text("resume.md", md)
    assert "Jane Doe" in out and "healthcare" in out


def test_extract_latex_strips_comments():
    tex = b"% this is a comment\n\\section{Skills}\nPython, PyTorch % inline note\n"
    out = extract_resume_text("resume.tex", tex)
    assert "this is a comment" not in out
    assert "inline note" not in out
    assert "Python, PyTorch" in out
    assert "Skills" in out  # content kept, only comments removed


def test_normalize_profile_coerces_shapes():
    raw = {
        "interests_paragraph": "  Interested in ML.  ",
        "skills": "python",                       # bare string -> list
        "job_titles": ["ML Engineer", "", "  "],  # blanks dropped
        "keyword_groups": [
            {"label": "AI", "terms": ["ml", "ai"]},
            ["healthcare", "medicine"],            # bare list -> labeled group
            {"label": "Empty", "terms": []},       # dropped (no terms)
        ],
    }
    p = normalize_profile(raw)
    assert p["interests_paragraph"] == "Interested in ML."
    assert p["skills"] == ["python"]
    assert p["job_titles"] == ["ML Engineer"]
    assert [g["label"] for g in p["keyword_groups"]] == ["AI", "Group 2"]
    assert p["keyword_groups"][1]["terms"] == ["healthcare", "medicine"]


def test_normalize_profile_handles_garbage():
    assert normalize_profile("not a dict") == EMPTY_PROFILE
    assert normalize_profile(None) == EMPTY_PROFILE


def test_build_profile_from_text_with_fake_client():
    class FakeClient:
        def __init__(self):
            self.seen = None

        def chat_json(self, messages, **kw):
            self.seen = messages
            return {
                "interests_paragraph": "Wants ML in medicine.",
                "skills": ["python", "pytorch"],
                "job_titles": ["ML Engineer"],
                "keyword_groups": [{"label": "Domain", "terms": ["healthcare"]}],
            }

    fake = FakeClient()
    profile = build_profile_from_text("resume text here", fake)
    assert profile["skills"] == ["python", "pytorch"]
    assert profile["keyword_groups"][0]["label"] == "Domain"
    # The resume text is forwarded to the model.
    assert any("resume text here" in m["content"] for m in fake.seen)
