"""
Round-trip test for the `saved` flag: `set_job_saved()` + `_job_to_dict` serialization.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time.
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


def test_set_job_saved_round_trip(temp_db):
    job_id = db_ops.add_job(
        {"title": "SWE", "company": "Acme", "location": "Remote"},
        create_statuses=True,
    )

    # Default is not saved and the flag is serialized.
    job = db_ops.get_job_by_id(job_id)
    assert job["saved"] == 0
    assert "saved" in job

    # Save it.
    assert db_ops.set_job_saved(job_id, 1) is True
    assert db_ops.get_job_by_id(job_id)["saved"] == 1

    # Saving is independent of the ignore flag.
    assert db_ops.set_job_ignore(job_id, 1) is True
    saved_and_ignored = db_ops.get_job_by_id(job_id)
    assert saved_and_ignored["saved"] == 1
    assert saved_and_ignored["ignore"] == 1

    # Unsave it.
    assert db_ops.set_job_saved(job_id, 0) is True
    assert db_ops.get_job_by_id(job_id)["saved"] == 0

    # Missing job -> False.
    assert db_ops.set_job_saved(999999, 1) is False
