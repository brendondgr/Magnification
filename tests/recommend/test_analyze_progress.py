"""
Background analyze runner + status endpoints. Stubs analyze_jobs (so no DB/model/network is
touched) and drives the Flask blueprint through its test client, asserting the task store
streams progress events and the final results.
"""

import time

import pytest
from flask import Flask

from utils.backend.routes import recommend_routes as rr


@pytest.fixture()
def client(monkeypatch):
    # An active profile is required to start; stub it.
    monkeypatch.setattr(rr.db_ops, "get_active_profile", lambda: {"id": 1})
    app = Flask(__name__)
    app.register_blueprint(rr.recommend_bp)
    rr.analyze_tasks.clear()
    return app.test_client()


def _fake_analyze(emitted):
    """Return an analyze_jobs stub that emits a couple of staged progress updates."""
    def _impl(job_ids=None, llm_only_missing=True, progress_callback=None, **kw):
        emitted.append({"job_ids": job_ids, "llm_only_missing": llm_only_missing})
        if progress_callback:
            progress_callback({"stage": "embedding", "percent": 10,
                               "details": {"message": "Embedding 5 jobs…"}})
            progress_callback({"stage": "llm", "percent": 90,
                               "details": {"message": "LLM fit verdict on 2 of 5 job(s)…"}})
        return {"success": True, "analyzed": 5, "llm_analyzed": 2, "compensation_extracted": 1}
    return _impl


def _wait_completed(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rec = client.get(f"/api/recommend/analyze/status/{job_id}").get_json()
        if rec.get("status") in ("completed", "failed"):
            return rec
        time.sleep(0.02)
    raise AssertionError("analyze task did not finish in time")


def test_start_runs_background_and_streams_progress(client, monkeypatch):
    emitted = []
    monkeypatch.setattr(rr.service, "analyze_jobs", _fake_analyze(emitted))

    resp = client.post("/api/recommend/analyze/start", json={})
    body = resp.get_json()
    assert resp.status_code == 200 and body["success"] and body["job_id"].startswith("analyze_")

    rec = _wait_completed(client, body["job_id"])
    assert rec["status"] == "completed"
    assert rec["results"] == {"success": True, "analyzed": 5,
                              "llm_analyzed": 2, "compensation_extracted": 1}
    messages = [e["message"] for e in rec["events"]]
    assert "Embedding 5 jobs…" in messages
    assert any("LLM fit verdict on 2 of 5" in m for m in messages)
    # Default gap-fill: llm_only_missing stays True when reanalyze_all is absent.
    assert emitted[0]["llm_only_missing"] is True


def test_reanalyze_all_flag_forwarded(client, monkeypatch):
    emitted = []
    monkeypatch.setattr(rr.service, "analyze_jobs", _fake_analyze(emitted))
    body = client.post("/api/recommend/analyze/start", json={"reanalyze_all": True}).get_json()
    _wait_completed(client, body["job_id"])
    assert emitted[0]["llm_only_missing"] is False


def test_start_requires_active_profile(client, monkeypatch):
    monkeypatch.setattr(rr.db_ops, "get_active_profile", lambda: None)
    resp = client.post("/api/recommend/analyze/start", json={})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False


def test_status_unknown_job_is_404(client):
    resp = client.get("/api/recommend/analyze/status/analyze_missing")
    assert resp.status_code == 404


def test_background_failure_marks_failed(client, monkeypatch):
    def _boom(**kw):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(rr.service, "analyze_jobs", _boom)
    body = client.post("/api/recommend/analyze/start", json={}).get_json()
    rec = _wait_completed(client, body["job_id"])
    assert rec["status"] == "failed"
    assert "kaboom" in (rec.get("error") or "")
