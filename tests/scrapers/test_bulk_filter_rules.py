"""
Tests for the ad-hoc bulk-hide rules behind the New Jobs **Filter** popup
(``utils.backend.scrapers.bulk_filter``).

Covers each criterion alone (keyword kill-list, found-before date, minimum match, industry set),
the OR combination, the saved-job exemption, the already-hidden skip, the unscored-job default
and its opt-in, the ``Unclassified`` industry sentinel, and dry-run purity.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching the
module-level ``SessionLocal`` that ``get_db_context`` resolves at call time — mirroring
``tests/scrapers/test_apply_all_filters.py``.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.scrapers.bulk_filter import (
    UNCLASSIFIED, apply_bulk_filters, job_matches_bulk_rules,
    normalize_bulk_rules, rules_are_empty,
)


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


def _add(title="Engineer", company="Acme", description="", industry=None,
         days_ago=0, match=None, saved=0, ignore=0):
    jid = db_ops.add_job(
        {"title": title, "company": company, "location": "x", "description": description},
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


def _ignored(job_id):
    return db_ops.get_job_by_id(job_id)["ignore"] == 1


# ---------------------------------------------------------------- normalization


def test_normalize_lowercases_dedupes_and_clamps():
    rules = normalize_bulk_rules({
        "keywords": ["Senior", "senior", "  ", "Clearance "],
        "keyword_scopes": ["title", "bogus"],
        "min_match": "142",
        "industries": ["Retail", "retail", ""],
        "found_before": "2026-01-05",
    })
    assert rules["keywords"] == ["senior", "clearance"]
    assert rules["keyword_scopes"] == ["title"]
    assert rules["min_match"] == 100
    assert rules["industries"] == ["Retail"]
    assert rules["found_before"].isoformat() == "2026-01-05"


def test_normalize_defaults_scopes_to_both_and_rejects_bad_dates():
    assert normalize_bulk_rules({})["keyword_scopes"] == ["title", "description"]
    with pytest.raises(ValueError):
        normalize_bulk_rules({"found_before": "05/01/2026"})


def test_rules_are_empty_only_when_no_criterion_is_enabled():
    assert rules_are_empty(normalize_bulk_rules({}))
    # hide_unscored on its own is a modifier, not a criterion.
    assert rules_are_empty(normalize_bulk_rules({"hide_unscored": True}))
    assert not rules_are_empty(normalize_bulk_rules({"min_match": 0}))


# ---------------------------------------------------------------- predicate


def test_keyword_scope_limits_where_terms_are_matched():
    job = {"title": "Senior Engineer", "description": "great team"}
    title_only = normalize_bulk_rules({"keywords": ["senior"], "keyword_scopes": ["description"]})
    assert job_matches_bulk_rules(job, None, title_only) == []
    both = normalize_bulk_rules({"keywords": ["senior"]})
    assert job_matches_bulk_rules(job, None, both) == ["keywords"]


def test_unclassified_sentinel_selects_jobs_with_no_industry_label():
    rules = normalize_bulk_rules({"industries": [UNCLASSIFIED]})
    assert job_matches_bulk_rules({"industry": None}, None, rules) == ["industry"]
    assert job_matches_bulk_rules({"industry": "Tech"}, None, rules) == []


def test_a_job_can_trip_several_criteria_at_once():
    rules = normalize_bulk_rules({"keywords": ["senior"], "industries": ["Retail"]})
    reasons = job_matches_bulk_rules({"title": "Senior Clerk", "industry": "Retail"}, None, rules)
    assert reasons == ["keywords", "industry"]


# ---------------------------------------------------------------- driver


def test_empty_rules_are_a_no_op(temp_db):
    keep = _add(title="Engineer")
    result = apply_bulk_filters({})
    assert result == {
        "checked": 0, "matched": 0, "hidden": 0, "job_ids": [],
        "breakdown": {"keywords": 0, "date": 0, "match": 0, "industry": 0},
        "dry_run": False,
    }
    assert not _ignored(keep)


def test_keyword_kill_list_hides_matching_jobs_only(temp_db):
    doomed = _add(title="Senior Engineer")
    kept = _add(title="Junior Engineer")
    desc_hit = _add(title="Analyst", description="requires an active clearance")

    result = apply_bulk_filters({"keywords": ["senior", "clearance"]})

    assert result["matched"] == 2
    assert result["breakdown"]["keywords"] == 2
    assert _ignored(doomed) and _ignored(desc_hit)
    assert not _ignored(kept)


def test_found_before_hides_older_jobs(temp_db):
    old = _add(title="Old", days_ago=40)
    fresh = _add(title="Fresh", days_ago=1)
    cutoff = (datetime.utcnow() - timedelta(days=7)).date().isoformat()

    result = apply_bulk_filters({"found_before": cutoff})

    assert result["breakdown"]["date"] == 1
    assert _ignored(old)
    assert not _ignored(fresh)


def test_min_match_hides_weak_matches_and_keeps_unscored_by_default(temp_db):
    weak = _add(title="Weak", match=12)
    strong = _add(title="Strong", match=80)
    unscored = _add(title="Unscored")

    result = apply_bulk_filters({"min_match": 40})

    assert result["breakdown"]["match"] == 1
    assert _ignored(weak)
    assert not _ignored(strong)
    assert not _ignored(unscored)


def test_hide_unscored_opt_in_also_removes_never_analyzed_jobs(temp_db):
    unscored = _add(title="Unscored")
    strong = _add(title="Strong", match=80)

    apply_bulk_filters({"min_match": 40, "hide_unscored": True})

    assert _ignored(unscored)
    assert not _ignored(strong)


def test_industry_selection_hides_selected_labels_and_unclassified(temp_db):
    retail = _add(title="Clerk", industry="Retail")
    tech = _add(title="Dev", industry="Tech")
    unlabelled = _add(title="Mystery")

    result = apply_bulk_filters({"industries": ["Retail", UNCLASSIFIED]})

    assert result["breakdown"]["industry"] == 2
    assert _ignored(retail) and _ignored(unlabelled)
    assert not _ignored(tech)


def test_criteria_are_ored_together(temp_db):
    by_keyword = _add(title="Senior Engineer", industry="Tech", match=90)
    by_industry = _add(title="Analyst", industry="Retail", match=90)
    survivor = _add(title="Analyst", industry="Tech", match=90)

    result = apply_bulk_filters({
        "keywords": ["senior"], "industries": ["Retail"], "min_match": 10,
    })

    assert result["matched"] == 2
    assert _ignored(by_keyword) and _ignored(by_industry)
    assert not _ignored(survivor)


def test_saved_jobs_are_exempt_and_hidden_jobs_are_skipped(temp_db):
    saved = _add(title="Senior Saved", saved=1)
    already = _add(title="Senior Hidden", ignore=1)
    fresh = _add(title="Senior Fresh")

    result = apply_bulk_filters({"keywords": ["senior"]})

    assert result["checked"] == 1
    assert result["job_ids"] == [fresh]
    assert not _ignored(saved)
    assert _ignored(already)  # untouched — it was already hidden


def test_dry_run_counts_without_writing(temp_db):
    doomed = _add(title="Senior Engineer")

    preview = apply_bulk_filters({"keywords": ["senior"]}, dry_run=True)

    assert preview["matched"] == 1
    assert preview["hidden"] == 0
    assert preview["dry_run"] is True
    assert not _ignored(doomed)


def test_job_ids_scope_limits_the_pass(temp_db):
    inside = _add(title="Senior A")
    outside = _add(title="Senior B")

    apply_bulk_filters({"keywords": ["senior"]}, job_ids=[inside])

    assert _ignored(inside)
    assert not _ignored(outside)
