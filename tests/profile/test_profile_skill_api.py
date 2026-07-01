"""
Profile skill quick-add API tests — isolated on an in-memory SQLite engine (same pattern as
test_profile_block_api.py) so they never touch the real dev database.

Covers: POST /api/profile/add-skill adds a skill, creates a default profile if none exists,
de-dupes case-insensitively (idempotent), and rejects a blank skill.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
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


def test_add_skill_creates_profile_and_appends(client):
    resp = client.post("/api/profile/add-skill", json={"skill": "Python"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["skills"] == ["Python"]

    loaded = client.get("/api/profile").get_json()
    assert loaded["exists"] is True
    assert loaded["skills"] == ["Python"]


def test_add_skill_is_idempotent_case_insensitive(client):
    client.post("/api/profile/add-skill", json={"skill": "Python"})
    again = client.post("/api/profile/add-skill", json={"skill": "  python  "}).get_json()
    assert again["skills"] == ["Python"]


def test_add_skill_appends_to_existing_profile(client):
    client.post("/api/profile", json={"skills": ["SQL"]})
    resp = client.post("/api/profile/add-skill", json={"skill": "Docker"}).get_json()
    assert resp["skills"] == ["SQL", "Docker"]


def test_add_skill_requires_name(client):
    resp = client.post("/api/profile/add-skill", json={"skill": "   "})
    assert resp.status_code == 400
