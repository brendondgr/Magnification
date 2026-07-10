"""
Flask test-client tests for the documents blueprint.

Runs the routes against an isolated in-memory SQLite engine (patched SessionLocal,
like tests/database/test_clear_jobs.py) and stubs the ingestion agent at the route
boundary so no LLM/network is touched.
"""

import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    application.config.update(TESTING=True)
    yield application.test_client()
    engine.dispose()


# ---- ingest -------------------------------------------------------------------

def test_ingest_returns_draft(client, monkeypatch):
    def fake_ingest(name, data, doc_type=None):
        return {
            "doc_type": "behavioral", "target_table": "behavioral_profiles",
            "draft": {"traits": {"influence": "high"}, "strengths": ["writing"],
                      "work_style_paragraph": "ships"},
            "summary": "", "raw_text": "raw", "llm_used": True, "llm_error": None,
        }
    monkeypatch.setattr("utils.backend.routes.documents_routes.ingest_document", fake_ingest)

    resp = client.post(
        "/api/documents/ingest",
        data={"file": (io.BytesIO(b"assessment text"), "disc.txt"), "doc_type": "behavioral"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["target_table"] == "behavioral_profiles"
    assert body["draft"]["strengths"] == ["writing"]


def test_ingest_rejects_missing_and_unsupported(client):
    assert client.post("/api/documents/ingest", data={}, content_type="multipart/form-data").status_code == 400
    resp = client.post(
        "/api/documents/ingest",
        data={"file": (io.BytesIO(b"x"), "bad.exe")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


# ---- ingest/save --------------------------------------------------------------

def test_ingest_save_behavioral_persists_and_links(client):
    resp = client.post("/api/documents/ingest/save", json={
        "doc_type": "behavioral",
        "target_table": "behavioral_profiles",
        "record": {"traits": {"influence": "high"}, "strengths": ["ownership"],
                   "work_style_paragraph": "ships increments"},
        "filename": "disc.pdf",
        "raw_text": "raw disc text",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["derived_table"] == "behavioral_profiles"
    assert body["derived_id"] is not None

    got = client.get("/api/behavioral-profile").get_json()
    assert got["exists"] is True
    assert got["strengths"] == ["ownership"]
    assert got["source_filename"] == "disc.pdf"

    uploaded = client.get("/api/documents/uploaded").get_json()["documents"]
    assert len(uploaded) == 1
    assert uploaded[0]["derived_table"] == "behavioral_profiles"
    assert uploaded[0]["derived_id"] == body["derived_id"]
    assert uploaded[0]["status"] == "saved"


def test_ingest_save_reference_is_summary_only(client):
    resp = client.post("/api/documents/ingest/save", json={
        "doc_type": "reference",
        "target_table": None,
        "record": {"summary": "Strong recommendation."},
        "filename": "rec.txt",
        "raw_text": "long letter",
        "summary": "Strong recommendation.",
    })
    body = resp.get_json()
    assert body["success"] is True
    assert body["derived_table"] is None
    assert body["derived_id"] is None
    uploaded = client.get("/api/documents/uploaded").get_json()["documents"]
    assert uploaded[0]["summary"] == "Strong recommendation."


# ---- behavioral / writing CRUD ------------------------------------------------

def test_behavioral_crud(client):
    assert client.get("/api/behavioral-profile").get_json()["exists"] is False
    client.post("/api/behavioral-profile", json={"strengths": ["clarity"], "traits": {"d": "hi"}})
    got = client.get("/api/behavioral-profile").get_json()
    assert got["exists"] is True
    assert got["strengths"] == ["clarity"]


def test_writing_style_crud(client):
    assert client.get("/api/writing-style").get_json()["exists"] is False
    client.post("/api/writing-style", json={"tone": "warm", "dos": ["hook"], "donts": ["generic"]})
    got = client.get("/api/writing-style").get_json()
    assert got["exists"] is True
    assert got["tone"] == "warm"
    assert got["dos"] == ["hook"]


# ---- templates CRUD -----------------------------------------------------------

def test_templates_crud(client):
    created = client.post("/api/templates", json={
        "kind": "cover_letter", "name": "Classic", "body": "{{hook}}", "is_default": 1,
    }).get_json()
    assert created["success"] is True
    tid = created["template"]["id"]

    listing = client.get("/api/templates?kind=cover_letter").get_json()["templates"]
    assert any(t["id"] == tid for t in listing)

    patched = client.patch(f"/api/templates/{tid}", json={"name": "Classic v2"}).get_json()
    assert patched["template"]["name"] == "Classic v2"

    assert client.post("/api/templates", json={}).status_code == 400  # kind required
    assert client.delete(f"/api/templates/{tid}").get_json()["deleted"] == tid
    assert client.get(f"/api/templates/{tid}").status_code == 404


# ---- job evaluation -----------------------------------------------------------

def test_job_evaluation(client):
    # Missing job -> read is exists:False, write is 404.
    assert client.get("/api/job-evaluation/424242").get_json()["exists"] is False
    assert client.post("/api/job-evaluation/424242", json={"verdict": "x"}).status_code == 404

    job_id = db_ops.add_job({"title": "SWE", "company": "Acme", "location": "Remote"},
                            create_statuses=False)
    resp = client.post(f"/api/job-evaluation/{job_id}", json={
        "verdict": "strong fit", "fit_score": 82, "emphasize": ["python"],
    })
    assert resp.status_code == 200
    got = client.get(f"/api/job-evaluation/{job_id}").get_json()
    assert got["exists"] is True
    assert got["fit_score"] == 82
    assert got["emphasize"] == ["python"]
