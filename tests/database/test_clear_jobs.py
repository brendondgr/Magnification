"""
Scoped-clear test for `clear_jobs_database()`.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by
patching the module-level ``SessionLocal`` that ``get_db_context`` resolves at
call time. Seeds a profile + job + application statuses + analysis, clears the
jobs scope, and asserts every job-scoped row is gone while the profile survives.
"""

import struct

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base, Job, ApplicationStatus, JobAnalysis, Profile


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # get_db_context() reads the module global SessionLocal at call time.
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def test_clear_jobs_keeps_profile(temp_db):
    # Seed a profile (should survive) and a fully-populated job graph.
    profile_id = db_ops.create_profile({"name": "default", "is_active": 1, "skills": ["python"]})
    job_id = db_ops.add_job(
        {"title": "SWE", "company": "Acme", "location": "Remote"},
        create_statuses=True,
    )
    db_ops.save_job_analysis(
        job_id,
        {"rag_score": 0.9, "embedding": struct.pack("<2f", 0.1, 0.2), "embedding_dim": 2},
        profile_id=profile_id,
    )

    with init_db.SessionLocal() as db:
        assert db.query(Job).count() == 1
        assert db.query(ApplicationStatus).count() > 0
        assert db.query(JobAnalysis).count() == 1
        assert db.query(Profile).count() == 1

    deleted = db_ops.clear_jobs_database()
    assert deleted == 1

    with init_db.SessionLocal() as db:
        assert db.query(Job).count() == 0
        assert db.query(ApplicationStatus).count() == 0
        assert db.query(JobAnalysis).count() == 0
        # Profile is preserved.
        assert db.query(Profile).count() == 1
        assert db.query(Profile).first().name == "default"
