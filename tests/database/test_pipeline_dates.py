"""
Durable, write-once pipeline-date columns on ``jobs``.

Verifies that reaching a pipeline stage stamps the mapped ``date_first_*`` column exactly once
and that the value is never overwritten (re-reaching a later day) or cleared (un-checking the
status / moving a card backward). Runs against an isolated in-memory SQLite engine (never the
real dev DB) by patching the module-level ``SessionLocal`` that ``get_db_context`` resolves.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def _add_job():
    return db_ops.add_job(
        {"title": "SWE", "company": "Acme", "location": "Remote"},
        create_statuses=True,
    )


def test_pipeline_dates_exposed_and_default_null(temp_db):
    job = db_ops.get_job_by_id(_add_job())
    for key in (
        "date_found",
        "date_first_applied",
        "date_first_interview",
        "date_first_offer",
        "date_first_rejected",
        "date_first_ghosted",
    ):
        assert key in job, f"missing pipeline key: {key}"
    # "found" is always known (created_at); the stage dates start empty.
    assert job["date_found"] is not None
    assert job["date_first_applied"] is None
    assert job["date_first_ghosted"] is None


def test_stage_stamped_once_on_reach(temp_db):
    job_id = _add_job()
    db_ops.update_application_status(job_id, "Applied", 1, "2026-01-05")
    db_ops.update_application_status(job_id, "Interview 2", 1, "2026-02-10")
    db_ops.update_application_status(job_id, "Offer", 1, "2026-03-01")

    job = db_ops.get_job_by_id(job_id)
    assert job["date_first_applied"] == "2026-01-05"
    assert job["date_first_interview"] == "2026-02-10"
    assert job["date_first_offer"] == "2026-03-01"


def test_write_once_not_overwritten_on_re_reach(temp_db):
    job_id = _add_job()
    db_ops.update_application_status(job_id, "Applied", 1, "2026-01-05")
    # Reaching the same stage again on a later day must NOT move the first-applied date.
    db_ops.update_application_status(job_id, "Applied", 1, "2026-04-20")
    assert db_ops.get_job_by_id(job_id)["date_first_applied"] == "2026-01-05"


def test_date_not_cleared_when_moved_backward(temp_db):
    job_id = _add_job()
    db_ops.update_application_status(job_id, "Offer", 1, "2026-03-01")
    assert db_ops.get_job_by_id(job_id)["date_first_offer"] == "2026-03-01"

    # Dragging the card back to Applied un-checks Offer (clears its mutable date_reached),
    # but the durable pipeline record must remain.
    db_ops.update_application_status(job_id, "Offer", 0, None)
    job = db_ops.get_job_by_id(job_id)
    assert job["date_first_offer"] == "2026-03-01"
    # The mutable per-status date is cleared, proving the durability is independent of it.
    statuses = {s["status"]: s for s in db_ops.get_application_status_by_job(job_id)}
    assert statuses["Offer"]["checked"] == 0
    assert statuses["Offer"]["date_reached"] is None


def test_interview_first_round_wins(temp_db):
    job_id = _add_job()
    # Any interview round feeds the single first-interview date; earliest reached wins.
    db_ops.update_application_status(job_id, "Interview 1", 1, "2026-02-01")
    db_ops.update_application_status(job_id, "Interview 3", 1, "2026-02-15")
    assert db_ops.get_job_by_id(job_id)["date_first_interview"] == "2026-02-01"


def test_rejection_variants_map_to_one_column(temp_db):
    job_id = _add_job()
    db_ops.update_application_status(job_id, "Post-Interview Rejection", 1, "2026-05-09")
    assert db_ops.get_job_by_id(job_id)["date_first_rejected"] == "2026-05-09"
