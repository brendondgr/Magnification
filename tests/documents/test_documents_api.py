"""
Flask test-client tests for the documents blueprint.

Runs the routes against an isolated in-memory SQLite engine (patched SessionLocal,
like tests/database/test_clear_jobs.py). Only the per-job job-evaluation and the
read-only generated-documents routes remain after the Behavioral / Writing / Templates /
ingestion subsystems were retired in favor of the editable Document Guidance.
"""

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


# ---- generated documents (read-only list) -------------------------------------

def test_list_generated_documents(client):
    assert client.get("/api/documents").status_code == 400  # job_id required

    job_id = db_ops.add_job({"title": "SWE", "company": "Acme", "location": "Remote"},
                            create_statuses=False)
    empty = client.get(f"/api/documents?job_id={job_id}").get_json()
    assert empty["documents"] == []
