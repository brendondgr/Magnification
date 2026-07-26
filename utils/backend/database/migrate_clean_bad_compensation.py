"""
Lightweight, idempotent migration that scrubs malformed compensation strings already stored.

Boards (Indeed in particular) hand JobSpy pandas ``NaN`` salary amounts. ``float('nan')`` is
truthy and formats as ``"nan"``, so the old salary formatter wrote rows like
``"USDnan - USDnan hourly"`` and ``"nannan - nannan nan"``. Those strings are non-empty, so
they both render as garbage on the card **and** made the job look like it already had pay,
permanently blocking description-based recovery.

This blanks every such value and clears the row's ``compensation_checked`` flag so the shared
enrichment pass re-derives the real figure from the description. The producers are fixed in
``scrapers/jobspy_wrapper.build_compensation_string``; this repairs the history. Safe (and
cheap — it only touches rows that still match) to run on every startup.
"""

import sqlite3

from .config import DATABASE_PATH
from ..recommend.compensation import clean_compensation

# Cheap SQL pre-filter: only rows that *might* be malformed are read into Python, where
# clean_compensation() makes the actual call. Keeps startup free on a healthy database.
_SUSPECT_SQL = """
    SELECT id, compensation FROM jobs
    WHERE compensation IS NOT NULL AND TRIM(compensation) != ''
      AND (LOWER(compensation) LIKE '%nan%' OR compensation NOT GLOB '*[0-9]*')
"""


def migrate() -> int:
    """Blank malformed jobs.compensation values. Returns the number of rows repaired."""
    if not DATABASE_PATH.exists():
        return 0

    conn = sqlite3.connect(DATABASE_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        if cursor.fetchone() is None:
            return 0

        cursor.execute("PRAGMA table_info(jobs)")
        columns = {row[1] for row in cursor.fetchall()}
        if "compensation" not in columns:
            return 0

        cursor.execute(_SUSPECT_SQL)
        bad_ids = [row[0] for row in cursor.fetchall() if clean_compensation(row[1]) is None]
        if not bad_ids:
            return 0

        # Clearing compensation_checked lets the description extractor try these again; the
        # column may be absent on a database that predates it.
        assignments = "compensation = ''"
        if "compensation_checked" in columns:
            assignments += ", compensation_checked = 0"
        cursor.executemany(
            f"UPDATE jobs SET {assignments} WHERE id = ?", [(i,) for i in bad_ids]
        )
        conn.commit()
        return len(bad_ids)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Cleaned {migrate()} malformed compensation value(s).")
