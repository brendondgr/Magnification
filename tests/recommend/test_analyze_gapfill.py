"""
Gap-fill behavior for "Analyze Matches": the LLM fit verdict only fills jobs that don't
already have one, and missing compensation is recovered from the description. Fake clients,
no network / no real DB.
"""

from utils.backend.recommend import service


class FakeClient:
    """Returns a canned per-call list from chat_many (mirrors OpenAIClient.chat_many)."""

    def __init__(self, many_result=None):
        self._many = many_result or []

    def chat_many(self, message_lists, **kw):
        # Mirror one result per message so order/zip line up with the real client.
        return self._many[: len(message_lists)]


def _enable_llm(monkeypatch, many_result):
    monkeypatch.setattr(service, "load_llm_endpoint_config",
                        lambda: {"enabled": True, "base_url": "x"})
    monkeypatch.setattr(service.OpenAIClient, "from_config",
                        classmethod(lambda cls, cfg=None, **kw: FakeClient(many_result=many_result)))


# ---- LLM gap-fill selection ----

def test_gapfill_skips_jobs_with_existing_verdict(monkeypatch):
    """Default llm_only_missing=True: only jobs lacking llm_score are sent to the LLM."""
    _enable_llm(monkeypatch, [{"score": 90, "rationale": "new"}])
    jobs = [{"id": 1, "title": "A", "description": "a"},
            {"id": 2, "title": "B", "description": "b"}]
    # Job 1 already has a stored verdict (seeded onto the fresh analysis); job 2 does not.
    analyses = [{"job_id": 1, "llm_score": 55.0, "llm_rationale": "old"},
                {"job_id": 2}]
    new = service._llm_rerank(jobs, analyses, {"interests_paragraph": "x"},
                              {"llm_workers": 2}, llm_only_missing=True)
    assert new == 1                         # only the one missing verdict was issued
    assert analyses[0]["llm_score"] == 55.0  # existing verdict preserved untouched
    assert analyses[1]["llm_score"] == 90.0  # gap filled


def test_reanalyze_all_rescores_every_job(monkeypatch):
    """llm_only_missing=False re-scores jobs even when they already have a verdict."""
    _enable_llm(monkeypatch, [{"score": 10, "rationale": "r1"}, {"score": 20, "rationale": "r2"}])
    jobs = [{"id": 1, "title": "A", "description": "a"},
            {"id": 2, "title": "B", "description": "b"}]
    analyses = [{"job_id": 1, "llm_score": 55.0}, {"job_id": 2, "llm_score": 60.0}]
    new = service._llm_rerank(jobs, analyses, {"interests_paragraph": "x"},
                              {"llm_workers": 2}, llm_only_missing=False)
    assert new == 2
    assert analyses[0]["llm_score"] == 10.0
    assert analyses[1]["llm_score"] == 20.0


def test_gapfill_all_present_is_noop(monkeypatch):
    """When every job already has a verdict, no LLM call is made and count is 0."""
    _enable_llm(monkeypatch, [{"score": 99, "rationale": "unused"}])
    jobs = [{"id": 1, "title": "A", "description": "a"}]
    analyses = [{"job_id": 1, "llm_score": 42.0}]
    new = service._llm_rerank(jobs, analyses, {}, {}, llm_only_missing=True)
    assert new == 0
    assert analyses[0]["llm_score"] == 42.0


def test_llm_fraction_applies_to_full_set_not_just_gap(monkeypatch):
    """The fix: llm_fraction is a share of ALL jobs, not of the missing-verdict gap.

    Jobs 3 & 4 (top semantic+bm25) lack a verdict; jobs 1 & 2 (low relevance) already have one.
    llm_fraction=0.5 selects the top 2 of ALL four jobs (3 & 4), then gap-fills — so both are
    issued a verdict. (Pre-fix, the fraction hit the missing gap and would keep only 1.)
    """
    _enable_llm(monkeypatch, [{"score": 80, "rationale": "r"}, {"score": 81, "rationale": "r"}])
    jobs = [{"id": i, "title": f"J{i}", "description": "d"} for i in range(1, 5)]
    analyses = [
        {"job_id": 1, "semantic_score": 0.1, "bm25_score": 0.1, "llm_score": 50.0},
        {"job_id": 2, "semantic_score": 0.2, "bm25_score": 0.2, "llm_score": 51.0},
        {"job_id": 3, "semantic_score": 0.6, "bm25_score": 0.6},
        {"job_id": 4, "semantic_score": 0.9, "bm25_score": 0.9},
    ]
    new = service._llm_rerank(jobs, analyses, {"interests_paragraph": "x"},
                              {"llm_fraction": 0.5, "llm_workers": 2}, llm_only_missing=True)
    assert new == 2                                   # both top-half missing jobs filled
    assert analyses[0]["llm_score"] == 50.0           # low-relevance verdicts preserved
    assert analyses[1]["llm_score"] == 51.0
    assert analyses[2].get("llm_score") is not None   # jobs 3 & 4 (top 50%) gap-filled
    assert analyses[3].get("llm_score") is not None


