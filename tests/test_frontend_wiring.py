"""
End-to-end wiring tests for the redesigned Job Finder frontend.

These exercise the contract the dc-runtime Component relies on:
  * the index page is the dc-runtime design shell
  * the runtime is served as a same-origin static asset
  * the job + config + database API endpoints return the shapes the
    Component maps into its view model

The tests are self-contained: the job-API test creates a throwaway job and
deletes it afterwards, and the config test backs up / restores any existing
user config so it never destroys real data.
"""

import os
import json
import shutil

import pytest

from app import application
from utils.backend.database import operations as db_ops
from utils.backend.routes.config_routes import CONFIG_PATH


@pytest.fixture
def client():
    application.config["TESTING"] = True
    with application.test_client() as c:
        yield c


def test_index_serves_dc_runtime_page(client):
    """`/` must serve the dc-runtime design shell, not the legacy template."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<x-dc>" in html
    assert "data-dc-script" in html
    assert "/static/js/dc-runtime.js" in html
    assert "class Component extends DCLogic" in html


def test_dc_runtime_asset_served(client):
    """The vendored runtime must be reachable where the page references it."""
    resp = client.get("/static/js/dc-runtime.js")
    assert resp.status_code == 200
    assert b"dc-runtime" in resp.get_data()


def test_jobs_api_shape_and_status_roundtrip(client):
    """`/api/jobs` returns hydrated jobs; ignore + status PATCH persist."""
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)

    job_id = db_ops.add_job({
        "title": "Wiring Test Engineer",
        "company": "Acme",
        "location": "Remote",
        "link": "https://example.com/job",
        "description": "Test role.",
        "compensation": "$1 - $2",
        "site": "indeed",
    })
    try:
        single = client.get(f"/api/jobs/{job_id}").get_json()
        assert single["title"] == "Wiring Test Engineer"
        # Nine application statuses hydrate the timeline.
        assert len(single["statuses"]) == 9
        assert {s["status"] for s in single["statuses"]} >= {"Applied", "Offer"}

        # Ignore toggle persists.
        assert client.patch(
            f"/api/jobs/{job_id}/ignore", json={"ignore": 1}
        ).get_json()["success"] is True
        assert client.get(f"/api/jobs/{job_id}").get_json()["ignore"] == 1

        # Status toggle persists.
        assert client.patch(
            f"/api/jobs/{job_id}/status",
            json={"status": "Applied", "checked": 1, "date_reached": "2026-06-30"},
        ).get_json()["success"] is True
        applied = next(
            s for s in client.get(f"/api/jobs/{job_id}").get_json()["statuses"]
            if s["status"] == "Applied"
        )
        assert applied["checked"] == 1
    finally:
        db_ops.delete_job(job_id)


def test_config_save_creates_dir_and_roundtrips(client):
    """Config save must create its dir on first run and load must round-trip."""
    backup = None
    if os.path.exists(CONFIG_PATH):
        backup = CONFIG_PATH + ".bak"
        shutil.copy2(CONFIG_PATH, backup)
    try:
        payload = {
            "search_terms": ["python developer"],
            "job_titles": [],
            "description_keywords": [["react", "typescript"]],
            "sites": ["indeed", "linkedin"],
            "hours_old": 72,
            "results_wanted": 10,
            "location": "Remote",
            "use_llm": False,
        }
        save = client.post("/api/config/save", json=payload)
        assert save.status_code == 200
        assert save.get_json()["success"] is True
        assert os.path.exists(CONFIG_PATH)

        loaded = client.get("/api/config/load").get_json()
        assert loaded["search_terms"] == ["python developer"]
        assert loaded["sites"] == ["indeed", "linkedin"]
        assert loaded["hours_old"] == 72
    finally:
        if backup:
            shutil.move(backup, CONFIG_PATH)
