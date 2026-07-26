"""
Tests for LLM industry classification + the combined compensation/industry enrichment pass
(utils/backend/recommend/compensation.py).

Uses a fake client (no network) whose chat_many returns canned per-job JSON so we can assert
that both fields are pulled in a single pass and that each is gated independently.
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


def test_normalize_industry_maps_synonyms_and_unknowns():
    assert comp.normalize_industry("Health") == "Health"
    assert comp.normalize_industry("healthcare") == "Health"      # synonym
    assert comp.normalize_industry("TECHNOLOGY") == "Tech"        # synonym, case-insensitive
    assert comp.normalize_industry("oil and gas") == "Energy"     # multi-word synonym
    assert comp.normalize_industry("underwater basket weaving") == "Other"  # unknown -> Other
    assert comp.normalize_industry("") is None                    # empty -> None
    assert comp.normalize_industry("null") is None
    assert comp.normalize_industry(None) is None
    assert comp.normalize_industry({"industry": "finance"}) == "Finance"  # accepts raw dict


def test_needs_industry_and_recovery_flag():
    assert comp.needs_industry({"description": "x", "industry": ""})
    assert comp.needs_industry({"description": "x", "industry": "Not specified"})
    assert not comp.needs_industry({"description": "x", "industry": "Tech"})
    assert not comp.needs_industry({"description": "", "industry": ""})  # no text
    # Not yet checked -> recover; checked -> skip; force overrides.
    assert comp.needs_industry_recovery({"description": "x", "industry": ""})
    assert not comp.needs_industry_recovery(
        {"description": "x", "industry": "", "industry_checked": True})
    assert comp.needs_industry_recovery(
        {"description": "x", "industry": "", "industry_checked": True}, force=True)


def test_needs_enrichment_composes_both_fields():
    # An unchecked description is a candidate for either field: compensation is always
    # re-derived from the description text, and the industry is still missing.
    j = {"description": "x", "compensation": "$100k", "industry": ""}
    assert comp.needs_enrichment(j)
    assert comp.needs_enrichment(j, industry_on=False)       # comp alone still qualifies it
    assert comp.needs_enrichment(j, comp_on=False)           # industry alone still qualifies it
    # Both fields already settled -> no call.
    done = {"description": "x", "compensation": "$1", "industry": "Tech",
            "compensation_checked": 1, "industry_checked": 1}
    assert not comp.needs_enrichment(done)
    # Only the disabled field is outstanding -> no call.
    comp_only = {"description": "x", "compensation": "$1", "industry": "Tech",
                 "compensation_checked": 0, "industry_checked": 1}
    assert not comp.needs_enrichment(comp_only, comp_on=False)
    assert comp.needs_enrichment(comp_only, industry_on=False)
    # No description text -> nothing to extract from, whatever is enabled.
    assert not comp.needs_enrichment({"description": "", "compensation": "", "industry": ""})


def test_extract_enrichment_fills_both_in_one_pass():
    jobs = [
        {"title": "A", "description": "We pay $120k. A hospital role.",
         "compensation": "", "industry": ""},
        {"title": "B", "description": "No pay listed, software team.",
         "compensation": "", "industry": ""},
    ]
    fake = FakeClient([
        {"compensation": "$120,000 a year", "industry": "healthcare"},  # A -> both
        {"compensation": None, "industry": "software"},                 # B -> industry only
    ])
    comp_n, ind_n = comp.extract_enrichment_llm(jobs, fake, max_workers=2)
    assert fake.calls == 1                       # single pass
    assert (comp_n, ind_n) == (1, 2)
    assert jobs[0]["compensation"] == "$120,000 a year"
    assert jobs[0]["industry"] == "Health"       # synonym normalized
    assert jobs[1]["compensation"] == ""         # model said null -> untouched
    assert jobs[1]["industry"] == "Tech"


def test_extract_enrichment_respects_field_flags():
    jobs = [{"title": "A", "description": "x", "compensation": "", "industry": ""}]
    fake = FakeClient([{"compensation": "$5/hr", "industry": "finance"}])
    # industry disabled -> only compensation written.
    comp_n, ind_n = comp.extract_enrichment_llm(jobs, fake, industry=False)
    assert (comp_n, ind_n) == (1, 0)
    assert jobs[0]["compensation"] == "$5/hr"
    assert jobs[0]["industry"] == ""             # untouched


def test_extract_enrichment_no_jobs_skips_client():
    fake = FakeClient([])
    assert comp.extract_enrichment_llm([], fake) == (0, 0)
    assert fake.calls == 0