def test_full_coverage_gapfills_only_missing(monkeypatch):
    """llm_fraction=1.0 covers every job but only spends calls on the ones missing a verdict."""
    _enable_llm(monkeypatch, [{"score": 88, "rationale": "r"}])
    jobs = [{"id": i, "title": f"J{i}", "description": "d"} for i in range(1, 4)]
    analyses = [
        {"job_id": 1, "semantic_score": 0.5, "bm25_score": 0.5, "llm_score": 40.0},
        {"job_id": 2, "semantic_score": 0.4, "bm25_score": 0.4, "llm_score": 41.0},
        {"job_id": 3, "semantic_score": 0.3, "bm25_score": 0.3},   # the only gap
    ]
    new = service._llm_rerank(jobs, analyses, {"interests_paragraph": "x"},
                              {"llm_fraction": 1.0, "llm_workers": 2}, llm_only_missing=True)
    assert new == 1                          # only the single missing verdict was issued
    assert analyses[0]["llm_score"] == 40.0  # existing verdicts untouched
    assert analyses[1]["llm_score"] == 41.0
    assert analyses[2]["llm_score"] == 88.0  # gap filled


def test_full_coverage_ignores_stale_top_n_cap(monkeypatch):
    """Regression: the retired top_n_llm no longer caps 100% coverage.

    Reproduces the reported bug — the top-relevance jobs already carry a verdict while the
    LOW-relevance jobs lack one. A leftover top_n_llm (=2) used to cap coverage to the top 2
    (already-verdicted) jobs, so the gap-fill filter found nothing and "Analyze Matches"
    reported everything already covered. With top_n_llm ignored, 100% coverage reaches the
    verdict-less low-relevance jobs and fills them.
    """
    _enable_llm(monkeypatch, [{"score": 30, "rationale": "r"}, {"score": 31, "rationale": "r"}])
    jobs = [{"id": i, "title": f"J{i}", "description": "d"} for i in range(1, 5)]
    analyses = [
        {"job_id": 1, "semantic_score": 0.9, "bm25_score": 0.9, "llm_score": 90.0},  # top, verdicted
        {"job_id": 2, "semantic_score": 0.8, "bm25_score": 0.8, "llm_score": 91.0},  # top, verdicted
        {"job_id": 3, "semantic_score": 0.2, "bm25_score": 0.2},                     # low, gap
        {"job_id": 4, "semantic_score": 0.1, "bm25_score": 0.1},                     # low, gap
    ]
    new = service._llm_rerank(jobs, analyses, {"interests_paragraph": "x"},
                              {"llm_fraction": 1.0, "top_n_llm": 2, "llm_workers": 2},
                              llm_only_missing=True)
    assert new == 2                                  # both low-relevance gaps filled despite top_n_llm=2
    assert analyses[2].get("llm_score") is not None
    assert analyses[3].get("llm_score") is not None
    assert analyses[0]["llm_score"] == 90.0          # existing verdicts preserved
    assert analyses[1]["llm_score"] == 91.0


# ---- compensation recovery ----

def test_recover_compensation_fills_and_persists(monkeypatch):
    _enable_llm(monkeypatch, [{"compensation": "$100,000 a year"}])
    calls = []
    monkeypatch.setattr(service.db_ops, "update_job",
                        lambda jid, updates: calls.append((jid, updates)) or True)
    jobs = [
        {"id": 1, "description": "We pay well.", "compensation": ""},       # needs recovery
        {"id": 2, "description": "Great team.", "compensation": "$50/hr"},   # already set
    ]
    n = service._recover_compensation(jobs, {"enable_llm_compensation": True, "llm_workers": 2})
    assert n == 1
    assert jobs[0]["compensation"] == "$100,000 a year"
    assert jobs[1]["compensation"] == "$50/hr"          # untouched
    assert calls == [(1, {"compensation": "$100,000 a year"})]


def test_recover_compensation_disabled_toggle_is_noop(monkeypatch):
    _enable_llm(monkeypatch, [{"compensation": "$1"}])
    calls = []
    monkeypatch.setattr(service.db_ops, "update_job",
                        lambda jid, updates: calls.append((jid, updates)) or True)
    jobs = [{"id": 1, "description": "We pay well.", "compensation": ""}]
    n = service._recover_compensation(jobs, {"enable_llm_compensation": False})
    assert n == 0
    assert jobs[0]["compensation"] == ""
    assert calls == []


def test_recover_compensation_endpoint_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(service, "load_llm_endpoint_config", lambda: {"enabled": False})
    calls = []
    monkeypatch.setattr(service.db_ops, "update_job",
                        lambda jid, updates: calls.append((jid, updates)) or True)
    jobs = [{"id": 1, "description": "We pay well.", "compensation": ""}]
    n = service._recover_compensation(jobs, {"enable_llm_compensation": True})
    assert n == 0
    assert calls == []
