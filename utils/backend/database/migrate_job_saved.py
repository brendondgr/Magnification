"""
Lightweight, idempotent migration that adds the jobs.saved column to an existing SQLite
database (pins a job to the Saved lane; 0 = not saved, 1 = saved).

New databases created via ``Base.metadata.create_all`` already include the column; this only
patches pre-existing databases. Safe to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH

_COLUMN = "saved"
_COLUMN_TYPE = "INTEGER DEFAULT 0"


def migrate() -> None:
    """Add the jobs.saved column if missing. No-op when the DB or table is absent."""
    if not DATABASE_PATH.exists():
        return

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
        )
        if cursor.fetchone() is None:
            return

        cursor.execute("PRAGMA table_info(jobs)")
        existing = {row[1] for row in cursor.fetchall()}
        if _COLUMN not in existing:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {_COLUMN} {_COLUMN_TYPE}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Job saved migration complete.")
