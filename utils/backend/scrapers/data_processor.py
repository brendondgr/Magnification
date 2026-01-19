"""
Data Processor for Job Scraping Operations.

This module processes, cleans, and deduplicates scraped job data:
- Deduplication by title + company + location
- Data cleaning and validation
- Transformation to database format
"""

from typing import List, Dict, Any, Set, Tuple
import logging

from .jobspy_wrapper import normalize_job_data

logger = logging.getLogger(__name__)


def deduplicate_jobs(job_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate job listings based on title + company + location.
    
    Args:
        job_list: List of job dictionaries from scraping operations
    
    Returns:
        List of unique job dictionaries
    """
    seen: Set[Tuple[str, str, str]] = set()
    unique_jobs: List[Dict[str, Any]] = []
    duplicates_removed = 0
    
    for job in job_list:
        # Create composite key for deduplication
        title = str(job.get('title', '')).strip().lower()
        company = str(job.get('company', '')).strip().lower()
        location = str(job.get('location', '')).strip().lower()
        
        key = (title, company, location)
        
        if key not in seen and title and company:  # Skip if missing required fields
            seen.add(key)
            unique_jobs.append(job)
        else:
            duplicates_removed += 1
    
    logger.info(f"Deduplication: {len(job_list)} jobs -> {len(unique_jobs)} unique ({duplicates_removed} duplicates removed)")
    return unique_jobs


def clean_job_data(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean and validate a single job record.
    
    Args:
        job: Raw job dictionary
    
    Returns:
        Cleaned job dictionary
    """
    cleaned = {}
    
    # Clean string fields
    string_fields = ['title', 'company', 'location', 'link', 'description', 'compensation', 'site', 'search_term']
    for field in string_fields:
        value = job.get(field)
        if value is not None:
            # Convert to string and strip whitespace
            cleaned[field] = str(value).strip()
        else:
            cleaned[field] = ''
    
    # Handle job_url -> link mapping
    if not cleaned.get('link') and job.get('job_url'):
        cleaned['link'] = str(job.get('job_url')).strip()
    
    # Build compensation string if not already present
    if not cleaned.get('compensation'):
        min_amount = job.get('min_amount')
        max_amount = job.get('max_amount')
        currency = job.get('currency', '$')
        interval = job.get('interval', '')
        
        if min_amount or max_amount:
            try:
                if min_amount and max_amount:
                    cleaned['compensation'] = f"{currency}{float(min_amount):,.0f} - {currency}{float(max_amount):,.0f}"
                elif min_amount:
                    cleaned['compensation'] = f"{currency}{float(min_amount):,.0f}"
                else:
                    cleaned['compensation'] = f"{currency}{float(max_amount):,.0f}"
                
                if interval:
                    cleaned['compensation'] += f" {interval}"
            except (ValueError, TypeError):
                pass
    
    return cleaned


def validate_job(job: Dict[str, Any]) -> bool:
    """
    Validate that a job has all required fields.
    
    Args:
        job: Job dictionary to validate
    
    Returns:
        bool: True if job is valid
    """
    required_fields = ['title', 'company', 'location']
    
    for field in required_fields:
        value = job.get(field)
        if not value or not str(value).strip():
            return False
    
    return True


def transform_to_db_format(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a cleaned job dictionary to database schema format.
    
    Args:
        job: Cleaned job dictionary
    
    Returns:
        Dictionary matching database Job model fields
    """
    return {
        'title': job.get('title', ''),
        'company': job.get('company', ''),
        'location': job.get('location', ''),
        'link': job.get('link', ''),
        'description': job.get('description', ''),
        'compensation': job.get('compensation', ''),
        'site': job.get('site', ''),  # Preserve site for LinkedIn description fetching
        'ignore': 0,  # Default to tracking
    }


def process_scraped_jobs(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Orchestrate the full processing pipeline for scraped jobs.
    
    Steps:
    1. Deduplicate jobs
    2. Clean each job
    3. Validate jobs
    4. Transform to database format
    
    Args:
        raw_jobs: List of raw job dictionaries from scraping
    
    Returns:
        List of processed job dictionaries ready for database insertion
    """
    logger.info(f"Processing {len(raw_jobs)} raw jobs...")
    
    # Step 1: Deduplicate
    unique_jobs = deduplicate_jobs(raw_jobs)
    
    # Step 2 & 3: Clean and validate
    valid_jobs = []
    invalid_count = 0
    
    for job in unique_jobs:
        cleaned = clean_job_data(job)
        if validate_job(cleaned):
            valid_jobs.append(cleaned)
        else:
            invalid_count += 1
    
    if invalid_count > 0:
        logger.warning(f"Removed {invalid_count} invalid jobs (missing required fields)")
    
    # Step 4: Transform to database format
    db_ready_jobs = [transform_to_db_format(job) for job in valid_jobs]
    
    logger.info(f"Processing complete: {len(db_ready_jobs)} jobs ready for database")
    return db_ready_jobs


def get_job_statistics(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate statistics about a list of jobs.
    
    Args:
        jobs: List of job dictionaries
    
    Returns:
        Dictionary containing job statistics
    """
    if not jobs:
        return {'total': 0}
    
    # Count jobs by company
    companies: Dict[str, int] = {}
    for job in jobs:
        company = job.get('company', 'Unknown')
        companies[company] = companies.get(company, 0) + 1
    
    # Count jobs by location
    locations: Dict[str, int] = {}
    for job in jobs:
        location = job.get('location', 'Unknown')
        locations[location] = locations.get(location, 0) + 1
    
    # Count jobs with compensation
    with_compensation = sum(1 for job in jobs if job.get('compensation'))
    
    return {
        'total': len(jobs),
        'unique_companies': len(companies),
        'unique_locations': len(locations),
        'with_compensation': with_compensation,
        'top_companies': sorted(companies.items(), key=lambda x: x[1], reverse=True)[:10],
        'top_locations': sorted(locations.items(), key=lambda x: x[1], reverse=True)[:10],
    }
