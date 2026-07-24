"""
Lightweight, idempotent migration that adds the jobs.industry and jobs.industry_checked
columns to an existing SQLite database. ``industry`` stores the job's detected industry/genre
(one of a fixed taxonomy, extracted from the description by the LLM); ``industry_checked``
records that the classification already ran (0 = not yet, 1 = checked) so jobs are not
re-queried on every "Analyze Matches"/scrape run. Mirrors ``migrate_job_compensation_checked``.

New databases created via ``Base.metadata.create_all`` already include the columns; this only
patches pre-existing databases. Safe to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH

_COLUMNS = {
    "industry": "VARCHAR(64)",
    "industry_checked": "INTEGER DEFAULT 0",
}


def migrate() -> None:
    """Add the jobs.industry / industry_checked columns if missing. No-op when the DB or table is absent."""
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
        for column, coltype in _COLUMNS.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {coltype}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Job industry migration complete.")
