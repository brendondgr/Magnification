"""
Regression tests: a saved job (``saved=1``) is an explicit user keep and is NEVER auto-hidden
by the two filters that set ``ignore=1`` without user action:

  * ``apply_profile_filters()``  — runs on Profile Save / Block Company, over all jobs.
  * ``filter_and_mark_jobs()``   — runs during a job search over the newly-stored ids.

This locks in the fix for the reported bug where saved jobs kept getting re-hidden after the
user un-hid them (on a search, profile save, block-company, or daily-search-on-boot).

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time — mirroring
``tests/database/test_job_saved.py``.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.scrapers import job_filter
from utils.backend.scrapers.job_filter import apply_profile_filters, filter_and_mark_jobs


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


def _add(title, company, description="", saved=0, ignore=0):
    jid = db_ops.add_job(
        {"title": title, "company": company, "location": "x", "description": description},
        create_statuses=False,
    )
    if saved:
        db_ops.set_job_saved(jid, 1)
    if ignore:
        db_ops.set_job_ignore(jid, 1)
    return jid


def test_apply_profile_filters_exempts_saved_job(temp_db):
    """A saved job matching a block rule stays visible; an identical non-saved job is hidden."""
    db_ops.create_profile({"name": "p", "is_active": 1, "blocked_companies": ["Tesla"]})
    saved_id = _add("AI Intern", "Tesla", "ai", saved=1, ignore=0)
    other_id = _add("AI Intern", "Tesla", "ai")  # same blocked company, not saved

    res = apply_profile_filters()

    assert res["blocked"] == 1  # only the non-saved job was hidden
    assert db_ops.get_job_by_id(saved_id)["ignore"] == 0  # saved job untouched
    assert db_ops.get_job_by_id(other_id)["ignore"] == 1  # non-saved job hidden


def test_apply_profile_filters_exempts_saved_for_title_and_keyword_rules(temp_db):
    """The exemption holds for title-blocklist and unsatisfied keyword-group rules too."""
    db_ops.create_profile(
        {
            "name": "p",
            "is_active": 1,
            "title_blocklist": ["senior"],
            "keyword_groups": [{"label": "Role", "terms": ["intern"], "scopes": ["title"]}],
        }
    )
    # Saved job that (a) hits the title blocklist and (b) fails the keyword group.
    saved_id = _add("Senior Engineer", "Acme", "backend", saved=1, ignore=0)
    other_id = _add("Senior Engineer", "Acme", "backend")

    apply_profile_filters()

    assert db_ops.get_job_by_id(saved_id)["ignore"] == 0
    assert db_ops.get_job_by_id(other_id)["ignore"] == 1


def test_filter_and_mark_jobs_exempts_saved_job(temp_db, monkeypatch):
    """A saved job failing the jobs_config keyword filter is kept; a non-saved one is hidden."""
    # Pin an explicit jobs_config so the assertion is deterministic regardless of the host's
    # real jobs_config.json contents.
    cfg = {"job_titles": [], "description_keywords": [["python"]]}
    monkeypatch.setattr(job_filter, "load_filter_config", lambda: cfg)

    saved_id = _add("Cook", "Diner", "no relevant terms here", saved=1, ignore=0)
    other_id = _add("Cook", "Diner", "no relevant terms here")

    res = filter_and_mark_jobs([saved_id, other_id])

    assert res["ignored"] == 1  # only the non-saved job was hidden
    assert db_ops.get_job_by_id(saved_id)["ignore"] == 0  # saved job kept
    assert db_ops.get_job_by_id(other_id)["ignore"] == 1  # non-saved job hidden
