"""
Integration test for the reordered `execute_full_scraping_workflow()` pipeline:

    scrape -> in-batch dedup (Title+Company) -> drop jobs already in DB (Title+Company)
    -> fetch LinkedIn descriptions -> save new jobs -> apply title/keyword filters
    -> compensation extraction + recommendation scoring on the filtered remainder

Everything network/LLM-facing is stubbed; the database operations run against a real
in-memory SQLite engine (same pattern as tests/database/test_clear_jobs.py) so the
dedup/filter/persistence behavior is exercised for real.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base
from utils.backend.scrapers import scraping_service as svc
from utils.backend.scrapers import job_filter
from utils.backend.llm import config as llm_config_module
from utils.backend.llm import client as llm_client_module
from utils.backend.recommend import compensation as compensation_module
from utils.backend.recommend import service as recommend_service_module


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


def test_pipeline_order_skips_db_duplicates_and_filtered_jobs(temp_db, monkeypatch):
    # A job already tracked in the DB, seeded under a *different* location — the
    # Title+Company match must still catch it as a duplicate.
    db_ops.add_job({"title": "Already Tracked Role", "company": "OldCo", "location": "Some Other City"})

    raw_jobs = [
        {"title": "Backend Engineer", "company": "Acme", "location": "New York, NY",
         "site": "indeed", "description": "We need someone who knows python.",
         "compensation": "", "link": "http://a"},
        {"title": "Backend Engineer", "company": "Acme", "location": "Austin, TX",
         "site": "indeed", "description": "We need someone who knows python.",
         "compensation": "", "link": "http://a2"},  # in-batch duplicate of the job above
        {"title": "Data Scientist", "company": "Globex", "location": "Remote",
         "site": "linkedin", "description": "", "compensation": "", "link": "http://b"},
        {"title": "Marketing Manager", "company": "Initech", "location": "Boston, MA",
         "site": "indeed", "description": "no relevant skills mentioned",
         "compensation": "", "link": "http://c"},  # will fail the keyword filter
        {"title": "Already Tracked Role", "company": "OldCo", "location": "Remote",
         "site": "linkedin", "description": "", "compensation": "", "link": "http://d"},
    ]

    order = []
    fetched_for = []
    compensation_for = []
    analysis_for = []

    class FakeScraper:
        def __init__(self, **kwargs):
            self.all_jobs = raw_jobs

        def run(self):
            order.append("scrape")

        def get_summary(self):
            return {}

    def fake_load_jobs_config():
        return {"search_terms": ["Engineer"], "sites": ["indeed", "linkedin"]}

    def fake_load_filter_config():
        return {"job_titles": [], "description_keywords": [["python"]]}

    def fake_fetch_descriptions_for_jobs(jobs, progress_callback=None, only_these_jobs=None,
                                          max_workers=None, delay=None):
        order.append("fetch_descriptions")
        fetched_for.extend(sorted((j["title"], j["company"]) for j in (only_these_jobs or [])))
        for j in (only_these_jobs or []):
            j["description"] = f"{j['title']} needs python skills"
        return jobs

    def fake_extract_compensation_llm(jobs, client, max_workers=4, max_chars=6000):
        order.append("compensation")
        compensation_for.extend(sorted(j["title"] for j in jobs))
        updated = 0
        for j in jobs:
            if j["title"] == "Data Scientist":
                j["compensation"] = "$100,000 - $130,000"
                updated += 1
        return updated

    def fake_analyze_jobs(job_ids=None, profile=None, runtime=None, progress_callback=None):
        order.append("analysis")
        analysis_for.extend(sorted(job_ids or []))
        return {"success": True, "analyzed": len(job_ids or []), "profile_id": 1, "top": []}

    monkeypatch.setattr(svc, "JobSpyScraper", FakeScraper)
    monkeypatch.setattr(svc, "load_jobs_config", fake_load_jobs_config)
    monkeypatch.setattr(svc, "load_filter_config", fake_load_filter_config)
    monkeypatch.setattr(job_filter, "load_filter_config", fake_load_filter_config)
    monkeypatch.setattr(svc, "fetch_descriptions_for_jobs", fake_fetch_descriptions_for_jobs)
    monkeypatch.setattr(db_ops, "get_active_profile",
                         lambda: {"id": 1, "blocked_companies": [], "title_blocklist": [], "keyword_groups": []})
    monkeypatch.setattr(llm_config_module, "load_llm_endpoint_config", lambda: {"enabled": True})
    monkeypatch.setattr(llm_client_module.OpenAIClient, "from_config", classmethod(lambda cls, **kw: object()))
    monkeypatch.setattr(compensation_module, "extract_compensation_llm", fake_extract_compensation_llm)
    monkeypatch.setattr(recommend_service_module, "analyze_jobs", fake_analyze_jobs)

    result = svc.execute_full_scraping_workflow(save_to_database=True)

    assert result["success"] is True
    assert not result["errors"], result["errors"]

    # Call order: LinkedIn fetch, then compensation, then recommendation analysis.
    assert order == ["scrape", "fetch_descriptions", "compensation", "analysis"]

    # Only the new LinkedIn job (not the already-tracked one) is ever fetched.
    assert fetched_for == [("Data Scientist", "Globex")]

    # In-batch dedup collapses the two Backend Engineer postings; DB dedup drops
    # "Already Tracked Role" before it ever reaches storage/fetch/compensation.
    assert result["steps"]["processing"]["processed_count"] == 4
    assert result["steps"]["db_dedup"]["removed"] == 1
    assert result["steps"]["db_dedup"]["remaining"] == 3

    stored_job_ids = result["steps"]["storage"]["job_ids"]
    assert result["steps"]["storage"]["stored_count"] == 3

    # The keyword filter drops Marketing Manager (no "python" in its description).
    assert result["steps"]["filtering"]["kept"] == 2
    assert result["steps"]["filtering"]["ignored"] == 1

    # Compensation extraction only ever sees the two kept jobs — never the filtered-out
    # Marketing Manager, and never the already-tracked duplicate.
    assert compensation_for == ["Backend Engineer", "Data Scientist"]

    # Recommendation analysis is handed every stored job id (it self-filters ignored ones).
    assert analysis_for == sorted(stored_job_ids)

    # DB state: no duplicate row was created for the already-tracked job.
    all_jobs = db_ops.get_all_jobs(include_ignored=True)
    assert sum(1 for j in all_jobs if j["company"] == "OldCo") == 1

    by_title = {j["title"]: j for j in db_ops.get_jobs_by_ids(stored_job_ids)}
    assert by_title["Marketing Manager"]["ignore"] == 1
    assert by_title["Backend Engineer"]["ignore"] == 0
    assert by_title["Data Scientist"]["ignore"] == 0

    # Recovered compensation was persisted back to the database.
    assert by_title["Data Scientist"]["compensation"] == "$100,000 - $130,000"
    assert not by_title["Backend Engineer"]["compensation"]
