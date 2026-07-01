"""
Profile blocklist API tests — fully isolated on an in-memory SQLite engine so they never
touch (or hide jobs in) the real dev database. The Flask routes resolve ``SessionLocal`` from
``init_db`` at call time, so patching it redirects every request at the temp DB.

Covers: save persists the new fields (blocked_companies, title_blocklist, scoped keyword_groups)
and re-applies block rules to the current feed; POST /api/profile/block-company adds a company,
hides its jobs, and is idempotent.
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
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c
    engine.dispose()


def test_save_persists_block_fields_and_scopes(client):
    payload = {
        "blocked_companies": ["Evil Corp", "  "],   # blanks dropped by normalization
        "title_blocklist": ["Senior"],
        "keyword_groups": [
            {"label": "Role", "terms": ["intern"], "scopes": ["title"]},
            {"label": "Domain", "terms": ["ml"]},   # no scopes -> defaults to both
        ],
    }
    resp = client.post("/api/profile", json=payload)
    assert resp.status_code == 200
    loaded = client.get("/api/profile").get_json()
    assert loaded["blocked_companies"] == ["Evil Corp"]
    assert loaded["title_blocklist"] == ["Senior"]
    assert loaded["keyword_groups"][0]["scopes"] == ["title"]
    assert loaded["keyword_groups"][1]["scopes"] == ["title", "description"]


def test_save_reapplies_filters_to_feed(client):
    # Seed jobs, then save a profile that should retroactively hide one of them.
    keep = db_ops.add_job({"title": "Data Intern", "company": "Good Co", "location": "Remote"})
    drop = db_ops.add_job({"title": "Senior Engineer", "company": "Good Co", "location": "NYC"})
    resp = client.post("/api/profile", json={"title_blocklist": ["Senior"]})
    assert resp.get_json()["hidden"] == 1
    assert db_ops.get_job_by_id(keep)["ignore"] == 0
    assert db_ops.get_job_by_id(drop)["ignore"] == 1


def test_block_company_hides_and_is_idempotent(client):
    a = db_ops.add_job({"title": "Engineer", "company": "Evil Corp", "location": "NYC"})
    b = db_ops.add_job({"title": "Engineer", "company": "evil corp", "location": "LA"})
    keep = db_ops.add_job({"title": "Engineer", "company": "Good Co", "location": "SF"})

    resp = client.post("/api/profile/block-company", json={"company": "Evil Corp"})
    body = resp.get_json()
    assert body["success"] is True
    assert body["blocked_companies"] == ["Evil Corp"]
    assert body["hidden"] == 2  # both case variants
    assert db_ops.get_job_by_id(a)["ignore"] == 1
    assert db_ops.get_job_by_id(b)["ignore"] == 1
    assert db_ops.get_job_by_id(keep)["ignore"] == 0

    # Blocking the same company again is a no-op (no dupes, nothing new hidden).
    again = client.post("/api/profile/block-company", json={"company": "evil corp"}).get_json()
    assert again["blocked_companies"] == ["Evil Corp"]
    assert again["hidden"] == 0


def test_block_company_requires_name(client):
    resp = client.post("/api/profile/block-company", json={"company": "   "})
    assert resp.status_code == 400
