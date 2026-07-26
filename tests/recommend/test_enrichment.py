"""
Tests for the shared description-enrichment pass (utils/backend/recommend/enrichment.py).

This is the one implementation both "Find Jobs" and "Analyze Matches" use, so the tests cover
(a) the extraction/persistence behavior itself and (b) parity — that both workflows really do
route through ``enrich_jobs`` rather than re-implementing it. Fake client, no network, no
real database (``update_job`` is captured).
"""

import pytest

from utils.backend.recommend import enrichment
from utils.backend.recommend import service as recommend_service
from utils.backend.scrapers import scraping_service


class FakeClient:
    """Returns a canned per-call list from chat_many (mirrors OpenAIClient.chat_many)."""

    def __init__(self, many_result=None):
        self._many = many_result or []
        self.batches = []

    def chat_many(self, message_lists, **kw):
        self.batches.append(len(message_lists))
        return self._many[: len(message_lists)]


@pytest.fixture()
def captured(monkeypatch):
    """Capture update_job writes instead of touching the shared database."""
    calls = []
    monkeypatch.setattr(enrichment.db_ops, "update_job",
                        lambda jid, updates: calls.append((jid, updates)) or True)
    return calls


def _enable_llm(monkeypatch, many_result):
    client = FakeClient(many_result=many_result)
    monkeypatch.setattr(enrichment, "load_llm_endpoint_config",
                        lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(enrichment.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg=None, **kw: client))
    return client


BOTH_ON = {"enable_llm_compensation": True, "enable_llm_industry": True, "llm_workers": 2}


# ---- extraction + persistence ----

