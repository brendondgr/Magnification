"""
Lightweight, idempotent migration adding the durable, write-once pipeline-date columns to an
existing SQLite ``jobs`` table:

    date_first_applied, date_first_interview, date_first_offer,
    date_first_rejected, date_first_ghosted   (all TEXT, YYYY-MM-DD)

These record the FIRST time a job reached each pipeline stage and are never cleared or
overwritten afterwards, so the application pipeline history survives a card being dragged
backward (unlike the mutable per-status ``application_statuses.date_reached``). "Found" is not
a column here; the durable ``jobs.created_at`` already records it.

New databases created via ``Base.metadata.create_all`` already include the columns; this only
patches pre-existing databases. When a column is first added, its value is backfilled from the
earliest matching checked ``application_statuses.date_reached`` so existing history is kept.
Safe to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH

# column -> the application statuses whose earliest checked date_reached seeds it on backfill.
_COLUMNS = {
    "date_first_applied": ("Applied",),
    "date_first_interview": ("Interview 1", "Interview 2", "Interview 3"),
    "date_first_offer": ("Offer", "Accepted"),
    "date_first_rejected": ("Rejected", "Post-Interview Rejection"),
    "date_first_ghosted": ("Ignored/Ghosted",),
}


def _backfill(cursor: sqlite3.Cursor, column: str, statuses: tuple) -> None:
    """Seed a freshly added column with the earliest matching checked status date (per job)."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='application_statuses'"
    )
    if cursor.fetchone() is None:
        return
    placeholders = ",".join("?" for _ in statuses)
    cursor.execute(
        f"""
        UPDATE jobs SET {column} = (
            SELECT MIN(a.date_reached) FROM application_statuses a
            WHERE a.job_id = jobs.id AND a.checked = 1
              AND a.date_reached IS NOT NULL
              AND a.status IN ({placeholders})
        )
        WHERE {column} IS NULL
        """,
        statuses,
    )


def migrate() -> None:
    """Add the durable pipeline-date columns if missing (+ one-time backfill). No-op when the
    DB or ``jobs`` table is absent."""
    if not DATABASE_PATH.exists():
        return

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if cursor.fetchone() is None:
            return

        cursor.execute("PRAGMA table_info(jobs)")
        existing = {row[1] for row in cursor.fetchall()}
        for column, statuses in _COLUMNS.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
                _backfill(cursor, column, statuses)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Job pipeline-dates migration complete.")
