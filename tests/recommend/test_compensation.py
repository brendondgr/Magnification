"""
Tests for the pure compensation layer (utils/backend/recommend/compensation.py).

Covers the malformed-value normalizer (the "USDnan - USDnan hourly" family) and the
"always extract from the description" candidate predicate. The combined compensation +
industry LLM pass is covered by tests/recommend/test_industry.py, and the shared DB-aware
orchestration by tests/recommend/test_enrichment.py.
"""

from utils.backend.recommend import compensation as comp


def test_clean_compensation_keeps_real_pay():
    assert comp.clean_compensation("  $50/hr ") == "$50/hr"
    assert comp.clean_compensation("$120,000 - $150,000 a year") == "$120,000 - $150,000 a year"
    assert comp.clean_compensation("£45/hour") == "£45/hour"


def test_clean_compensation_rejects_nan_and_placeholder_values():
    # The exact malformed strings the boards produced.
    assert comp.clean_compensation("USDnan - USDnan hourly") is None
    assert comp.clean_compensation("nannan - nannan nan") is None
    assert comp.clean_compensation("$nan - $nan yearly") is None
    # Placeholders and empties.
    for value in ("", "   ", "null", "None", "Not specified", "n/a", None):
        assert comp.clean_compensation(value) is None
    # No digits at all is not pay.
    assert comp.clean_compensation("competitive salary") is None


def test_clean_compensation_truncates():
    assert len(comp.clean_compensation("$1" + "0" * 400)) == 255


def test_has_compensation_uses_the_normalizer():
    assert comp.has_compensation({"compensation": "$90,000"})
    assert not comp.has_compensation({"compensation": "USDnan - USDnan hourly"})
    assert not comp.has_compensation({"compensation": ""})


def test_needs_compensation_ignores_malformed_values():
    assert comp.needs_compensation({"description": "pays well", "compensation": ""})
    assert comp.needs_compensation({"description": "x", "compensation": "Not specified"})
    # A nan string must not count as "has pay" — that is what blocked recovery.
    assert comp.needs_compensation({"description": "x", "compensation": "nannan - nannan nan"})
    assert not comp.needs_compensation({"description": "x", "compensation": "$100k"})
    assert not comp.needs_compensation({"description": "", "compensation": ""})  # no text


def test_recovery_always_runs_on_an_unchecked_description():
    # Compensation is extracted from the description no matter what the board reported.
    assert comp.needs_compensation_recovery({"description": "pays well", "compensation": ""})
    assert comp.needs_compensation_recovery({"description": "x", "compensation": "$100k"})
    assert comp.needs_compensation_recovery({"description": "x", "compensation": "USDnan hourly"})
    # No description -> nothing to extract from.
    assert not comp.needs_compensation_recovery({"description": "", "compensation": ""})


def test_recovery_respects_the_checked_flag():
    checked = {"description": "pays well", "compensation": "", "compensation_checked": True}
    assert not comp.needs_compensation_recovery(checked)
    assert comp.needs_compensation_recovery(checked, force=True)


def test_parse_comp_rejects_empty_sentinels():
    assert comp._parse_comp({"compensation": "null"}) is None
    assert comp._parse_comp({"compensation": "Not specified"}) is None
    assert comp._parse_comp({"compensation": "nan"}) is None
    assert comp._parse_comp(None) is None
    assert comp._parse_comp({"compensation": "  $50/hr "}) == "$50/hr"
