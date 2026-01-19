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
from .job_filter import filter_jobs, filter_and_mark_jobs, load_filter_config, apply_title_filter
from .linkedin_scraper import fetch_descriptions_for_jobs
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
                
            # If we are loading terms from config, we should also load other settings 
            # unless they were explicitly overridden in the function call.
            # We check if they are at their default values to decide if we should override from config.
            if sites is None:
                sites = config.get('sites')
            
            if results_wanted == DEFAULT_RESULTS_WANTED and 'results_wanted' in config:
                results_wanted = config.get('results_wanted')
                
            if hours_old == DEFAULT_HOURS_OLD and 'hours_old' in config:
                hours_old = config.get('hours_old')

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
        
        # Step 3.5: Fetch LinkedIn descriptions
        # LinkedIn jobs from JobSpy don't have descriptions, so we fetch them
        # via LinkedIn's guest API to enable description-based filtering.
        # Optimization: Filter by title first to avoid fetching for irrelevant jobs.
        raw_linkedin_jobs = [j for j in processed_jobs if str(j.get('site', '')).lower() == 'linkedin']
        
        if raw_linkedin_jobs:
            # Load filter config to apply title filter
            filter_config = load_filter_config()
            allowed_titles = filter_config.get('job_titles', [])
            
            # Filter LinkedIn jobs that pass title criteria
            linkedin_jobs_to_scrape = [
                j for j in raw_linkedin_jobs 
                if apply_title_filter(j, allowed_titles)
            ]
            
            if linkedin_jobs_to_scrape:
                update_progress('fetching_descriptions', 83, {
                    'message': f'Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs...'
                })
                logger.info(f"Step 3.5: Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs (after title filtering)...")
                
                def linkedin_progress(current, total):
                    # Map LinkedIn progress to 83-88% of overall workflow
                    percent = 83 + (current / total) * 5
                    update_progress('fetching_descriptions', percent, {
                        'message': f'Fetching LinkedIn descriptions ({current}/{total})...'
                    })
                
                # We pass the full processed_jobs list but only describe-fetch for the ones we want
                # fetch_descriptions_for_jobs already handles identifying which ones to fetch
                # Let's modify the scrape-logic here to only update the specific ones.
                
                processed_jobs = fetch_descriptions_for_jobs(processed_jobs, linkedin_progress, only_these_jobs=linkedin_jobs_to_scrape)
                
                # Count how many got descriptions
                with_desc = sum(1 for j in processed_jobs 
                              if str(j.get('site', '')).lower() == 'linkedin' 
                              and j.get('description'))
                results['steps']['linkedin_descriptions'] = {
                    'total_linkedin': len(raw_linkedin_jobs),
                    'passed_title_filter': len(linkedin_jobs_to_scrape),
                    'fetched': with_desc
                }
                logger.info(f"  Fetched {with_desc}/{len(linkedin_jobs_to_scrape)} LinkedIn descriptions")
            else:
                logger.info("  No LinkedIn jobs passed title filtering. Skipping description fetching.")
                results['steps']['linkedin_descriptions'] = {
                    'total_linkedin': len(raw_linkedin_jobs),
                    'passed_title_filter': 0,
                    'fetched': 0
                }
        
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
            'jobs_kept': filter_results.get('kept', 0) if isinstance(filter_results, dict) else len(filter_results.get('kept', [])),
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
