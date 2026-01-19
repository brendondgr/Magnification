"""
JobSpy Wrapper for Magnification Job Search Application.

This module provides the wrapper interface for jobspy library operations:
- JobScrapeTask dataclass for managing individual scraping operations
- Error handling and retry logic
- Data normalization from jobspy format
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
import logging

from jobspy import scrape_jobs

from .scraper_config import (
    SUPPORTED_SITES,
    DEFAULT_RESULTS_WANTED,
    DEFAULT_HOURS_OLD,
    DEFAULT_COUNTRY,
    MAX_RETRIES,
    RETRY_DELAY
)

logger = logging.getLogger(__name__)


@dataclass
class JobScrapeTask:
    """
    Represents a job scraping task for a single job title across all sites.
    
    Each instance scrapes all specified sites for its job_title.
    Based on reference implementation from tests/job_scraper.py.
    """
    job_title: str
    sites: List[str] = field(default_factory=lambda: SUPPORTED_SITES.copy())
    results_wanted: int = DEFAULT_RESULTS_WANTED
    hours_old: int = DEFAULT_HOURS_OLD
    country_indeed: str = DEFAULT_COUNTRY
    location: Optional[str] = None
    
    # Results storage
    jobs_data: List[Dict[str, Any]] = field(default_factory=list, init=False)
    site_counts: Dict[str, int] = field(default_factory=dict, init=False)
    errors: Dict[str, str] = field(default_factory=dict, init=False)
    progress_callback: Optional[Callable[[int], None]] = field(default=None, init=False)
    
    def run(self) -> 'JobScrapeTask':
        """
        Execute the scraping for this job title across all sites.
        
        Returns:
            self: For easy result collection
        """
        logger.info(f"Starting scrape for '{self.job_title}' on {len(self.sites)} sites")
        
        for site in self.sites:
            try:
                # Prepare arguments for scrape_jobs
                scrape_args = {
                    'site_name': [site],
                    'search_term': self.job_title,
                    'results_wanted': self.results_wanted,
                    'hours_old': self.hours_old,
                    'country_indeed': self.country_indeed,
                    'location': self.location
                }
                
                # Special handling for Google
                if site == 'google' and self.location:
                    google_term = self._generate_google_search_term()
                    if google_term:
                        scrape_args['google_search_term'] = google_term
                
                jobs_df = scrape_jobs(**scrape_args)
                
                if jobs_df is not None and not jobs_df.empty:
                    # Add search metadata to the DataFrame
                    jobs_df['search_term'] = self.job_title
                    
                    # Convert to list of dictionaries
                    records = jobs_df.to_dict('records')
                    self.jobs_data.extend(records)
                    self.site_counts[site] = len(records)
                    
                    logger.info(f"  [{site}] Found {len(records)} jobs")
                else:
                    self.site_counts[site] = 0
                    logger.info(f"  [{site}] No jobs found")
                    
            except Exception as e:
                self.site_counts[site] = 0
                self.errors[site] = str(e)
                logger.error(f"  [{site}] Error: {e}")
            
            # Report progress for this site (success or fail)
            if self.progress_callback:
                # We report the count found for this specific site iteration
                # The callback should handle incrementing global progress
                count = self.site_counts.get(site, 0)
                self.progress_callback(count)
        
        logger.info(f"Completed scrape for '{self.job_title}': {self.total_jobs} total jobs")
        return self

    def _generate_google_search_term(self) -> Optional[str]:
        """
        Generate a specific search term for Google Jobs to include location and age.
        Format: "{job_title} jobs near {location} in the last {date}"
        """
        if not self.location:
            return None
            
        # Map hours to text
        if self.hours_old <= 24:
            date_str = "24 Hours"
        elif self.hours_old <= 48:
            date_str = "2 Days"
        elif self.hours_old <= 72:
            date_str = "3 Days"
        elif self.hours_old <= 168:
            date_str = "Week"
        elif self.hours_old <= 720:
            date_str = "Month"
        else:
            date_str = f"{self.hours_old} Hours"
            
        return f"{self.job_title} jobs near {self.location} in the last {date_str}"
    
    @property
    def total_jobs(self) -> int:
        """Return total number of jobs found for this task."""
        return len(self.jobs_data)
    
    @property
    def sanitized_title(self) -> str:
        """Return a filename-safe version of the job title."""
        return self.job_title.replace(" ", "_").replace("/", "_")
    
    @property
    def has_errors(self) -> bool:
        """Check if any errors occurred during scraping."""
        return len(self.errors) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the scraping results."""
        return {
            'job_title': self.job_title,
            'total_jobs': self.total_jobs,
            'site_counts': self.site_counts,
            'errors': self.errors,
            'sites_scraped': len(self.sites),
            'sites_with_results': sum(1 for c in self.site_counts.values() if c > 0)
        }


