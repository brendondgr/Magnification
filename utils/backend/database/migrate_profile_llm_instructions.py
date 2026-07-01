"""
Lightweight, idempotent migration that adds the profiles.llm_instructions column to an
existing SQLite database (free-text guidance for the LLM profile build).

New databases created via ``Base.metadata.create_all`` already include the column; this only
patches pre-existing databases. Safe to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH

_COLUMN = "llm_instructions"
_COLUMN_TYPE = "TEXT"


def migrate() -> None:
    """Add the llm_instructions column if missing. No-op when the DB or column is absent."""
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
        if _COLUMN not in existing:
            cursor.execute(f"ALTER TABLE profiles ADD COLUMN {_COLUMN} {_COLUMN_TYPE}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Profile llm_instructions migration complete.")
