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


def test_index_has_documents_sidebar_wiring(client):
    """The served page wires the simplified Profile sidebar (Candidate | Guidance) + the editable
    Document Guidance handlers."""
    html = client.get("/").get_data(as_text=True)
    # Panel + the two remaining tabs.
    assert "Profile &amp; Documents" in html
    for token in ("setDocsCandidate", "setDocsGuidance", "docsTabCandidate", "docsTabGuidance"):
        assert token in html, f"missing sidebar token: {token}"
    # Guidance load/edit/save/reset handlers.
    for token in ("loadDocuments", "guidanceText", "onGuidanceText", "saveGuidance",
                  "resetGuidance"):
        assert token in html, f"missing handler token: {token}"
    # Visible labels for the new tab.
    assert "Document Guidance" in html
    assert "Reset to default" in html
    # The retired tabs are gone.
    for token in ("setDocsBehavioral", "setDocsWriting", "setDocsTemplates", "ingestDoc"):
        assert token not in html, f"retired token still present: {token}"


def test_index_has_thinking_budget_input(client):
    """The LLM Endpoint options tab wires the thinking-token-budget input (replaced the toggle)."""
    html = client.get("/").get_data(as_text=True)
    for token in ("llmThinkingBudget", "onLlmThinkingBudget", "thinking_token_budget"):
        assert token in html, f"missing thinking-budget token: {token}"
    assert "Thinking token budget" in html
    # The retired on/off toggle is gone.
    assert "toggleLlmThinking" not in html
    assert "Disable model thinking" not in html


def test_index_has_application_mode(client):
    """The served page wires Application Mode (Apply → intake / workspace / refine)."""
    html = client.get("/").get_data(as_text=True)
    for token in ("openApply", "startApply", "appOpen", "appCards", "submitRefine",
                  "approveAppDoc", "markAppliedAndClose", "onMarkApplied", "_pollApp"):
        assert token in html, f"missing Application Mode token: {token}"
    # Two buttons: Apply (opens the flow) + Applied (quick mark). Intake + review copy present.
    assert "Apply to " in html          # intake header
    assert "Tailor my résumé" in html
    assert "Regenerate" in html
    assert "Mark as Applied" in html
    # The old side-panel Documents surface must be gone.
    assert "docGenActive" not in html
    assert "docViewOpen" not in html


def test_index_has_per_page_search_and_saved_sort(client):
    """New Jobs and Saved each own an independent keyword search; Saved has a Newest/Match sort."""
    html = client.get("/").get_data(as_text=True)
    # Independent per-page search handlers + bindings.
    for token in ("searchNew", "onSearchNew", "searchSaved", "onSearchSaved", "keywordMatch"):
        assert token in html, f"missing search token: {token}"
    # Saved Newest/Match sort control.
    for token in ("toggleSavedSort", "savedSortLabel", "savedSortStyle", "savedSortByMatch"):
        assert token in html, f"missing Saved-sort token: {token}"
    # Both in-page inputs render.
    assert "Search jobs…" in html
    assert "Search saved…" in html
    # The retired global sidebar search must be gone (ignore the per-page handlers).
    assert "onSearch" not in (
        html.replace("onSearchNew", "").replace("onSearchSaved", "").replace("onSearchTracker", "")
    )
    assert "Title or company…" not in html
    assert "matchSearch" not in html


def test_index_has_tracker_search_and_rejected_column(client):
    """The Application Tracker owns a keyword search and a distinct Rejected column."""
    html = client.get("/").get_data(as_text=True)
    # Tracker search input + binding (reuses the shared keywordMatch matcher).
    for token in ("searchTracker", "onSearchTracker"):
        assert token in html, f"missing tracker-search token: {token}"
    assert "Search tracker…" in html
    # Rejected is its own kanban column with its own theme token.
    assert "{key:'rejected',label:'Rejected',c:'--c-reject'}" in html
    assert "'--c-reject'" in html
    # The final lane keeps its internal 'archived' key/token but is labelled "Ghosted".
    assert "{key:'archived',label:'Ghosted',c:'--c-archive'}" in html


