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


def test_upload_resume_llm_disabled_returns_text_and_manual_draft(client, monkeypatch):
    # Force the LLM-disabled fallback so the test is deterministic + offline.
    monkeypatch.setattr(profile_routes, "load_llm_endpoint_config", lambda: {"enabled": False})

    md = b"# Jane\nInterested in ML for healthcare.\nSkills: Python, PyTorch.\n"
    resp = client.post(
        "/api/profile/upload",
        data={"file": (io.BytesIO(md), "resume.md")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["llm_used"] is False
    assert "healthcare" in body["resume_text"]
    assert body["profile"]["skills"] == []  # manual draft (user fills in)


def test_upload_rejects_unsupported_type(client):
    resp = client.post(
        "/api/profile/upload",
        data={"file": (io.BytesIO(b"x"), "resume.docx")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
