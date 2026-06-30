"""
Tests for the live scraping activity event log accumulated in scrape_routes.

The background runner appends a timestamped, deduplicated event for each distinct
progress message so the UI can render a step-by-step feed.
"""

import time

from utils.backend.routes import scrape_routes as sr


def test_events_accumulate_and_dedupe(monkeypatch):
    calls = [
        {"stage": "init", "percent": 5, "details": {"message": "Loading configuration..."}},
        {"stage": "scraping", "percent": 10, "details": {"message": "Searching 2 term(s)"}},
        {"stage": "scraping", "percent": 10, "details": {"message": "Searching 2 term(s)"}},  # dup
        {"stage": "scraping", "percent": 40, "details": {"message": "Scraping... (40% done)"}},
        {"stage": "completed", "percent": 100, "details": {"message": "Completed"}},
    ]

    def fake_workflow(search_terms=None, progress_callback=None, **kw):
        for c in calls:
            progress_callback(c)
        return {"success": True, "steps": {}, "errors": []}

    monkeypatch.setattr(sr, "execute_full_scraping_workflow", fake_workflow)

    jid = "scrape_test_events"
    sr.scrape_jobs[jid] = {
        "status": "pending",
        "progress": {"stage": "pending", "percent": 0, "details": {}},
        "events": [],
        "results": None,
        "start_time": time.time(),
    }
    try:
        sr.run_scraping_background(jid, True)
        events = sr.scrape_jobs[jid]["events"]
        msgs = [e["message"] for e in events]
        # The duplicate consecutive message is collapsed.
        assert msgs == [
            "Loading configuration...",
            "Searching 2 term(s)",
            "Scraping... (40% done)",
            "Completed",
        ]
        # Each event carries a relative timestamp + stage for the UI.
        assert all("t" in e and "stage" in e and "percent" in e for e in events)
        assert sr.scrape_jobs[jid]["status"] == "completed"
    finally:
        sr.scrape_jobs.pop(jid, None)


def test_events_capped(monkeypatch):
    def fake_workflow(search_terms=None, progress_callback=None, **kw):
        for i in range(260):
            progress_callback({"stage": "scraping", "percent": i, "details": {"message": f"step {i}"}})
        return {"success": True, "steps": {}, "errors": []}

    monkeypatch.setattr(sr, "execute_full_scraping_workflow", fake_workflow)

    jid = "scrape_test_cap"
    sr.scrape_jobs[jid] = {
        "status": "pending",
        "progress": {},
        "events": [],
        "results": None,
        "start_time": time.time(),
    }
    try:
        sr.run_scraping_background(jid, True)
        events = sr.scrape_jobs[jid]["events"]
        assert len(events) == 200  # capped
        assert events[-1]["message"] == "step 259"  # newest retained
    finally:
        sr.scrape_jobs.pop(jid, None)
