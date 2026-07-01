"""
Profile API tests. Snapshots/restores the active profile so it never destroys real
data, and forces the LLM-disabled path for the upload test (no network).
"""

import io

import pytest

from app import application
from utils.backend.database import operations as db_ops
from utils.backend.routes import profile_routes


@pytest.fixture
def client():
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _restore_active_profile():
    prior = db_ops.get_active_profile()
    try:
        yield
    finally:
        current = db_ops.get_active_profile()
        if current and (not prior or current["id"] != prior["id"]):
            db_ops.delete_profile(current["id"])
        if prior:
            # Re-create the prior profile's fields as the active profile.
            db_ops.upsert_active_profile({
                k: prior[k] for k in (
                    "name", "source_filename", "resume_text", "interests_paragraph",
                    "skills", "job_titles", "keyword_groups",
                    "blocked_companies", "title_blocklist", "llm_instructions",
                )
            })


def test_get_profile_default_shape(client):
    data = client.get("/api/profile").get_json()
    assert "interests_paragraph" in data
    assert "skills" in data and "job_titles" in data and "keyword_groups" in data


def test_save_and_get_profile_roundtrip(client):
    payload = {
        "interests_paragraph": "ML for healthcare.",
        "skills": ["python", "pytorch"],
        "job_titles": ["ML Engineer", "Research Scientist"],
        "keyword_groups": [{"label": "Domain", "terms": ["healthcare", "medicine"]}],
    }
    resp = client.post("/api/profile", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True

    loaded = client.get("/api/profile").get_json()
    assert loaded["exists"] is True
    assert loaded["skills"] == ["python", "pytorch"]
    assert loaded["keyword_groups"][0]["terms"] == ["healthcare", "medicine"]


def test_upload_resume_extracts_text_without_calling_llm(client, monkeypatch):
    # Upload must be lightweight: extract text only, never invoke the LLM (which could
    # block for the full read-timeout). Prove it by booby-trapping the client builder —
    # even with an "enabled" endpoint, upload must not touch it.
    monkeypatch.setattr(
        profile_routes, "load_llm_endpoint_config",
        lambda: {"enabled": True, "base_url": "http://x/v1"},
    )

    def _boom(*a, **k):
        raise AssertionError("upload must not call the LLM")

    monkeypatch.setattr(profile_routes.OpenAIClient, "from_config", staticmethod(_boom))

    md = b"# Jane\nInterested in ML for healthcare.\nSkills: Python, PyTorch.\n"
    resp = client.post(
        "/api/profile/upload",
        data={"file": (io.BytesIO(md), "resume.md")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert "healthcare" in body["resume_text"]
    assert body["source_filename"] == "resume.md"
    # Upload no longer returns an LLM-built draft; that's the explicit /build step.
    assert "profile" not in body and "llm_used" not in body


def test_upload_rejects_unsupported_type(client):
    resp = client.post(
        "/api/profile/upload",
        data={"file": (io.BytesIO(b"x"), "resume.docx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
