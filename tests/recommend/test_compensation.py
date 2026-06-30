"""
Tests for LLM compensation extraction (utils/backend/recommend/compensation.py).

Uses a fake client (no network) whose chat_many returns canned per-job JSON so we can
assert that pay is filled only for jobs that need it and only when the model reports a value.
"""

from utils.backend.recommend import compensation as comp


class FakeClient:
    """Returns queued results in order from chat_many (mirrors OpenAIClient.chat_many)."""

    def __init__(self, results):
        self._results = results
        self.calls = 0

    def chat_many(self, message_lists, max_workers=4, as_json=False, **kw):
        self.calls += 1
        assert len(message_lists) == len(self._results)
        return list(self._results)


def test_needs_compensation():
    assert comp.needs_compensation({"description": "pays well", "compensation": ""})
    assert comp.needs_compensation({"description": "x", "compensation": "Not specified"})
    assert not comp.needs_compensation({"description": "x", "compensation": "$100k"})
    assert not comp.needs_compensation({"description": "", "compensation": ""})  # no text


def test_extract_fills_only_missing():
    jobs = [
        {"title": "A", "description": "We pay $120k-$150k.", "compensation": "Not specified"},
        {"title": "B", "description": "Great culture, no pay listed.", "compensation": ""},
        {"title": "C", "description": "irrelevant", "compensation": "$90,000"},  # already has pay -> skipped
    ]
    # Only A and B are candidates (order preserved); C is not sent.
    fake = FakeClient([
        {"compensation": "$120,000 - $150,000 a year"},  # A
        {"compensation": None},                            # B -> nothing stated
    ])
    updated = comp.extract_compensation_llm(jobs, fake, max_workers=2)
    assert updated == 1
    assert jobs[0]["compensation"] == "$120,000 - $150,000 a year"
    assert jobs[1]["compensation"] == ""          # untouched (model said null)
    assert jobs[2]["compensation"] == "$90,000"   # untouched (was not a candidate)


def test_extract_no_candidates_skips_client():
    jobs = [{"title": "A", "description": "x", "compensation": "$1/yr"}]
    fake = FakeClient([])  # would assert-fail if called with mismatched length
    assert comp.extract_compensation_llm(jobs, fake) == 0
    assert fake.calls == 0


def test_parse_comp_rejects_empty_sentinels():
    assert comp._parse_comp({"compensation": "null"}) is None
    assert comp._parse_comp({"compensation": "Not specified"}) is None
    assert comp._parse_comp(None) is None
    assert comp._parse_comp({"compensation": "  $50/hr "}) == "$50/hr"
