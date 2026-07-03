"""Unit tests for the once-per-day, LLM-gated runner (offline; scrape mocked)."""

import json
from datetime import date

import utils.backend.scrapers.scraping_service as scraping_service
from utils.backend.scheduler import daily_runner

TODAY = date(2026, 7, 3)


def _state(tmp_path):
    return tmp_path / "daily_search_state.json"


def _ok_result(**over):
    base = {"success": True, "jobs_found": 3, "jobs_kept": 2, "jobs_added": 2, "errors": []}
    base.update(over)
    return base


def test_check_only_ready(tmp_path):
    rc = daily_runner.run_daily_search(
        check_only=True, check_llm=lambda: True, state_path=_state(tmp_path)
    )
    assert rc == 0


def test_check_only_not_ready(tmp_path):
    rc = daily_runner.run_daily_search(
        check_only=True, check_llm=lambda: False, state_path=_state(tmp_path)
    )
    assert rc == 1


def test_runs_and_stamps_when_llm_ready(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_workflow(**kwargs):
        calls["n"] += 1
        assert kwargs.get("save_to_database") is True
        return _ok_result()

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", fake_workflow)
    sp = _state(tmp_path)
    rc = daily_runner.run_daily_search(
        check_llm=lambda: True, today=TODAY, state_path=sp, sleep_fn=lambda s: None
    )
    assert rc == 0
    assert calls["n"] == 1
    assert daily_runner.already_ran_today(TODAY, sp) is True
    data = json.loads(sp.read_text())
    assert data["last_status"] == "success"
    assert data["attempts"] == 1


def test_skips_when_already_ran_today(tmp_path, monkeypatch):
    sp = _state(tmp_path)
    daily_runner.mark_ran_today(TODAY, sp, "success", 1)

    def boom(**kwargs):
        raise AssertionError("scrape must not run when the day is already handled")

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", boom)
    rc = daily_runner.run_daily_search(check_llm=lambda: True, today=TODAY, state_path=sp)
    assert rc == 0


def test_force_reruns_even_if_already_ran(tmp_path, monkeypatch):
    sp = _state(tmp_path)
    daily_runner.mark_ran_today(TODAY, sp, "success", 1)
    calls = {"n": 0}

    def fake_workflow(**kwargs):
        calls["n"] += 1
        return _ok_result()

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", fake_workflow)
    rc = daily_runner.run_daily_search(
        force=True, check_llm=lambda: True, today=TODAY, state_path=sp, sleep_fn=lambda s: None
    )
    assert rc == 0
    assert calls["n"] == 1


def test_retries_every_interval_then_gives_up(tmp_path, monkeypatch):
    checks = {"n": 0}

    def never_ready():
        checks["n"] += 1
        return False

    def boom(**kwargs):
        raise AssertionError("scrape must not run when the LLM never comes up")

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", boom)
    slept = []
    sp = _state(tmp_path)
    rc = daily_runner.run_daily_search(
        check_llm=never_ready,
        today=TODAY,
        state_path=sp,
        max_attempts=6,
        interval_seconds=600,
        sleep_fn=lambda s: slept.append(s),
    )
    assert rc == 0
    assert checks["n"] == 6  # exactly 6 attempts
    assert slept == [600] * 5  # sleeps between attempts, not after the last
    assert daily_runner.already_ran_today(TODAY, sp) is True
    assert json.loads(sp.read_text())["last_status"] == "llm_unavailable"


def test_retries_then_succeeds_on_third_attempt(tmp_path, monkeypatch):
    seq = iter([False, False, True])

    def check():
        return next(seq)

    def fake_workflow(**kwargs):
        return _ok_result(jobs_found=0, jobs_kept=0, jobs_added=0)

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", fake_workflow)
    slept = []
    sp = _state(tmp_path)
    rc = daily_runner.run_daily_search(
        check_llm=check, today=TODAY, state_path=sp, sleep_fn=lambda s: slept.append(s)
    )
    assert rc == 0
    assert slept == [600, 600]  # slept after attempts 1 and 2, ran on attempt 3
    assert json.loads(sp.read_text())["attempts"] == 3


def test_scrape_failure_returns_nonzero_and_stamps(tmp_path, monkeypatch):
    def fake_workflow(**kwargs):
        return {"success": False, "errors": ["boom"], "jobs_found": 0}

    monkeypatch.setattr(scraping_service, "execute_full_scraping_workflow", fake_workflow)
    sp = _state(tmp_path)
    rc = daily_runner.run_daily_search(
        check_llm=lambda: True, today=TODAY, state_path=sp, sleep_fn=lambda s: None
    )
    assert rc == 1
    # The day is still marked consumed so it does not hammer the boards.
    assert daily_runner.already_ran_today(TODAY, sp) is True
    assert json.loads(sp.read_text())["last_status"] == "scrape_failed"
