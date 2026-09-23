"""
Favorite-company API tests, isolated on an in-memory SQLite engine (the routes resolve
``SessionLocal`` from ``init_db`` at call time, so patching it redirects every request).

Covers POST /api/profile/favorite-company (add, case-insensitive de-dupe, remove, toggle, 400),
that blocking a company clears its favorite, and that POST /api/profile can't write favorites.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base

URL = "/api/profile/favorite-company"


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


def test_empty_profile_exposes_favorites(client):
    assert client.get("/api/profile").get_json()["favorite_companies"] == []


def test_add_is_case_insensitive_and_keeps_first_spelling(client):
    d = client.post(URL, json={"company": " Acme Corp ", "favorite": True}).get_json()
    assert d == {"success": True, "favorite": True, "favorite_companies": ["Acme Corp"]}
    d = client.post(URL, json={"company": "acme corp", "favorite": True}).get_json()
    assert d["favorite_companies"] == ["Acme Corp"]
    assert client.get("/api/profile").get_json()["favorite_companies"] == ["Acme Corp"]


def test_explicit_remove_matches_any_casing(client):
    client.post(URL, json={"company": "Acme", "favorite": True})
    client.post(URL, json={"company": "Globex", "favorite": True})
    d = client.post(URL, json={"company": "ACME", "favorite": False}).get_json()
    assert d["favorite"] is False
    assert d["favorite_companies"] == ["Globex"]


def test_omitting_favorite_toggles(client):
    assert client.post(URL, json={"company": "Acme"}).get_json()["favorite"] is True
    d = client.post(URL, json={"company": "Acme"}).get_json()
    assert d["favorite"] is False and d["favorite_companies"] == []


def test_blank_company_is_rejected(client):
    assert client.post(URL, json={"company": "  "}).status_code == 400
    assert client.post(URL, json={}).status_code == 400


def test_favoriting_hides_nothing(client):
    jid = db_ops.add_job({"title": "Engineer", "company": "Acme", "location": "Remote"})
    client.post(URL, json={"company": "Acme"})
    assert db_ops.get_job_by_id(jid)["ignore"] == 0


def test_block_clears_the_favorite(client):
    client.post(URL, json={"company": "Acme"})
    client.post(URL, json={"company": "Globex"})
    d = client.post("/api/profile/block-company", json={"company": "acme"}).get_json()
    assert d["favorite_companies"] == ["Globex"]
    assert client.get("/api/profile").get_json()["favorite_companies"] == ["Globex"]


def test_profile_save_cannot_write_favorites(client):
    client.post(URL, json={"company": "Acme"})
    client.post("/api/profile", json={"skills": ["python"], "favorite_companies": []})
    assert client.get("/api/profile").get_json()["favorite_companies"] == ["Acme"]
