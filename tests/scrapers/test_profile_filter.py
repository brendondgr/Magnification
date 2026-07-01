"""
Unit tests for the pure profile block predicates (no DB).

Covers company block (exact, case-insensitive), title blocklist (substring), and the scoped
keyword-group hard filter (title-only vs both, AND across groups).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.scrapers import profile_filter as pf
from utils.backend.scrapers import job_filter
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


def test_company_blocked_case_insensitive_exact():
    blocked = ["Evil Corp"]
    assert pf.company_blocked("evil corp", blocked) is True
    assert pf.company_blocked("  EVIL CORP  ", blocked) is True
    # substring must NOT block (exact match only)
    assert pf.company_blocked("Evil Corporation", blocked) is False
    assert pf.company_blocked("", blocked) is False
    assert pf.company_blocked("Anything", []) is False


def test_title_blocked_substring():
    blocked = ["Senior", "Staff"]
    assert pf.title_blocked("Senior Software Engineer", blocked) is True
    assert pf.title_blocked("staff data scientist", blocked) is True   # case-insensitive
    assert pf.title_blocked("Software Engineer", blocked) is False
    assert pf.title_blocked("Engineer", []) is False


def test_keyword_group_title_only_scope():
    groups = [{"label": "Role", "terms": ["intern"], "scopes": ["title"]}]
    # intern only in description -> group unsatisfied
    assert pf.keyword_groups_satisfied("ML Engineer", "we train interns", groups) is False
    # intern in title -> satisfied
    assert pf.keyword_groups_satisfied("Data Science Intern", "great role", groups) is True


def test_keyword_group_both_scope():
    groups = [{"label": "Domain", "terms": ["machine learning"], "scopes": ["title", "description"]}]
    assert pf.keyword_groups_satisfied("ML Intern", "uses machine learning daily", groups) is True
    assert pf.keyword_groups_satisfied("machine learning engineer", "no match here", groups) is True
    assert pf.keyword_groups_satisfied("Analyst", "spreadsheets only", groups) is False


def test_keyword_group_missing_scopes_defaults_both():
    groups = [{"label": "Domain", "terms": ["python"]}]  # no scopes key
    assert pf.keyword_groups_satisfied("Backend role", "python and flask", groups) is True
    assert pf.keyword_groups_satisfied("python developer", "no match", groups) is True


def test_keyword_groups_and_across_groups():
    groups = [
        {"label": "Role", "terms": ["intern"], "scopes": ["title"]},
        {"label": "Domain", "terms": ["machine learning"], "scopes": ["title", "description"]},
    ]
    # both satisfied
    assert pf.keyword_groups_satisfied("ML Intern", "machine learning work", groups) is True
    # intern present but domain missing -> blocked
    assert pf.keyword_groups_satisfied("Software Intern", "web development", groups) is False
    # domain present but intern missing from title -> blocked
    assert pf.keyword_groups_satisfied("ML Engineer", "machine learning; trains interns", groups) is False


def test_job_blocked_by_profile_combines_rules():
    profile = {
        "blocked_companies": ["Evil Corp"],
        "title_blocklist": ["Senior"],
        "keyword_groups": [{"label": "Role", "terms": ["intern"], "scopes": ["title"]}],
    }
    # blocked by company
    assert pf.job_blocked_by_profile(
        {"title": "Data Intern", "company": "Evil Corp", "description": ""}, profile) is True
    # blocked by title blocklist
    assert pf.job_blocked_by_profile(
        {"title": "Senior Intern", "company": "Good Co", "description": ""}, profile) is True
    # blocked by unsatisfied keyword group (intern only in description)
    assert pf.job_blocked_by_profile(
        {"title": "Analyst", "company": "Good Co", "description": "train interns"}, profile) is True
    # passes everything
    assert pf.job_blocked_by_profile(
        {"title": "Data Intern", "company": "Good Co", "description": "great role"}, profile) is False
    # no profile -> never blocked
    assert pf.job_blocked_by_profile({"title": "x", "company": "y", "description": "z"}, None) is False


def test_apply_profile_filters_retroactively_hides(temp_db):
    db_ops.upsert_active_profile({
        "name": "default",
        "blocked_companies": ["Evil Corp"],
        "title_blocklist": ["Senior"],
    })
    keep_id = db_ops.add_job({"title": "Data Intern", "company": "Good Co", "location": "Remote"})
    company_id = db_ops.add_job({"title": "Engineer", "company": "Evil Corp", "location": "NYC"})
    title_id = db_ops.add_job({"title": "Senior Engineer", "company": "Good Co", "location": "NYC"})

    result = job_filter.apply_profile_filters()
    assert result["blocked"] == 2

    assert db_ops.get_job_by_id(keep_id)["ignore"] == 0
    assert db_ops.get_job_by_id(company_id)["ignore"] == 1
    assert db_ops.get_job_by_id(title_id)["ignore"] == 1

    # Idempotent: re-running blocks nothing new.
    assert job_filter.apply_profile_filters()["blocked"] == 0
