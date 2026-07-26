"""
Tests for the industry_checked repair migration.

Runs against a throwaway SQLite file (never the shared real database — see docs/workflow.md).
"""

import sqlite3

import pytest

from utils.backend.database import migrate_reset_unlabeled_industry as mig

_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    title TEXT,
    industry VARCHAR(64),
    industry_checked INTEGER DEFAULT 0
)
"""

_ROWS = [
    (1, "Nurse", "Health", 1),   # labeled -> keep the flag
    (2, "Cook", None, 1),        # stranded by the old behavior -> reopen
    (3, "Engineer", "", 1),      # ditto (empty string)
    (4, "Analyst", None, 0),     # already open
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    conn.executemany("INSERT INTO jobs VALUES (?,?,?,?)", _ROWS)
    conn.commit()
    conn.close()
    monkeypatch.setattr(mig, "DATABASE_PATH", path)
    return path


def _flags(path):
    conn = sqlite3.connect(path)
    try:
        return dict(conn.execute("SELECT id, industry_checked FROM jobs"))
    finally:
        conn.close()


def test_reopens_only_unlabeled_jobs(db):
    assert mig.migrate() == 2
    assert _flags(db) == {1: 1, 2: 0, 3: 0, 4: 0}


def test_is_idempotent(db):
    assert mig.migrate() == 2
    assert mig.migrate() == 0


def test_no_op_without_a_database(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "DATABASE_PATH", tmp_path / "missing.db")
    assert mig.migrate() == 0
