"""
Scraper Configuration for Magnification Job Search Application.

This module contains configuration constants for job scraping operations:
- Supported job board sites
- Default scraping parameters
- ThreadPool settings
"""

from typing import List

# Supported job board sites
# These are the site identifiers used by the jobspy library
SUPPORTED_SITES: List[str] = [
    "indeed",
    "linkedin",
    "glassdoor",
    "zip_recruiter",
    "google"
]

# Default scraping parameters
DEFAULT_RESULTS_WANTED: int = 20  # Number of jobs to fetch per search
DEFAULT_HOURS_OLD: int = 24  # Only fetch jobs posted within this many hours
DEFAULT_COUNTRY: str = 'USA'  # Country for job searches

# ThreadPool configuration
# Default thread count: CPU cores minus 2 (minimum 1)
# This is calculated dynamically in concurrent_scraper.py
MIN_THREAD_COUNT: int = 1
THREAD_RESERVE: int = 2  # Number of cores to reserve for other tasks

# Request settings
REQUEST_TIMEOUT: int = 30  # Timeout for individual scraping requests in seconds
MAX_RETRIES: int = 3  # Maximum number of retry attempts for failed requests
RETRY_DELAY: float = 1.0  # Delay between retries in seconds

# Data directory settings
DEFAULT_DATA_DIR: str = 'data'

# Field mapping: jobspy field names to database column names
# This maps the raw jobspy output to our database schema
FIELD_MAPPING = {
    'title': 'title',
    'company': 'company',
    'location': 'location',
    'job_url': 'link',
    'description': 'description',
    'min_amount': 'compensation',  # Will be combined with max_amount
    'max_amount': 'compensation',
}

# Fields to extract from jobspy results
EXTRACT_FIELDS = [
    'title',
    'company',
    'location',
    'job_url',
    'description',
    'min_amount',
    'max_amount',
    'currency',
    'interval',
    'site',
]

# LinkedIn Description Scraping Config
# Used by linkedin_scraper.py to fetch job descriptions via guest API
LINKEDIN_GUEST_API_URL: str = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
LINKEDIN_FETCH_DELAY: float = 0.5  # Delay between requests in seconds (rate limiting)
LINKEDIN_REQUEST_TIMEOUT: int = 10  # Request timeout in seconds

