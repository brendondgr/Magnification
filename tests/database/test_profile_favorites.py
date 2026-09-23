"""
Profile ``favorite_companies`` persistence: round-trip on an isolated in-memory engine and the
additive migration (adds the column once, second run is a no-op). Never touches the real DB.
"""

import sqlite3

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
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def test_favorites_roundtrip(temp_db):
    pid = db_ops.upsert_active_profile({"favorite_companies": ["Acme", "Globex"]})
    assert db_ops.get_profile_by_id(pid)["favorite_companies"] == ["Acme", "Globex"]


def test_favorites_default_empty_and_survive_other_updates(temp_db):
    pid = db_ops.upsert_active_profile({"skills": ["python"]})
    assert db_ops.get_profile_by_id(pid)["favorite_companies"] == []
    db_ops.upsert_active_profile({"favorite_companies": ["Acme"]})
    # A later save that doesn't mention favorites (e.g. a profile rebuild) leaves them alone.
    db_ops.upsert_active_profile({"skills": ["python", "sql"]})
    assert db_ops.get_active_profile()["favorite_companies"] == ["Acme"]


def test_migration_idempotent(tmp_path, monkeypatch):
    from utils.backend.database import migrate_profile_favorites as mig

    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(mig, "DATABASE_PATH", db_file)
    mig.migrate()
    mig.migrate()  # second run must be a no-op, not an error

    conn = sqlite3.connect(db_file)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(profiles)")}
    conn.close()
    assert "favorite_companies" in cols


def test_migration_noop_without_db(tmp_path, monkeypatch):
    from utils.backend.database import migrate_profile_favorites as mig

    monkeypatch.setattr(mig, "DATABASE_PATH", tmp_path / "missing.db")
    mig.migrate()
    assert not (tmp_path / "missing.db").exists()
