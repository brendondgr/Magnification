"""
Tests for `get_existing_job_keys()` — the bulk Title+Company lookup used to drop
already-tracked jobs from a freshly scraped batch before spending LinkedIn/LLM
calls on them.

Runs against an isolated in-memory SQLite engine (never the real dev DB), same
pattern as `tests/database/test_clear_jobs.py`.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def test_empty_database_returns_empty_set(temp_db):
    assert db_ops.get_existing_job_keys() == set()


def test_returns_lowercased_title_company_key(temp_db):
    db_ops.add_job({"title": "Software Engineer", "company": "Acme Corp", "location": "Remote"})
    keys = db_ops.get_existing_job_keys()
    assert keys == {("software engineer", "acme corp")}


def test_case_insensitive_match_against_seeded_job(temp_db):
    db_ops.add_job({"title": "Data Analyst", "company": "Globex", "location": "New York, NY"})
    keys = db_ops.get_existing_job_keys()
    assert ("data analyst", "globex") in keys
    # A newly scraped job with different casing/whitespace should match the same key.
    incoming_key = (" Data Analyst ".strip().lower(), "GLOBEX".strip().lower())
    assert incoming_key in keys


def test_location_is_not_part_of_the_key(temp_db):
    db_ops.add_job({"title": "Product Manager", "company": "Acme", "location": "Austin, TX"})
    keys = db_ops.get_existing_job_keys()
    # A same title+company job posted in a different city is still recognized as existing.
    assert ("product manager", "acme") in keys


def test_multiple_jobs_returns_all_keys(temp_db):
    db_ops.add_job({"title": "Backend Engineer", "company": "Initech", "location": "Boston, MA"})
    db_ops.add_job({"title": "Frontend Engineer", "company": "Initech", "location": "Boston, MA"})
    keys = db_ops.get_existing_job_keys()
    assert keys == {
        ("backend engineer", "initech"),
        ("frontend engineer", "initech"),
    }
