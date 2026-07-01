"""
Round-trip tests for the profile blocklist fields and scoped keyword groups.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time. Also exercises the
additive migration (idempotent, no-op when columns already exist) and the profile normalizer.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.recommend.profile_builder import normalize_profile, DEFAULT_SCOPES


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


def test_profile_blocklist_roundtrip(temp_db):
    pid = db_ops.upsert_active_profile({
        "name": "default",
        "blocked_companies": ["Evil Corp", "Spam Inc"],
        "title_blocklist": ["Senior", "Staff"],
        "keyword_groups": [
            {"label": "Role", "terms": ["intern"], "scopes": ["title"]},
            {"label": "Domain", "terms": ["machine learning"], "scopes": ["title", "description"]},
        ],
    })
    saved = db_ops.get_profile_by_id(pid)
    assert saved["blocked_companies"] == ["Evil Corp", "Spam Inc"]
    assert saved["title_blocklist"] == ["Senior", "Staff"]
    assert saved["keyword_groups"][0]["scopes"] == ["title"]
    assert saved["keyword_groups"][1]["scopes"] == ["title", "description"]


def test_profile_defaults_empty(temp_db):
    # A profile created without the new fields exposes empty lists, not None.
    pid = db_ops.upsert_active_profile({"name": "default", "skills": ["python"]})
    saved = db_ops.get_active_profile()
    assert saved["id"] == pid
    assert saved["blocked_companies"] == []
    assert saved["title_blocklist"] == []


def test_update_preserves_and_overwrites(temp_db):
    pid = db_ops.upsert_active_profile({"name": "default", "blocked_companies": ["A"]})
    db_ops.update_profile(pid, {"blocked_companies": ["A", "B"]})
    assert db_ops.get_profile_by_id(pid)["blocked_companies"] == ["A", "B"]


def test_normalize_profile_scopes_default():
    # Groups without scopes default to both; string/invalid scopes are coerced.
    out = normalize_profile({
        "keyword_groups": [
            {"label": "G1", "terms": ["a"]},                       # no scopes -> both
            {"label": "G2", "terms": ["b"], "scopes": "title"},    # string -> [title]
            {"label": "G3", "terms": ["c"], "scopes": ["bogus"]},  # invalid -> both
            {"label": "G4", "terms": ["d"], "scopes": ["description", "title"]},
        ],
        "blocked_companies": ["Foo", "", "  Bar  "],
        "title_blocklist": ["Senior"],
    })
    groups = out["keyword_groups"]
    assert groups[0]["scopes"] == DEFAULT_SCOPES
    assert groups[1]["scopes"] == ["title"]
    assert groups[2]["scopes"] == DEFAULT_SCOPES
    # order is normalized to (title, description) regardless of input order
    assert groups[3]["scopes"] == ["title", "description"]
    assert out["blocked_companies"] == ["Foo", "Bar"]
    assert out["title_blocklist"] == ["Senior"]


def test_migration_idempotent(tmp_path, monkeypatch):
    # Build a DB missing the new columns, then run the migration twice.
    import sqlite3
    from utils.backend.database import migrate_profile_blocklists as mig

    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT, keyword_groups TEXT)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(mig, "DATABASE_PATH", db_file)
    mig.migrate()
    mig.migrate()  # second run must be a no-op, not an error

    conn = sqlite3.connect(db_file)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)")}
    conn.close()
    assert "blocked_companies" in cols
    assert "title_blocklist" in cols