def test_index_has_pipeline_history_and_slim_tracker_cards(client):
    """Tracker cards are slimmed to title+company and the detail panel shows durable
    pipeline dates."""
    html = client.get("/").get_data(as_text=True)
    # Durable pipeline-history surface + its view-model binding.
    assert "Pipeline History" in html
    assert "selectedJob.pipeline" in html
    # The pipeline view-model reads the durable, write-once date fields from the job.
    for field in (
        "date_found",
        "date_first_applied",
        "date_first_interview",
        "date_first_offer",
        "date_first_rejected",
        "date_first_ghosted",
    ):
        assert field in html, f"missing pipeline field binding: {field}"
    # The tracker card no longer renders the initials avatar (logo) — that token is gone;
    # the detail panel keeps its own larger avatar (avatarLg).
    assert "{{ job.avatar }}" not in html


def test_index_has_industry_and_row_based_job_card(client):
    """The redesigned job card exposes the industry pill, the renamed Generate action, and the
    icon action row (info · block · hide · save · link out)."""
    html = client.get("/").get_data(as_text=True)
    # Industry taxonomy -> color map (source of truth for the per-industry pill color) + the
    # view-model bindings the card renders.
    assert "static INDUSTRY_COLORS" in html
    for token in ("job.industryBadge", "job.industryLabel", "job.hasIndustry", "job.iconBtn"):
        assert token in html, f"missing industry/card token: {token}"
    # The industry field is carried through the job view-model from the API.
    assert "industry:j.industry" in html
    # Row 7: the primary action is now "Generate" (was "Apply"); the old text "Details" button
    # is gone (replaced by the Info icon button).
    assert "Generate" in html
    assert ">Details</button>" not in html
    # Row 8 icon buttons expose a custom hover tool-descriptor via data-tip (+ aria-label for a11y),
    # backed by a pure-CSS [data-tip] bubble that is pointer-events:none so the button stays clickable.
    for label in ("View job details", "Block this company", "Hide this job", "Open original posting"):
        assert f'data-tip="{label}"' in html, f"missing icon-button tooltip: {label}"
        assert f'aria-label="{label}"' in html, f"missing icon-button aria-label: {label}"
    assert "[data-tip]::after" in html and "pointer-events:none" in html
    # The detail panel gains an Industry line.
    assert "selectedJob.industryBadge" in html


def test_index_has_two_column_latex_workspace(client):
    """The workspace wires the two-column (process ‖ PDF) layout + LaTeX/PDF preview plumbing."""
    html = client.get("/").get_data(as_text=True)
    for token in ("appWorkspace", "appActive", "appTabButtons", "data-appws",
                  "loadPdf", "pdfRef", "Agent process", "PDF preview"):
        assert token in html, f"missing workspace token: {token}"
    # The raw template must NOT ship a bound resource `src` (it would fetch a literal {{…}} URL
    # pre-hydration); the iframe src is set via a ref instead.
    assert 'src="{{ appActive.pdfUrl }}"' not in html
    assert "Download PDF" in html
    # LaTeX source export (not just the rendered PDF).
    assert "Export .tex" in html
    assert "downloadAppTex" in html


def test_index_has_hash_view_routing(client):
    """The three top-level views are hash-routed (deep-link + Back/Forward)."""
    html = client.get("/").get_data(as_text=True)
    # Route table + the tab<->hash sync plumbing.
    for token in ("static ROUTES", "tabFromHash", "goTab", "hashchange", "_hashHandler"):
        assert token in html, f"missing routing token: {token}"
    # Each view maps to a stable hash path.
    for path in ("/new-jobs", "/saved", "/tracker"):
        assert path in html, f"missing route path: {path}"
    # Nav entry points route through goTab, not a bare setState.
    assert "onClick:()=>this.goTab(k)" in html


def test_generation_endpoints_registered(client):
    """The generation blueprint is mounted (status of an unknown task 404s, not 405/500)."""
    assert client.get("/api/documents/status/does_not_exist").status_code == 404
    assert client.post("/api/documents/cover-letter/start", json={}).status_code == 400


def test_document_guidance_endpoint_served(client):
    """The guidance blueprint is registered and returns the editable house-style document."""
    body = client.get("/api/document-guidance").get_json()
    assert body["success"] is True
    assert isinstance(body["guidance"], str) and body["guidance"].strip()
    assert "is_default" in body
    # The retired subsystems' routes are gone.
    assert client.get("/api/templates").status_code == 404
    assert client.get("/api/behavioral-profile").status_code == 404


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
