"""
Verify LinkedIn description fetching runs in parallel and populates every targeted job.
No network: fetch_linkedin_description is monkeypatched with an instrumented stub that
records the peak number of concurrently-active fetches.
"""

import threading
import time

from utils.backend.scrapers import linkedin_scraper


def test_fetch_descriptions_is_parallel_and_complete(monkeypatch):
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_fetch(job_id):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)  # hold the slot so concurrency is observable
        with lock:
            active -= 1
        return f"description for {job_id}"

    monkeypatch.setattr(linkedin_scraper, "fetch_linkedin_description", fake_fetch)

    jobs = [
        {"site": "linkedin", "link": f"https://www.linkedin.com/jobs/view/{1000 + i}", "description": ""}
        for i in range(6)
    ]
    # Non-LinkedIn / already-described jobs must be left untouched.
    jobs.append({"site": "indeed", "link": "x", "description": ""})
    jobs.append({"site": "linkedin", "link": "https://www.linkedin.com/jobs/view/2000", "description": "already"})

    out = linkedin_scraper.fetch_descriptions_for_jobs(jobs, max_workers=4, delay=0)

    # All six empty LinkedIn jobs got descriptions.
    filled = [j for j in out if j["site"] == "linkedin" and j["description"].startswith("description for")]
    assert len(filled) == 6
    # The indeed job and the pre-described one are unchanged.
    assert out[6]["description"] == ""
    assert out[7]["description"] == "already"
    # Genuinely concurrent (more than one fetch active at once).
    assert peak >= 2


def test_progress_callback_reports_completion(monkeypatch):
    monkeypatch.setattr(linkedin_scraper, "fetch_linkedin_description", lambda jid: "desc")
    seen = []
    jobs = [{"site": "linkedin", "link": f"https://www.linkedin.com/jobs/view/{i}", "description": ""}
            for i in range(3)]
    linkedin_scraper.fetch_descriptions_for_jobs(
        jobs, progress_callback=lambda c, t: seen.append((c, t)), max_workers=2, delay=0
    )
    assert seen[-1] == (3, 3)
    assert sorted(c for c, _ in seen) == [1, 2, 3]
