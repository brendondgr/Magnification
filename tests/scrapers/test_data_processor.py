"""
Tests for the in-batch job deduplication key (Title + Company only).

Location and site are intentionally excluded from the dedup key: the same opening
posted across many cities, or mirrored on multiple job boards, must collapse to a
single listing.
"""

from utils.backend.scrapers.data_processor import deduplicate_jobs


def test_same_title_company_different_location_dedupes_to_one():
    jobs = [
        {"title": "Software Engineer", "company": "Acme", "location": "New York, NY", "site": "indeed"},
        {"title": "Software Engineer", "company": "Acme", "location": "Austin, TX", "site": "indeed"},
    ]
    unique = deduplicate_jobs(jobs)
    assert len(unique) == 1
    assert unique[0]["location"] == "New York, NY"  # first occurrence wins


def test_same_title_company_across_sites_dedupes_to_one():
    jobs = [
        {"title": "Data Analyst", "company": "Globex", "location": "Remote", "site": "indeed"},
        {"title": "Data Analyst", "company": "Globex", "location": "Remote", "site": "linkedin"},
    ]
    unique = deduplicate_jobs(jobs)
    assert len(unique) == 1


def test_case_insensitive_match():
    jobs = [
        {"title": "Backend Engineer", "company": "Initech", "location": "Boston, MA"},
        {"title": "backend engineer", "company": "INITECH", "location": "Boston, MA"},
    ]
    unique = deduplicate_jobs(jobs)
    assert len(unique) == 1


def test_different_company_both_kept():
    jobs = [
        {"title": "Product Manager", "company": "Acme", "location": "Remote"},
        {"title": "Product Manager", "company": "Globex", "location": "Remote"},
    ]
    unique = deduplicate_jobs(jobs)
    assert len(unique) == 2


def test_missing_title_or_company_dropped():
    jobs = [
        {"title": "", "company": "Acme", "location": "Remote"},
        {"title": "Analyst", "company": "", "location": "Remote"},
        {"title": "Analyst", "company": "Acme", "location": "Remote"},
    ]
    unique = deduplicate_jobs(jobs)
    assert len(unique) == 1
    assert unique[0]["company"] == "Acme"
