"""
Main Orchestration Service for Job Scraping Workflow.

This module coordinates all scraping operations:
- Task generation
- Concurrent scraping
- Data processing
- Database storage
- Filtering
"""

from typing import List, Dict, Any, Optional
import logging

from .task_generator import generate_scraping_tasks, load_jobs_config
from .concurrent_scraper import JobSpyScraper
from .data_processor import process_scraped_jobs, get_job_statistics
from .job_filter import filter_jobs, filter_and_mark_jobs, load_filter_config
from .scraper_config import (
    DEFAULT_RESULTS_WANTED,
    DEFAULT_HOURS_OLD,
    DEFAULT_COUNTRY,
    SUPPORTED_SITES
)

logger = logging.getLogger(__name__)


def execute_full_scraping_workflow(
    search_terms: Optional[List[str]] = None,
    sites: Optional[List[str]] = None,
    results_wanted: int = DEFAULT_RESULTS_WANTED,
    hours_old: int = DEFAULT_HOURS_OLD,
    save_to_database: bool = True,
    progress_callback: Optional[callable] = None,
    location: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute the full scraping workflow from start to finish.
    
    Workflow Steps:
    1. Generate scraping tasks from config (or provided terms)
    2. Execute concurrent scraping
    3. Process and deduplicate data
    4. Store jobs in database (if enabled)
    5. Apply filters and mark ignored jobs
    6. Return summary statistics
    
    Args:
        search_terms: Optional list of terms to search for. If None, loads from config.
        sites: Optional list of sites. If None, uses all supported sites.
        results_wanted: Number of results per search
        hours_old: Maximum age of job postings
        save_to_database: Whether to save results to database
        progress_callback: Optional function(status_dict) to report progress
    
    Returns:
        Dict containing workflow statistics and results
    """
    logger.info("=" * 60)
    logger.info("Starting Full Scraping Workflow")
    logger.info("=" * 60)
    
    results = {
        'success': False,
        'steps': {},
        'errors': []
    }

    def update_progress(stage, percent, details=None):
        if progress_callback:
            progress_callback({
                'stage': stage,
                'percent': percent,
                'details': details or {}
            })
    
    try:
        # Step 1: Load configuration and generate tasks
        update_progress('init', 5, {'message': 'Loading configuration...'})
        logger.info("Step 1: Loading configuration...")
        
        # Load config regardless to get filter criteria
        config = load_jobs_config()
        
        if search_terms is None:
            search_terms = config.get('search_terms', [])
            # Fallback to job_titles if search_terms is empty (backward compatibility)
            if not search_terms:
                search_terms = config.get('job_titles', [])
        
        if location is None:
            location = config.get('location', '')
            location = location if location else None
        
        if not search_terms:
            logger.warning("No search terms provided. Workflow aborted.")
            results['errors'].append("No search terms provided")
            update_progress('failed', 0, {'message': 'No search terms provided'})
            return results
        
        if sites is None:
            sites = SUPPORTED_SITES.copy()
        
        results['steps']['config'] = {
            'search_terms': search_terms,
            'sites': sites,
            'results_wanted': results_wanted,
            'hours_old': hours_old,
            'location': location
        }
        
        logger.info(f"  Search terms: {search_terms}")
        logger.info(f"  Sites: {sites}")
        
        # Step 2: Execute concurrent scraping
        update_progress('scraping', 10, {'message': f'Starting scrape for {len(search_terms)} terms...'})
        logger.info("Step 2: Executing concurrent scraping...")
        
        # Create a callback to bridge scraper progress to workflow progress (10% -> 80%)
        def scraper_progress_handler(scraper_percent, jobs_count):
            # Map 0-100% scraper progress to 10-80% workflow progress
            workflow_percent = 10 + (scraper_percent * 0.7)
            update_progress('scraping', workflow_percent, {
                'message': f'Scraping... ({int(scraper_percent)}% done) - Found {jobs_count} jobs',
                'jobs_found': jobs_count
            })

        # Note: JobSpyScraper takes 'job_titles' argument but we pass search_terms
        scraper = JobSpyScraper(
            job_titles=search_terms, 
            sites=sites,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country_indeed=DEFAULT_COUNTRY,
            location=location,
            progress_callback=scraper_progress_handler
        )
        
        scraper.run()
        raw_jobs = scraper.all_jobs
        
        results['steps']['scraping'] = {
            'raw_jobs_count': len(raw_jobs),
            'summary': scraper.get_summary()
        }
        
        logger.info(f"  Scraped {len(raw_jobs)} raw jobs")
        
        if not raw_jobs:
            logger.warning("No jobs scraped. Workflow complete.")
            results['success'] = True
            update_progress('completed', 100, {'message': 'No jobs found', 'jobs_found': 0})
            return results
        
        # Step 3: Process and deduplicate data
        update_progress('processing', 80, {'message': f'Processing {len(raw_jobs)} raw jobs...'})
        logger.info("Step 3: Processing and deduplicating data...")
        processed_jobs = process_scraped_jobs(raw_jobs)
        
        results['steps']['processing'] = {
            'processed_count': len(processed_jobs),
            'statistics': get_job_statistics(processed_jobs)
        }
        
        logger.info(f"  Processed {len(processed_jobs)} unique jobs")
        
        # Step 4: Store in database
        job_ids = []
        if save_to_database:
            update_progress('saving', 90, {'message': 'Saving to database...'})
            logger.info("Step 4: Storing jobs in database...")
            from ..database.operations import add_job, get_job_by_criteria
            
            stored_count = 0
            skipped_count = 0
            
            for job_data in processed_jobs:
                # Check for existing job (duplicate prevention)
                existing = get_job_by_criteria(
                    job_data['title'],
                    job_data['company'],
                    job_data['location']
                )
                
                if existing:
                    skipped_count += 1
                    continue
                
                try:
                    job_id = add_job(job_data)
                    job_ids.append(job_id)
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing job: {e}")
                    results['errors'].append(f"Store error: {e}")
            
            results['steps']['storage'] = {
                'stored_count': stored_count,
                'skipped_count': skipped_count,
                'job_ids': job_ids
            }
            
            logger.info(f"  Stored {stored_count} jobs, skipped {skipped_count} duplicates")
        else:
            logger.info("Step 4: Skipping database storage (disabled)")
            results['steps']['storage'] = {'skipped': True}
        
        # Step 5: Apply filters
        update_progress('filtering', 95, {'message': 'Applying filters...'})
        logger.info("Step 5: Applying filters...")
        if job_ids:
            # Mark jobs as ignored if they don't match criteria
            filter_results = filter_and_mark_jobs(job_ids)
            results['steps']['filtering'] = filter_results
            logger.info(f"  Kept {filter_results['kept']}, ignored {filter_results['ignored']}")
        else:
            # Filter in-memory for non-database mode
            filter_config = load_filter_config()
            filter_results = filter_jobs(processed_jobs, filter_config)
            results['steps']['filtering'] = {
                'kept': len(filter_results['kept']),
                'ignored': len(filter_results['ignored'])
            }
            logger.info(f"  Kept {len(filter_results['kept'])}, ignored {len(filter_results['ignored'])}")
        
        results['success'] = True
        update_progress('completed', 100, {
            'message': 'Completed',
            'jobs_found': len(processed_jobs),
            'jobs_added': len(job_ids) if save_to_database else 0
        })
        
        logger.info("=" * 60)
        logger.info("Scraping Workflow Complete")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"Workflow error: {e}")
        results['errors'].append(str(e))
        update_progress('failed', 0, {'message': f'Error: {str(e)}'})
    
    return results


def scrape_jobs_quick(
    job_titles: List[str],
    sites: Optional[List[str]] = None,
    results_wanted: int = DEFAULT_RESULTS_WANTED
) -> List[Dict[str, Any]]:
    """
    Quick scraping function that returns processed jobs without database storage.
    
    Useful for testing or one-off scraping operations.
    
    Args:
        job_titles: List of job titles to search
        sites: Optional list of sites
        results_wanted: Number of results per search
    
    Returns:
        List of processed job dictionaries
    """
    scraper = JobSpyScraper(
        job_titles=job_titles,
        sites=sites,
        results_wanted=results_wanted
    )
    
    scraper.run()
    return process_scraped_jobs(scraper.all_jobs)


def get_workflow_status() -> Dict[str, Any]:
    """
    Get current status/configuration of the scraping system.
    
    Returns:
        Dict containing current configuration and status
    """
    config = load_jobs_config()
    filter_config = load_filter_config()
    
    return {
        'configured_job_titles': config.get('job_titles', []),
        'configured_keywords': config.get('description_keywords', []),
        'supported_sites': SUPPORTED_SITES,
        'default_settings': {
            'results_wanted': DEFAULT_RESULTS_WANTED,
            'hours_old': DEFAULT_HOURS_OLD,
            'country': DEFAULT_COUNTRY
        }
    }
