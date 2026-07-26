"""
Tests for the malformed-compensation repair migration.

Runs against a throwaway SQLite file (never the shared real database — see
docs/workflow.md) by pointing the migration module's DATABASE_PATH at a tmp_path file.
"""

import sqlite3

import pytest

from utils.backend.database import migrate_clean_bad_compensation as mig

_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY,
    title TEXT,
    compensation TEXT,
    compensation_checked INTEGER DEFAULT 0
)
"""

_ROWS = [
    (1, "Nurse", "USDnan - USDnan hourly", 1),
    (2, "Cook", "nannan - nannan nan", 1),
    (3, "Engineer", "$120,000 - $150,000 a year", 1),
    (4, "Analyst", "", 0),
    (5, "Clerk", "competitive salary", 1),   # no digits -> not real pay
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


def _rows(path):
    conn = sqlite3.connect(path)
    try:
        return {r[0]: (r[1], r[2]) for r in
                conn.execute("SELECT id, compensation, compensation_checked FROM jobs")}
    finally:
        conn.close()


def test_blanks_malformed_values_and_reopens_them_for_extraction(db):
    assert mig.migrate() == 3
    rows = _rows(db)
    for job_id in (1, 2, 5):
        assert rows[job_id] == ("", 0), f"job {job_id} not repaired"
    # Real pay and already-empty rows are untouched.
    assert rows[3] == ("$120,000 - $150,000 a year", 1)
    assert rows[4] == ("", 0)


def test_is_idempotent(db):
    assert mig.migrate() == 3
    assert mig.migrate() == 0


def test_no_op_without_a_database(tmp_path, monkeypatch):
    monkeypatch.setattr(mig, "DATABASE_PATH", tmp_path / "missing.db")
    assert mig.migrate() == 0
