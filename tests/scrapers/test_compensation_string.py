"""
Tests for the jobspy salary formatter (utils/backend/scrapers/jobspy_wrapper.py).

Regression coverage for the "USDnan - USDnan hourly" / "nannan - nannan nan" values Indeed
listings produced: jobspy hands back pandas NaN amounts, and float('nan') is truthy, so the
old formatter stringified them instead of treating the job as having no reported pay.
"""

import math

from utils.backend.scrapers.data_processor import clean_job_data
from utils.backend.scrapers.jobspy_wrapper import build_compensation_string, normalize_job_data

NAN = float("nan")


def test_real_range_formats():
    assert build_compensation_string(120000, 150000, "$", "yearly") == "$120,000 - $150,000 yearly"


def test_single_bound_formats():
    assert build_compensation_string(45, None, "$", "hourly") == "$45 hourly"
    assert build_compensation_string(None, 90000, "$", "") == "$90,000"


def test_nan_amounts_yield_no_string():
    # The exact shapes seen in the database.
    assert build_compensation_string(NAN, NAN, "USD", "hourly") is None
    assert build_compensation_string(NAN, NAN, NAN, NAN) is None
    assert build_compensation_string(None, None, "$", "yearly") is None


def test_nan_currency_and_interval_are_dropped_not_stringified():
    assert build_compensation_string(50000, 70000, NAN, NAN) == "50,000 - 70,000"


def test_non_numeric_and_nonpositive_amounts_ignored():
    assert build_compensation_string("abc", None, "$", "") is None
    assert build_compensation_string(0, 0, "$", "yearly") is None
    assert build_compensation_string(math.inf, None, "$", "") is None


def test_normalize_job_data_leaves_nan_pay_empty():
    job = normalize_job_data({
        "title": "Nurse", "company": "Acme", "min_amount": NAN, "max_amount": NAN,
        "currency": "USD", "interval": "hourly",
    })
    assert job["compensation"] is None


def test_clean_job_data_drops_a_nan_poisoned_board_string():
    # Some rows arrive with the malformed string already built upstream.
    cleaned = clean_job_data({
        "title": "Nurse", "company": "Acme", "location": "Remote",
        "compensation": "USDnan - USDnan hourly",
    })
    assert cleaned["compensation"] == ""


def test_clean_job_data_builds_from_amounts_and_keeps_real_pay():
    cleaned = clean_job_data({
        "title": "Nurse", "company": "Acme", "location": "Remote",
        "min_amount": 30, "max_amount": 40, "currency": "$", "interval": "hourly",
    })
    assert cleaned["compensation"] == "$30 - $40 hourly"

    kept = clean_job_data({
        "title": "Nurse", "company": "Acme", "location": "Remote",
        "compensation": "$120,000 a year",
    })
    assert kept["compensation"] == "$120,000 a year"
