"""
LinkedIn Job Description Scraper.

This module fetches job descriptions for LinkedIn postings using LinkedIn's 
guest API endpoint. This is necessary because JobSpy does not provide 
descriptions for LinkedIn jobs.

Usage:
    from .linkedin_scraper import fetch_descriptions_for_jobs
    jobs_with_descriptions = fetch_descriptions_for_jobs(jobs)
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional

import requests
from bs4 import BeautifulSoup

from .scraper_config import (
    LINKEDIN_GUEST_API_URL,
    LINKEDIN_FETCH_DELAY,
    LINKEDIN_REQUEST_TIMEOUT
)

logger = logging.getLogger(__name__)

# User-Agent header to mimic a real browser
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def extract_linkedin_job_id(job_url: str) -> Optional[str]:
    """
    Extract the LinkedIn job ID from a job URL.
    
    LinkedIn job URLs typically contain a 10-digit numeric job ID in formats like:
    - https://www.linkedin.com/jobs/view/1234567890
    - https://www.linkedin.com/jobs/view/1234567890/
    - https://linkedin.com/jobs/view/1234567890?...
    
    Args:
        job_url: LinkedIn job posting URL
    
    Returns:
        The extracted job ID string, or None if not found
    """
    if not job_url:
        return None
    
    # Pattern to match LinkedIn job ID (typically 10 digits)
    # Matches /jobs/view/{id} or /jobs/{id}
    patterns = [
        r'/jobs/view/(\d+)',
        r'/jobs/(\d+)',
        r'currentJobId=(\d+)',
        r'jobId=(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, job_url)
        if match:
            return match.group(1)
    
    return None


def clean_html_text(html_content: str) -> str:
    """
    Clean HTML content and convert to plain text.
    
    Removes HTML tags while preserving basic structure (newlines for breaks,
    bullets for list items).
    
    Args:
        html_content: Raw HTML string
    
    Returns:
        Cleaned plain text string
    """
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Replace <br> tags with newlines
    for br in soup.find_all('br'):
        br.replace_with('\n')
    
    # Replace list items with bullet points
    for li in soup.find_all('li'):
        li.insert_before('• ')
        li.insert_after('\n')
    
    # Replace paragraph ends with newlines
    for p in soup.find_all('p'):
        p.insert_after('\n')
    
    # Get text and clean up whitespace
    text = soup.get_text()
    
    # Normalize whitespace while preserving newlines
    lines = text.split('\n')
    cleaned_lines = [' '.join(line.split()) for line in lines]
    text = '\n'.join(line for line in cleaned_lines if line)
    
    return text.strip()


def fetch_linkedin_description(job_id: str) -> Optional[str]:
    """
    Fetch job description from LinkedIn's guest API.
    
    Uses the endpoint: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}
    
    Args:
        job_id: LinkedIn job ID (10-digit numeric string)
    
    Returns:
        Job description text, or None if fetch fails
    """
    if not job_id:
        return None
    
    url = LINKEDIN_GUEST_API_URL.format(job_id=job_id)
    logger.info(f"[DEBUG] Fetching LinkedIn job {job_id} from: {url}")
    
    try:
        response = requests.get(
            url,
            headers=DEFAULT_HEADERS,
            timeout=LINKEDIN_REQUEST_TIMEOUT
        )
        
        if response.status_code == 429:
            logger.warning(f"Rate limited by LinkedIn for job {job_id}")
            return None
        
        if response.status_code == 404:
            logger.debug(f"Job {job_id} not found (may be expired or private)")
            return None
        
        if response.status_code != 200:
            logger.warning(f"Failed to fetch job {job_id}: HTTP {response.status_code}")
            return None
        
        # Parse the HTML response
        logger.info(f"[DEBUG] Got response for job {job_id}, status: {response.status_code}, length: {len(response.text)} chars")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the job description in the show-more-less-html__markup class
        description_div = soup.find(class_='show-more-less-html__markup')
        
        if description_div:
            desc_text = clean_html_text(str(description_div))
            # Debug: print first 30 chars with newlines escaped
            preview = desc_text[:30].replace('\n', '\\n').replace('\r', '\\r') if desc_text else "(empty)"
            logger.info(f"[DEBUG] Job {job_id} description preview: '{preview}...'")
            return desc_text
        
        # Fallback: try other common description containers
        fallback_selectors = [
            'description__text',
            'job-description',
            'description',
        ]
        
        for selector in fallback_selectors:
            desc_element = soup.find(class_=selector)
            if desc_element:
                return clean_html_text(str(desc_element))
        
        logger.info(f"[DEBUG] No description element found for job {job_id}. Response snippet: {response.text[:200]}...")
        return None
        
    except requests.Timeout:
        logger.warning(f"Timeout fetching description for job {job_id}")
        return None
    except requests.RequestException as e:
        logger.error(f"Request error for job {job_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching job {job_id}: {e}")
        return None


def fetch_descriptions_for_jobs(
    jobs: List[Dict[str, Any]],
    progress_callback: Optional[callable] = None,
    only_these_jobs: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Fetch descriptions for all LinkedIn jobs in a list.
    
    Only fetches descriptions for jobs from LinkedIn that don't already
    have descriptions. Adds a delay between requests to avoid rate limiting.
    
    Args:
        jobs: List of job dictionaries
        progress_callback: Optional function(current, total) for progress updates
        only_these_jobs: Optional subset of jobs to fetch descriptions for
    
    Returns:
        The same list with descriptions added to LinkedIn jobs
    """
    # Identify which jobs we should actually process
    target_jobs = only_these_jobs if only_these_jobs is not None else jobs
    
    # Identify LinkedIn jobs without descriptions within the target list
    linkedin_jobs_to_fetch = []
    for target_job in target_jobs:
        site = str(target_job.get('site', '')).lower()
        if site == 'linkedin':
            description = target_job.get('description', '')
            if not description or description.strip() == '':
                # Find the index in the original 'jobs' list to update it
                # We use identity comparison if possible, otherwise rely on content
                # Since jobs are dicts, we can find it by index or matching fields
                # However, scraping_service.py passes individual objects that are also in 'jobs'
                # So we can just find which index in 'jobs' matches the target_job object
                try:
                    job_index = -1
                    for idx, j in enumerate(jobs):
                        if j is target_job: # Identity check
                            job_index = idx
                            break
                    
                    if job_index == -1:
                        continue # Should not happen if only_these_jobs is a subset
                        
                    job_url = target_job.get('link', '') or target_job.get('job_url', '')
                    logger.info(f"[DEBUG] LinkedIn job URL: {job_url}")
                    job_id = extract_linkedin_job_id(job_url)
                    if job_id:
                        logger.info(f"[DEBUG] Extracted job ID: {job_id}")
                        linkedin_jobs_to_fetch.append((job_index, job_id))
                    else:
                        logger.warning(f"[DEBUG] Could not extract job ID from URL: {job_url}")
                except Exception as e:
                    logger.error(f"Error identifying job index: {e}")
    
    if not linkedin_jobs_to_fetch:
        logger.info("No LinkedIn jobs need description fetching")
        return jobs
    
    logger.info(f"Fetching descriptions for {len(linkedin_jobs_to_fetch)} LinkedIn jobs...")
    
    fetched_count = 0
    failed_count = 0
    
    for idx, (job_index, job_id) in enumerate(linkedin_jobs_to_fetch):
        # Report progress
        if progress_callback:
            try:
                progress_callback(idx + 1, len(linkedin_jobs_to_fetch))
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")
        
        # Fetch the description
        description = fetch_linkedin_description(job_id)
        
        if description:
            jobs[job_index]['description'] = description
            fetched_count += 1
            logger.debug(f"Fetched description for job {job_id} ({len(description)} chars)")
        else:
            failed_count += 1
        
        # Rate limiting delay (skip for last item)
        if idx < len(linkedin_jobs_to_fetch) - 1:
            time.sleep(LINKEDIN_FETCH_DELAY)
    
    logger.info(
        f"LinkedIn descriptions: {fetched_count} fetched, "
        f"{failed_count} failed out of {len(linkedin_jobs_to_fetch)} total"
    )
    
    return jobs
