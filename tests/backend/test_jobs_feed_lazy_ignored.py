"""The jobs feed must not ship ignored jobs until they are asked for.

With a large company/title blocklist, ignored rows outnumber the visible feed by
orders of magnitude, so `/api/jobs` withholds them by default. The exceptions are
ignored jobs that are *saved* or *applied to* — the Saved lane and the Tracker board
still render those, and a card must not vanish because its company was blocked after
the fact.
"""

import pytest

from app import application
from utils.backend.database import operations as db_ops


@pytest.fixture
def client():
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


def _make_job(title):
    return db_ops.add_job({
        "title": title,
        "company": "Lazy Ignored Test Co",
        "location": "Remote",
        "link": f"https://example.com/{title}",
        "description": "Test role.",
        "site": "indeed",
    })


@pytest.fixture
def jobs():
    """plain / ignored / ignored+saved / ignored+applied, cleaned up afterwards."""
    ids = {k: _make_job(f"Lazy Ignored {k}") for k in
           ("plain", "ignored", "ignored_saved", "ignored_applied")}
    db_ops.update_application_status(ids["ignored_applied"], "Applied", 1, "2026-07-01")
    db_ops.set_job_saved(ids["ignored_saved"], 1)
    for k in ("ignored", "ignored_saved", "ignored_applied"):
        db_ops.set_job_ignore(ids[k], 1)
    try:
        yield ids
    finally:
        for job_id in ids.values():
            db_ops.delete_job(job_id)


def _ids(resp):
    assert resp.status_code == 200
    return {j["id"] for j in resp.get_json()}


def test_default_feed_withholds_plain_ignored_jobs(client, jobs):
    served = _ids(client.get("/api/jobs"))
    assert jobs["plain"] in served
    assert jobs["ignored"] not in served


def test_default_feed_keeps_saved_and_applied_ignored_jobs(client, jobs):
    """Ignoring a job the user saved or applied to must not remove it from the UI."""
    served = _ids(client.get("/api/jobs"))
    assert jobs["ignored_saved"] in served
    assert jobs["ignored_applied"] in served


def test_include_ignored_returns_everything(client, jobs):
    served = _ids(client.get("/api/jobs?include_ignored=1"))
    assert set(jobs.values()) <= served


def test_statuses_are_hydrated_on_the_lean_payload(client, jobs):
    """Batching the status lookup must not change the per-job shape."""
    job = next(j for j in client.get("/api/jobs").get_json() if j["id"] == jobs["plain"])
    assert len(job["statuses"]) == 9
    applied = next(j for j in client.get("/api/jobs").get_json()
                   if j["id"] == jobs["ignored_applied"])
    assert next(s for s in applied["statuses"] if s["status"] == "Applied")["checked"] == 1


def test_counts_endpoint_reports_the_withheld_rows(client, jobs):
    counts = client.get("/api/jobs/counts").get_json()
    assert counts["total"] == counts["feed"] + counts["hidden"]
    assert counts["feed"] == len(client.get("/api/jobs").get_json())
    assert counts["total"] == len(client.get("/api/jobs?include_ignored=1").get_json())
    assert counts["hidden"] >= 1  # at least the plain ignored fixture job


def test_counts_route_does_not_shadow_the_single_job_route(client, jobs):
    """/api/jobs/counts must resolve to the counts view, not /api/jobs/<int:job_id>."""
    assert set(client.get("/api/jobs/counts").get_json()) == {"total", "feed", "hidden"}
    assert client.get(f"/api/jobs/{jobs['plain']}").get_json()["id"] == jobs["plain"]


def test_frontend_lazy_loads_ignored_once(client):
    """The page must fetch the lean feed first and pull ignored rows only on toggle."""
    html = client.get("/").get_data(as_text=True)
    assert "include_ignored='+inc" in html          # loadJobs() is inclusive-aware
    assert "loadIgnoredJobs" in html                # on-demand pull exists
    assert "ignoredLoaded" in html                  # cached in RAM for the session
    assert "/api/jobs/counts" in html               # label without downloading rows
