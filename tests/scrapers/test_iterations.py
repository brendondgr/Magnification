"""Max Iterations: the workflow re-scrapes with an advancing offset and dedups across passes.

Fully offline — the scraper, config, and DB layer are faked/monkeypatched, so no network
and no real database are touched.
"""

from utils.backend.scrapers import scraping_service as svc


class FakeScraper:
    """Stand-in for JobSpyScraper: records the offset and returns two jobs per page.

    Consecutive pages overlap by one job (offset N → Job{N}, Job{N+1}) so the database dedup
    has something to remove, exercising cross-iteration uniqueness.
    """
    offsets = []

    def __init__(self, **kwargs):
        self.offset = kwargs.get("offset", 0)
        FakeScraper.offsets.append(self.offset)
        base = self.offset
        self.all_jobs = [
            {"title": f"Job{base}", "company": "X", "site": "indeed", "job_url": f"u{base}"},
            {"title": f"Job{base + 1}", "company": "X", "site": "indeed", "job_url": f"u{base + 1}"},
        ]

    def run(self):
        return None

    def get_summary(self):
        return {}


class FakeDB:
    """A tiny in-memory job store keyed by (title, company) to mimic the DB dedup."""
    def __init__(self):
        self.keys = set()
        self.next_id = 1

    def get_existing_job_keys(self):
        return set(self.keys)

    def add_job(self, job):
        self.keys.add((job["title"].strip().lower(), job["company"].strip().lower()))
        jid = self.next_id
        self.next_id += 1
        return jid


def _patch_common(monkeypatch, config):
    FakeScraper.offsets = []
    db = FakeDB()
    monkeypatch.setattr(svc, "load_jobs_config", lambda: dict(config))
    monkeypatch.setattr(svc, "JobSpyScraper", FakeScraper)
    monkeypatch.setattr(svc, "process_scraped_jobs", lambda jobs: list(jobs))
    monkeypatch.setattr(svc, "get_job_statistics", lambda jobs: {})
    monkeypatch.setattr(svc, "filter_and_mark_jobs", lambda ids: {"kept": len(ids), "ignored": 0})
    # DB layer resolved lazily via `from ..database.operations import ...` — patch the source.
    from utils.backend.database import operations as db_ops
    monkeypatch.setattr(db_ops, "get_existing_job_keys", db.get_existing_job_keys)
    monkeypatch.setattr(db_ops, "add_job", db.add_job)
    monkeypatch.setattr(db_ops, "get_jobs_by_ids", lambda ids: [])
    monkeypatch.setattr(db_ops, "get_active_profile", lambda: None)  # skips analysis
    return db


def test_iterations_advance_offset_and_dedup(monkeypatch):
    """max_iterations=3 with results_wanted=1 → offsets 0,1,2; overlaps deduped to 4 unique."""
    _patch_common(monkeypatch, {
        "search_terms": ["ml"], "sites": ["indeed"],
        "results_wanted": 1, "max_iterations": 3,
    })
    result = svc.execute_full_scraping_workflow(save_to_database=True)
    assert result["success"] is True
    assert FakeScraper.offsets == [0, 1, 2]              # advancing pages
    assert result["steps"]["iterations"]["total_new_stored"] == 4  # Job0..Job3, overlaps dropped


def test_default_single_iteration(monkeypatch):
    """No max_iterations in config → a single pass at offset 0 (today's behavior)."""
    _patch_common(monkeypatch, {
        "search_terms": ["ml"], "sites": ["indeed"], "results_wanted": 20,
    })
    result = svc.execute_full_scraping_workflow(save_to_database=True)
    assert result["success"] is True
    assert FakeScraper.offsets == [0]
    assert "iterations" not in result["steps"]  # single-pass runs skip the iterations summary


def test_iterations_clamped_to_five(monkeypatch):
    """max_iterations above 5 is clamped to 5 passes."""
    _patch_common(monkeypatch, {
        "search_terms": ["ml"], "sites": ["indeed"],
        "results_wanted": 2, "max_iterations": 99,
    })
    result = svc.execute_full_scraping_workflow(save_to_database=True)
    assert result["success"] is True
    assert FakeScraper.offsets == [0, 2, 4, 6, 8]  # 5 passes, step = results_wanted