def test_fills_pay_and_industry_in_one_pass(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": "$120k a year", "industry": "healthcare"}])
    jobs = [{"id": 3, "description": "Hospital software, we pay well.",
             "compensation": "", "industry": ""}]

    result = enrichment.enrich_jobs(jobs, BOTH_ON)

    assert result == {"candidates": 1, "compensation": 1, "industry": 1}
    assert jobs[0]["compensation"] == "$120k a year"
    assert jobs[0]["industry"] == "Health"               # synonym normalized
    assert captured == [(3, {"compensation_checked": 1, "compensation": "$120k a year",
                             "industry": "Health", "industry_checked": 1})]


def test_description_pay_overrides_a_board_value(monkeypatch, captured):
    """The description is the authority — a job that already shows pay is still extracted."""
    _enable_llm(monkeypatch, [{"compensation": "$65/hour", "industry": "Tech"}])
    jobs = [{"id": 5, "description": "The posted rate is $65/hour.",
             "compensation": "USDnan - USDnan hourly", "industry": ""}]

    result = enrichment.enrich_jobs(jobs, BOTH_ON)

    assert result["candidates"] == 1 and result["compensation"] == 1
    assert captured[0][1]["compensation"] == "$65/hour"


def test_board_value_kept_when_the_description_states_no_pay(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": None, "industry": "finance"}])
    jobs = [{"id": 6, "description": "No salary listed.", "compensation": "$80k", "industry": ""}]

    result = enrichment.enrich_jobs(jobs, BOTH_ON)

    assert result["compensation"] == 0
    assert jobs[0]["compensation"] == "$80k"             # untouched
    # Flagged checked so this job is asked once, not once per run — but no value rewritten.
    assert captured == [(6, {"compensation_checked": 1,
                             "industry": "Finance", "industry_checked": 1})]


def test_checked_flag_stops_a_second_query(monkeypatch, captured):
    client = _enable_llm(monkeypatch, [{"compensation": None, "industry": "Tech"}])
    jobs = [{"id": 7, "description": "No salary listed here.", "compensation": "",
             "compensation_checked": 1, "industry": "Tech", "industry_checked": 1}]

    assert enrichment.enrich_jobs(jobs, BOTH_ON)["candidates"] == 0
    assert client.batches == []                          # the LLM was never called
    assert captured == []


def test_force_reattempts_a_checked_job(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": "$90k", "industry": "Tech"}])
    jobs = [{"id": 9, "description": "We pay well.", "compensation": "",
             "compensation_checked": 1, "industry": "Tech", "industry_checked": 1}]

    result = enrichment.enrich_jobs(jobs, BOTH_ON, force=True)

    assert result["compensation"] == 1
    assert captured[0][1]["compensation"] == "$90k"


def test_failed_industry_response_is_not_flagged_checked(monkeypatch, captured):
    """An empty/failed classification must retry next run, not poison the job forever."""
    _enable_llm(monkeypatch, [{"compensation": "$70k", "industry": None}])
    jobs = [{"id": 11, "description": "Some role.", "compensation": "", "industry": ""}]

    result = enrichment.enrich_jobs(jobs, BOTH_ON)

    assert result["industry"] == 0
    updates = captured[0][1]
    assert "industry_checked" not in updates and "industry" not in updates
    assert updates["compensation_checked"] == 1          # pay *is* settled either way


def test_industry_only_when_compensation_disabled(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": "$1", "industry": "finance"}])
    jobs = [{"id": 4, "description": "A bank.", "compensation": "$80k", "industry": ""}]

    result = enrichment.enrich_jobs(
        jobs, {"enable_llm_compensation": False, "enable_llm_industry": True, "llm_workers": 2})

    assert (result["compensation"], result["industry"]) == (0, 1)
    assert jobs[0]["compensation"] == "$80k"             # comp off -> untouched
    assert captured == [(4, {"industry": "Finance", "industry_checked": 1})]


def test_jobs_without_a_description_are_never_queried(monkeypatch, captured):
    client = _enable_llm(monkeypatch, [{"compensation": "$1", "industry": "Tech"}])
    jobs = [{"id": 12, "description": "", "compensation": "", "industry": ""}]

    assert enrichment.enrich_jobs(jobs, BOTH_ON)["candidates"] == 0
    assert client.batches == []
    assert captured == []


def test_both_toggles_off_is_a_noop(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": "$1"}])
    jobs = [{"id": 1, "description": "We pay well.", "compensation": "", "industry": ""}]

    result = enrichment.enrich_jobs(
        jobs, {"enable_llm_compensation": False, "enable_llm_industry": False})

    assert result == {"candidates": 0, "compensation": 0, "industry": 0}
    assert captured == []


def test_disabled_endpoint_is_a_noop(monkeypatch, captured):
    monkeypatch.setattr(enrichment, "load_llm_endpoint_config", lambda: {"enabled": False})
    jobs = [{"id": 1, "description": "We pay well.", "compensation": "", "industry": ""}]

    assert enrichment.enrich_jobs(jobs, BOTH_ON) == {"candidates": 0, "compensation": 0, "industry": 0}
    assert captured == []


def test_llm_failure_is_non_fatal(monkeypatch, captured):
    monkeypatch.setattr(enrichment, "load_llm_endpoint_config", lambda: {"enabled": True})

    class Boom:
        def chat_many(self, *a, **kw):
            raise RuntimeError("endpoint down")

    monkeypatch.setattr(enrichment.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg=None, **kw: Boom()))
    jobs = [{"id": 1, "description": "We pay well.", "compensation": "", "industry": ""}]

    assert enrichment.enrich_jobs(jobs, BOTH_ON) == {"candidates": 0, "compensation": 0, "industry": 0}
    assert captured == []                                # nothing flagged checked on failure


def test_progress_messages_are_reported(monkeypatch, captured):
    _enable_llm(monkeypatch, [{"compensation": "$1/hr", "industry": "Tech"}])
    seen = []
    jobs = [{"id": 1, "description": "Pays $1/hr.", "compensation": "", "industry": ""}]

    enrichment.enrich_jobs(jobs, BOTH_ON, on_progress=seen.append)

    assert any("1 description(s)" in m for m in seen)
    assert any("Recovered pay for 1" in m for m in seen)


# ---- parity: both workflows share this one implementation ----

def test_analyze_matches_and_find_jobs_both_call_enrich_jobs(monkeypatch):
    """Neither workflow may re-implement enrichment — both must land in enrich_jobs()."""
    assert recommend_service.enrich_jobs is enrichment.enrich_jobs

    # The scrape workflow imports it lazily inside step 7a; assert on the source instead so a
    # re-implementation there is caught.
    import inspect
    source = inspect.getsource(scraping_service.execute_full_scraping_workflow)
    assert "from ..recommend.enrichment import enrich_jobs" in source
    assert "enrich_jobs(" in source
    # ...and does not reach for the lower-level extractor directly.
    assert "extract_enrichment_llm" not in source
