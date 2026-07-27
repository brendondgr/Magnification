"""Cumulative "Jobs Found" / "Jobs Saved" across multi-iteration searches.

Each iteration builds a fresh scraper and rewrites its slice of `results['steps']`, so the
counters the Find Jobs progress view renders have to be accumulated at the workflow level.
These tests assert the run totals — and the progress stream feeding the live counters — are
cumulative and never walk backwards.

Fully offline: the scraper, config, and DB layer are faked, so no network and no real database.
"""

from utils.backend.scrapers import scraping_service as svc


class FakeScraper:
    """Returns `per_page` jobs per pass and replays a per-pass progress ramp.

    The progress callback reports this pass' own tally starting from zero — exactly what the
    real JobSpyScraper does, and the reason the workflow has to add the earlier passes' total.
    """
    per_page = 3
    offsets = []

    def __init__(self, **kwargs):
        self.offset = kwargs.get("offset", 0)
        self.progress_callback = kwargs.get("progress_callback")
        FakeScraper.offsets.append(self.offset)
        base = self.offset
        self.all_jobs = [
            {"title": f"Job{base + i}", "company": "X", "site": "indeed", "job_url": f"u{base + i}"}
            for i in range(FakeScraper.per_page)
        ]

    def run(self):
        # Two mid-pass progress ticks, each reporting only this pass' running count.
        if self.progress_callback:
            self.progress_callback(50.0, len(self.all_jobs) // 2)
            self.progress_callback(100.0, len(self.all_jobs))
        return None

    def get_summary(self):
        return {}


class FakeDB:
    """Tiny in-memory job store keyed by (title, company), mimicking the DB dedup."""

    def __init__(self, prefill=()):
        self.keys = {(t.strip().lower(), c.strip().lower()) for t, c in prefill}
        self.next_id = 1

    def get_existing_job_keys(self):
        return set(self.keys)

    def add_job(self, job):
        self.keys.add((job["title"].strip().lower(), job["company"].strip().lower()))
        jid = self.next_id
        self.next_id += 1
        return jid


def _run(monkeypatch, config, prefill=(), per_page=3):
    """Run the workflow against fakes; return (results, progress_events)."""
    FakeScraper.offsets = []
    FakeScraper.per_page = per_page
    db = FakeDB(prefill)
    monkeypatch.setattr(svc, "load_jobs_config", lambda: dict(config))
    monkeypatch.setattr(svc, "JobSpyScraper", FakeScraper)
    monkeypatch.setattr(svc, "process_scraped_jobs", lambda jobs: list(jobs))
    monkeypatch.setattr(svc, "get_job_statistics", lambda jobs: {})
    monkeypatch.setattr(svc, "filter_and_mark_jobs", lambda ids: {"kept": len(ids), "ignored": 0})
    from utils.backend.database import operations as db_ops
    monkeypatch.setattr(db_ops, "get_existing_job_keys", db.get_existing_job_keys)
    monkeypatch.setattr(db_ops, "add_job", db.add_job)
    monkeypatch.setattr(db_ops, "get_jobs_by_ids", lambda ids: [])
    monkeypatch.setattr(db_ops, "get_active_profile", lambda: None)  # skips analysis

    events = []
    results = svc.execute_full_scraping_workflow(
        save_to_database=True, progress_callback=lambda u: events.append(u)
    )
    return results, events


def _series(events, key):
    """Every reported value of `details[key]`, in emission order."""
    return [
        e["details"][key] for e in events
        if isinstance(e.get("details"), dict) and key in e["details"]
    ]


def _is_monotonic(values):
    return all(b >= a for a, b in zip(values, values[1:]))


THREE_PASSES = {
    "search_terms": ["ml"], "sites": ["indeed"],
    "results_wanted": 3, "max_iterations": 3,
}


def test_steps_hold_run_totals_not_last_pass(monkeypatch):
    """3 non-overlapping passes of 3 jobs → totals of 9, not the final pass' 3."""
    results, _ = _run(monkeypatch, THREE_PASSES)

    assert results["success"] is True
    assert FakeScraper.offsets == [0, 3, 6]
    assert results["steps"]["scraping"]["raw_jobs_count"] == 9
    assert results["steps"]["scraping"]["last_pass_count"] == 3
    assert results["steps"]["processing"]["processed_count"] == 9
    assert results["steps"]["storage"]["stored_count"] == 9
    assert results["steps"]["storage"]["last_pass_count"] == 3
    assert len(results["steps"]["storage"]["job_ids"]) == 9
    assert results["steps"]["iterations"]["total_new_stored"] == 9
    assert results["steps"]["iterations"]["total_unique"] == 9
    assert [p["stored"] for p in results["steps"]["iterations"]["passes"]] == [3, 3, 3]


def test_progress_jobs_found_is_cumulative_and_monotonic(monkeypatch):
    """The live "Jobs Found" counter never snaps back at an iteration boundary."""
    _, events = _run(monkeypatch, THREE_PASSES)

    found = _series(events, "jobs_found")
    assert found, "no jobs_found reported"
    assert _is_monotonic(found), f"jobs_found walked backwards: {found}"
    assert found[-1] == 9
    # Mid-scrape of pass 2 the scraper itself reports 1, but the run total must already be >3.
    assert max(found) == 9


def test_progress_jobs_saved_ticks_up_per_iteration(monkeypatch):
    """"Jobs Saved" updates after every iteration's storage step, not only at completion."""
    _, events = _run(monkeypatch, THREE_PASSES)

    saved = _series(events, "jobs_saved")
    assert _is_monotonic(saved), f"jobs_saved walked backwards: {saved}"
    assert saved[-1] == 9
    # Each pass' storage step reports its own running total — 3, then 6, then 9 all appear
    # before the run ends, which is what makes the counter live rather than end-loaded.
    assert {3, 6, 9} <= set(saved)


def test_fully_deduped_run_reports_real_found_not_zero(monkeypatch):
    """Every scraped job already in the DB → jobs_found is the raw total, jobs_saved 0."""
    prefill = [(f"Job{i}", "X") for i in range(12)]
    results, events = _run(monkeypatch, THREE_PASSES, prefill=prefill)

    assert results["success"] is True
    assert results["jobs_found"] == 9
    assert results["jobs_saved"] == 0
    terminal = [e for e in events if e.get("stage") == "completed"][-1]
    assert terminal["details"]["jobs_found"] == 9
    assert terminal["details"]["jobs_saved"] == 0
    assert _is_monotonic(_series(events, "jobs_found"))


def test_completion_totals_on_results_payload(monkeypatch):
    """Run totals land on the returned payload (scheduler/daily_runner logs these keys)."""
    results, events = _run(monkeypatch, THREE_PASSES)

    assert results["jobs_found"] == 9      # raw listings across all passes
    assert results["jobs_unique"] == 9     # after in-batch dedup
    assert results["jobs_saved"] == 9      # rows inserted
    assert results["jobs_added"] == 9
    assert results["jobs_kept"] == 9       # survived filtering

    terminal = [e for e in events if e.get("stage") == "completed"][-1]["details"]
    assert terminal["jobs_found"] == 9
    assert terminal["jobs_saved"] == 9
    assert terminal["jobs_kept"] == 9
    assert terminal["jobs_unique"] == 9


def test_single_iteration_counts_unchanged(monkeypatch):
    """A single pass reports the same figures it always did — no iterations rollup."""
    results, events = _run(monkeypatch, {
        "search_terms": ["ml"], "sites": ["indeed"], "results_wanted": 5,
    }, per_page=4)

    assert FakeScraper.offsets == [0]
    assert "iterations" not in results["steps"]
    assert results["steps"]["scraping"]["raw_jobs_count"] == 4
    assert results["steps"]["storage"]["stored_count"] == 4
    assert results["jobs_found"] == 4
    assert results["jobs_saved"] == 4
    assert _series(events, "jobs_saved")[-1] == 4


def test_overlapping_pages_count_saved_not_scraped(monkeypatch):
    """Overlapping pages: found counts every raw listing, saved counts only new rows."""
    # results_wanted=1 with 2 jobs/page → pages overlap by one, as in test_iterations.py.
    results, events = _run(monkeypatch, {
        "search_terms": ["ml"], "sites": ["indeed"],
        "results_wanted": 1, "max_iterations": 3,
    }, per_page=2)

    assert FakeScraper.offsets == [0, 1, 2]
    assert results["jobs_found"] == 6   # 3 passes × 2 raw listings
    assert results["jobs_saved"] == 4   # Job0..Job3 — overlaps dropped by the DB dedup
    assert _is_monotonic(_series(events, "jobs_saved"))
    assert _is_monotonic(_series(events, "jobs_found"))
