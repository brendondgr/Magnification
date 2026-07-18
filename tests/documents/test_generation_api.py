"""
Flask test-client tests for the document-generation blueprint (generation_bp).

Runs the async graphs end-to-end against an isolated in-memory SQLite engine, forcing the
offline (no-LLM) path so the deterministic fallbacks run fast and no network is touched.
Covers start→poll→completed for both kinds, the résumé match-lift in the result, edit/approve
via PATCH, and the interactive checkpoint pause→resume.
"""

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.agents import context


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)

    # Force the offline path regardless of the shared LLM config, so graphs run fast + hermetic.
    def _no_endpoint(*a, **k):
        raise RuntimeError("endpoint disabled")
    monkeypatch.setattr(context.OpenAIClient, "from_config", _no_endpoint)

    application.config.update(TESTING=True)
    yield application.test_client()
    engine.dispose()


def _seed():
    db_ops.upsert_active_profile({
        "name": "default",
        "resume_text": "Engineer. I wrote Python services.",
        "skills": ["Python", "PyTorch", "Kubernetes"],
        "job_titles": ["ML Engineer"],
    })
    job_id = db_ops.add_job({
        "title": "ML Engineer", "company": "Acme", "location": "Remote",
        "description": "We need Python, PyTorch, and Kubernetes for production ML.",
    }, create_statuses=False)
    db_ops.save_job_analysis(job_id, {
        "rag_score": 0.5,
        "skill_match": {"matched": ["Python"], "missing": ["PyTorch", "Kubernetes"]},
        "extracted_skills": ["Python", "PyTorch", "Kubernetes"],
    }, profile_id=db_ops.get_active_profile()["id"])
    return job_id


def _poll(client, task_id, until, timeout=15.0):
    deadline = time.time() + timeout
    rec = {}
    while time.time() < deadline:
        rec = client.get(f"/api/documents/status/{task_id}").get_json()
        if rec.get("status") in until:
            return rec
        time.sleep(0.02)
    raise AssertionError(f"task {task_id} stuck in {rec.get('status')}: {rec}")


def test_cover_letter_start_poll_and_fetch(client):
    job_id = _seed()
    start = client.post("/api/documents/cover-letter/start", json={"job_id": job_id}).get_json()
    assert start["success"] is True
    task_id = start["task_id"]

    rec = _poll(client, task_id, until={"completed", "failed"})
    assert rec["status"] == "completed"
    results = rec["results"]
    assert results["kind"] == "cover_letter"
    assert results["content"]
    doc_id = results["document_id"]

    # The document is fetchable and listed for the job.
    doc = client.get(f"/api/documents/{doc_id}").get_json()
    assert doc["kind"] == "cover_letter"
    assert doc["job_id"] == job_id
    listed = client.get(f"/api/documents?job_id={job_id}").get_json()["documents"]
    assert any(d["id"] == doc_id for d in listed)


def test_resume_start_has_match_lift(client):
    job_id = _seed()
    start = client.post("/api/documents/resume/start", json={"job_id": job_id}).get_json()
    rec = _poll(client, start["task_id"], until={"completed", "failed"})
    assert rec["status"] == "completed"
    results = rec["results"]
    assert results["kind"] == "resume"
    assert results["match_before"] is not None
    assert results["match_after"] is not None
    assert results["match_after"] >= results["match_before"]

    doc = client.get(f"/api/documents/{results['document_id']}").get_json()
    assert doc["match_after"] == results["match_after"]


def test_patch_approves_document(client):
    job_id = _seed()
    start = client.post("/api/documents/cover-letter/start", json={"job_id": job_id}).get_json()
    rec = _poll(client, start["task_id"], until={"completed", "failed"})
    doc_id = rec["results"]["document_id"]

    patched = client.patch(f"/api/documents/{doc_id}", json={"status": "approved"}).get_json()
    assert patched["success"] is True
    assert patched["document"]["status"] == "approved"


def test_interactive_checkpoint_pause_resume(client):
    job_id = _seed()
    start = client.post("/api/documents/cover-letter/start",
                        json={"job_id": job_id, "interactive": True}).get_json()
    task_id = start["task_id"]

    paused = _poll(client, task_id, until={"paused", "completed", "failed"})
    assert paused["status"] == "paused"
    assert paused["checkpoint"]["name"] == "angle"

    resumed = client.post(f"/api/documents/{task_id}/resume",
                          json={"decision": "approve"}).get_json()
    assert resumed["success"] is True

    done = _poll(client, task_id, until={"completed", "failed"})
    assert done["status"] == "completed"


def test_refine_updates_in_place(client):
    job_id = _seed()
    start = client.post("/api/documents/cover-letter/start", json={"job_id": job_id}).get_json()
    rec = _poll(client, start["task_id"], until={"completed", "failed"})
    doc_id = rec["results"]["document_id"]
    rev0 = client.get(f"/api/documents/{doc_id}").get_json()["revision"]

    # Refine with guidance + revise_from → same doc id, revision bumped, no new row accumulated.
    start2 = client.post("/api/documents/cover-letter/start",
                         json={"job_id": job_id, "instructions": "Warmer tone.",
                               "revise_from": doc_id}).get_json()
    rec2 = _poll(client, start2["task_id"], until={"completed", "failed"})
    assert rec2["status"] == "completed"
    assert rec2["results"]["document_id"] == doc_id
    assert client.get(f"/api/documents/{doc_id}").get_json()["revision"] == rev0 + 1

    cover_docs = [d for d in client.get(f"/api/documents?job_id={job_id}").get_json()["documents"]
                  if d["kind"] == "cover_letter"]
    assert len(cover_docs) == 1  # updated in place, not accumulated


def test_start_rejects_unknown_job_and_status_404(client):
    _seed()
    assert client.post("/api/documents/cover-letter/start", json={"job_id": 999999}).status_code == 404
    assert client.post("/api/documents/cover-letter/start", json={}).status_code == 400
    assert client.get("/api/documents/status/nope_123").status_code == 404
