"""
Contract tests for the New Jobs **Filter** popup's two endpoints:

  * ``GET  /api/jobs/filter/options`` — the facets the popup builds its controls from.
  * ``POST /api/jobs/filter`` — now two modes: the legacy saved-rules pass (empty body) and the
    ad-hoc ``rules`` pass, with an optional ``dry_run``.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.scrapers import job_filter


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
    # Pin the saved rule sets so the legacy mode doesn't depend on the host's real config.
    monkeypatch.setattr(job_filter, "load_filter_config",
                        lambda: {"job_titles": [], "description_keywords": []})
    yield engine
    engine.dispose()


@pytest.fixture()
def client():
    with application.test_client() as c:
        yield c


def _add(title="Engineer", industry=None, days_ago=0, match=None, saved=0, ignore=0):
    jid = db_ops.add_job(
        {"title": title, "company": "Acme", "location": "x", "description": ""},
        create_statuses=False,
    )
    updates = {"created_at": datetime.utcnow() - timedelta(days=days_ago)}
    if industry is not None:
        updates["industry"] = industry
    db_ops.update_job(jid, updates)
    if match is not None:
        db_ops.save_job_analysis(jid, {"rag_score": match / 100.0})
    if saved:
        db_ops.set_job_saved(jid, 1)
    if ignore:
        db_ops.set_job_ignore(jid, 1)
    return jid


# ---------------------------------------------------------------- facets


def test_filter_options_reports_industries_scores_and_date_bounds(temp_db, client):
    _add(title="Dev", industry="Tech", match=70, days_ago=30)
    _add(title="Dev2", industry="Tech")
    _add(title="Clerk", industry="Retail")
    _add(title="Mystery")

    body = client.get("/api/jobs/filter/options").get_json()

    assert body["success"] is True
    assert body["total"] == 4
    assert body["industries"] == [
        {"label": "Tech", "count": 2},
        {"label": "Retail", "count": 1},
    ]
    assert body["unclassified"] == 1
    assert body["scored"] == 1
    assert body["unscored"] == 3
    assert body["oldest"] < body["newest"]


def test_filter_options_excludes_hidden_and_saved_jobs(temp_db, client):
    _add(title="Visible", industry="Tech")
    _add(title="Hidden", industry="Retail", ignore=1)
    _add(title="Saved", industry="Legal", saved=1)

    body = client.get("/api/jobs/filter/options").get_json()

    assert body["total"] == 1
    assert body["industries"] == [{"label": "Tech", "count": 1}]


def test_filter_options_on_an_empty_feed(temp_db, client):
    body = client.get("/api/jobs/filter/options").get_json()
    assert body["total"] == 0
    assert body["industries"] == []
    assert body["oldest"] is None and body["newest"] is None


# ---------------------------------------------------------------- filter route


def test_empty_body_still_runs_the_saved_rules_pass(temp_db, client):
    kept = _add(title="Engineer")

    res = client.post("/api/jobs/filter", json={})

    assert res.status_code == 200
    assert res.get_json() == {"success": True, "checked": 1, "hidden": 0}
    assert db_ops.get_job_by_id(kept)["ignore"] == 0


def test_dry_run_reports_the_breakdown_without_writing(temp_db, client):
    doomed = _add(title="Senior Engineer", industry="Retail")
    kept = _add(title="Junior Engineer", industry="Tech")

    body = client.post("/api/jobs/filter", json={
        "rules": {"keywords": ["senior"], "industries": ["Retail"]},
        "dry_run": True,
    }).get_json()

    assert body["success"] is True
    assert body["checked"] == 2
    assert body["matched"] == 1
    assert body["hidden"] == 0
    assert body["dry_run"] is True
    assert body["breakdown"] == {"keywords": 1, "date": 0, "match": 0, "industry": 1}
    assert body["job_ids"] == [doomed]
    assert db_ops.get_job_by_id(doomed)["ignore"] == 0
    assert db_ops.get_job_by_id(kept)["ignore"] == 0


def test_committing_a_rules_pass_hides_the_matched_jobs(temp_db, client):
    weak = _add(title="Engineer", match=10)
    strong = _add(title="Engineer", match=90)

    body = client.post("/api/jobs/filter", json={"rules": {"min_match": 50}}).get_json()

    assert body["hidden"] == 1
    assert body["dry_run"] is False
    assert db_ops.get_job_by_id(weak)["ignore"] == 1
    assert db_ops.get_job_by_id(strong)["ignore"] == 0


def test_a_malformed_date_is_a_400(temp_db, client):
    res = client.post("/api/jobs/filter", json={"rules": {"found_before": "yesterday"}})

    assert res.status_code == 400
    body = res.get_json()
    assert body["success"] is False
    assert "YYYY-MM-DD" in body["error"]


def test_rules_pass_respects_the_job_ids_scope(temp_db, client):
    inside = _add(title="Senior A")
    outside = _add(title="Senior B")

    client.post("/api/jobs/filter", json={
        "rules": {"keywords": ["senior"]}, "job_ids": [inside],
    })

    assert db_ops.get_job_by_id(inside)["ignore"] == 1
    assert db_ops.get_job_by_id(outside)["ignore"] == 0
