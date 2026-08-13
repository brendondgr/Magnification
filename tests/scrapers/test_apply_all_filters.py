"""
Tests for the on-demand "Filter" pass (`job_filter.apply_all_filters`) and its route,
``POST /api/jobs/filter``.

It re-applies BOTH rule sets to the currently visible feed:

  * the per-search ``jobs_config`` title / description keyword filter, and
  * the active profile's block rules (blocked companies, title blocklist, keyword groups).

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time — mirroring
``tests/scrapers/test_saved_job_filter_exempt.py``.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.scrapers import job_filter
from utils.backend.scrapers.job_filter import apply_all_filters

NO_CONFIG_FILTER = {"job_titles": [], "description_keywords": []}


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


def _pin_config(monkeypatch, cfg):
    """Pin jobs_config so assertions don't depend on the host's real jobs_config.json."""
    monkeypatch.setattr(job_filter, "load_filter_config", lambda: cfg)


def test_hides_jobs_failing_the_jobs_config_keywords(temp_db, monkeypatch):
    """The Find Jobs title/description keyword filter is applied retroactively."""
    _pin_config(monkeypatch, {"job_titles": ["engineer"], "description_keywords": [["python"]]})

    keep = _add("Software Engineer", "Acme", "we use python daily")
    bad_title = _add("Line Cook", "Diner", "python is on the menu")
    bad_desc = _add("Software Engineer", "Acme", "cobol only")

    res = apply_all_filters()

    assert res["checked"] == 3
    assert res["hidden"] == 2
    assert db_ops.get_job_by_id(keep)["ignore"] == 0
    assert db_ops.get_job_by_id(bad_title)["ignore"] == 1
    assert db_ops.get_job_by_id(bad_desc)["ignore"] == 1


def test_hides_jobs_matching_profile_block_rules(temp_db, monkeypatch):
    """Blocked companies, the title blocklist, and unsatisfied keyword groups all hide a job."""
    _pin_config(monkeypatch, NO_CONFIG_FILTER)
    db_ops.create_profile({
        "name": "p",
        "is_active": 1,
        "blocked_companies": ["Tesla"],
        "title_blocklist": ["senior"],
        "keyword_groups": [{"label": "Role", "terms": ["engineer"], "scopes": ["title"]}],
    })

    keep = _add("Software Engineer", "Acme", "backend")
    blocked_company = _add("Software Engineer", "Tesla", "backend")
    blocked_title = _add("Senior Engineer", "Acme", "backend")
    unsatisfied_group = _add("Data Analyst", "Acme", "backend")

    res = apply_all_filters()

    assert res["hidden"] == 3
    assert db_ops.get_job_by_id(keep)["ignore"] == 0
    for jid in (blocked_company, blocked_title, unsatisfied_group):
        assert db_ops.get_job_by_id(jid)["ignore"] == 1


def test_saved_jobs_are_exempt_and_hidden_jobs_are_left_alone(temp_db, monkeypatch):
    """Saved jobs are never auto-hidden; already-hidden jobs are not re-counted."""
    _pin_config(monkeypatch, NO_CONFIG_FILTER)
    db_ops.create_profile({"name": "p", "is_active": 1, "blocked_companies": ["Tesla"]})

    saved_id = _add("AI Intern", "Tesla", "ai", saved=1)
    already_hidden = _add("AI Intern", "Tesla", "ai", ignore=1)
    fresh = _add("AI Intern", "Tesla", "ai")

    res = apply_all_filters()

    assert res["checked"] == 1  # neither the saved nor the already-hidden job is re-checked
    assert res["hidden"] == 1
    assert db_ops.get_job_by_id(saved_id)["ignore"] == 0
    assert db_ops.get_job_by_id(already_hidden)["ignore"] == 1
    assert db_ops.get_job_by_id(fresh)["ignore"] == 1


def test_is_one_directional(temp_db, monkeypatch):
    """Nothing is ever un-hidden, even when a hidden job now passes every rule."""
    _pin_config(monkeypatch, NO_CONFIG_FILTER)
    hidden_but_passing = _add("Software Engineer", "Acme", "backend", ignore=1)

    apply_all_filters()

    assert db_ops.get_job_by_id(hidden_but_passing)["ignore"] == 1


def test_job_ids_scope_limits_the_pass(temp_db, monkeypatch):
    """Passing job_ids narrows the pass to those rows."""
    _pin_config(monkeypatch, {"job_titles": ["engineer"], "description_keywords": []})

    in_scope = _add("Line Cook", "Diner", "")
    out_of_scope = _add("Line Cook", "Diner", "")

    res = apply_all_filters([in_scope])

    assert res == {"checked": 1, "hidden": 1}
    assert db_ops.get_job_by_id(in_scope)["ignore"] == 1
    assert db_ops.get_job_by_id(out_of_scope)["ignore"] == 0


def test_filter_route_returns_counts_and_hides(temp_db, monkeypatch):
    """POST /api/jobs/filter reports {success, checked, hidden} and flips the ignore flag."""
    _pin_config(monkeypatch, {"job_titles": ["engineer"], "description_keywords": []})
    keep = _add("Software Engineer", "Acme", "")
    drop = _add("Line Cook", "Diner", "")

    import app as app_module
    client = app_module.application.test_client()
    res = client.post("/api/jobs/filter", json={})

    assert res.status_code == 200
    body = res.get_json()
    assert body == {"success": True, "checked": 2, "hidden": 1}
    assert db_ops.get_job_by_id(keep)["ignore"] == 0
    assert db_ops.get_job_by_id(drop)["ignore"] == 1
