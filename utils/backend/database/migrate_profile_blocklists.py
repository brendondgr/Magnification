"""
Lightweight, idempotent migration that adds the profile blocklist columns to an
existing SQLite database:

  * profiles.blocked_companies  (JSON list of company names to hide)
  * profiles.title_blocklist    (JSON list of title substrings to hide)

New databases created via ``Base.metadata.create_all`` already include these columns;
this migration only patches pre-existing databases. It is safe to run on every startup.

(The scoped ``keyword_groups`` change needs no migration — that column is already JSON and
the per-group ``scopes`` key is handled in normalization.)
"""

import sqlite3

from .config import DATABASE_PATH

# column name -> SQLite column type. JSON columns are stored as TEXT by SQLAlchemy's
# JSON type on SQLite, so we add them as TEXT.
_NEW_COLUMNS = {
    "blocked_companies": "TEXT",
    "title_blocklist": "TEXT",
}


def migrate() -> None:
    """Add any missing profile blocklist columns. No-op when the DB or columns are absent."""
    if not DATABASE_PATH.exists():
        return

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        # If the profiles table doesn't exist yet, create_all will make it with the columns.
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'"
        )
        if cursor.fetchone() is None:
            return

        cursor.execute("PRAGMA table_info(profiles)")
        existing = {row[1] for row in cursor.fetchall()}

        for column, col_type in _NEW_COLUMNS.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE profiles ADD COLUMN {column} {col_type}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
    print("Profile blocklist migration complete.")
