"""
Lightweight, idempotent migration that un-sticks jobs flagged as industry-checked but unlabeled.

The first version of the industry pass stamped ``industry_checked = 1`` on every attempted job,
including the ones where the LLM call failed or returned nothing. Since the model is asked to
*always* pick a label, "no answer" means the call failed — not that the job has no industry —
so those rows were permanently excluded from re-classification and their cards never showed a
pill. (On the real database that was 10 of the 17 visible jobs.)

``enrichment.enrich_jobs`` now only stamps the flag alongside a real label; this clears the
flag on the rows the old behavior stranded so they are asked again. Safe to run on every
startup — it only touches rows that are still in that state.
"""

import sqlite3

from .config import DATABASE_PATH

_RESET_SQL = """
    UPDATE jobs SET industry_checked = 0
    WHERE industry_checked = 1 AND (industry IS NULL OR TRIM(industry) = '')
"""


def migrate() -> int:
    """Clear industry_checked on jobs that carry no label. Returns the number of rows reset."""
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
        if not {"industry", "industry_checked"} <= columns:
            return 0

        cursor.execute(_RESET_SQL)
        conn.commit()
        return cursor.rowcount or 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    print(f"Re-opened {migrate()} job(s) for industry classification.")