def scrape_single_site(
    job_title: str,
    site: str,
    results_wanted: int = DEFAULT_RESULTS_WANTED,
    hours_old: int = DEFAULT_HOURS_OLD,
    country: str = DEFAULT_COUNTRY,
    location: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Scrape jobs from a single site for a single job title.
    
    This is a simpler alternative to JobScrapeTask for individual operations.
    
    Args:
        job_title: Job title to search for
        site: Site identifier (e.g., 'indeed', 'linkedin')
        results_wanted: Number of results to fetch
        hours_old: Maximum age of job postings
        country: Country for job search
    
    Returns:
        List of job dictionaries
    """
    if site not in SUPPORTED_SITES:
        raise ValueError(f"Invalid site '{site}'. Supported sites: {SUPPORTED_SITES}")
    
    try:
        # Prepare arguments
        scrape_args = {
            'site_name': [site],
            'search_term': job_title,
            'results_wanted': results_wanted,
            'hours_old': hours_old,
            'country_indeed': country,
            'location': location
        }
        
        # Google special logic
        if site == 'google' and location:
            # Map hours to text (duplicate logic for standalone function, or could extract to helper)
            date_str = "24 Hours" # Default fallback
            if hours_old <= 24: date_str = "24 Hours"
            elif hours_old <= 48: date_str = "2 Days"
            elif hours_old <= 72: date_str = "3 Days"
            elif hours_old <= 168: date_str = "Week"
            elif hours_old <= 720: date_str = "Month"
            else: date_str = f"{hours_old} Hours"
            
            scrape_args['google_search_term'] = f"{job_title} jobs near {location} in the last {date_str}"

        jobs_df = scrape_jobs(**scrape_args)
        
        if jobs_df is not None and not jobs_df.empty:
            jobs_df['search_term'] = job_title
            return jobs_df.to_dict('records')
        
        return []
        
    except Exception as e:
        logger.error(f"Error scraping {site} for '{job_title}': {e}")
        return []


def normalize_job_data(raw_job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw jobspy result to a standard format.
    
    Args:
        raw_job: Raw job dictionary from jobspy
    
    Returns:
        Normalized job dictionary
    """
    # Build compensation string from salary data
    compensation = None
    min_amount = raw_job.get('min_amount')
    max_amount = raw_job.get('max_amount')
    currency = raw_job.get('currency', '')
    interval = raw_job.get('interval', '')
    
    if min_amount or max_amount:
        if min_amount and max_amount:
            compensation = f"{currency}{min_amount:,.0f} - {currency}{max_amount:,.0f}"
        elif min_amount:
            compensation = f"{currency}{min_amount:,.0f}"
        else:
            compensation = f"{currency}{max_amount:,.0f}"
        
        if interval:
            compensation += f" {interval}"
    
    return {
        'title': raw_job.get('title', ''),
        'company': raw_job.get('company', ''),
        'location': raw_job.get('location', ''),
        'link': raw_job.get('job_url', ''),
        'description': raw_job.get('description', ''),
        'compensation': compensation,
        'site': raw_job.get('site', ''),
        'search_term': raw_job.get('search_term', ''),
    }
