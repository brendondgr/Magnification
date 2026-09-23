"""
Lightweight, idempotent migration that adds ``profiles.favorite_companies`` (a JSON list of
starred company names) to an existing SQLite database.

New databases created via ``Base.metadata.create_all`` already include the column; this
migration only patches pre-existing databases. It is safe to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH


def migrate() -> None:
    """Add ``profiles.favorite_companies`` if missing. No-op when the DB or table is absent."""
    if not DATABASE_PATH.exists():
        return

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'"
        )
        if cursor.fetchone() is None:
            return

        cursor.execute("PRAGMA table_info(profiles)")
        existing = {row[1] for row in cursor.fetchall()}
        # JSON columns are stored as TEXT by SQLAlchemy's JSON type on SQLite.
        if "favorite_companies" not in existing:
            cursor.execute("ALTER TABLE profiles ADD COLUMN favorite_companies TEXT")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Profile favorites migration complete.")
