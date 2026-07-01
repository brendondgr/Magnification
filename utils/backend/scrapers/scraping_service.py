"""
Main Orchestration Service for Job Scraping Workflow.

This module coordinates all scraping operations:
- Task generation
- Concurrent scraping
- Data processing / dedup (in-batch and against the database)
- LinkedIn description fetching
- Database storage
- Filtering
- Compensation extraction + recommendation scoring (on the filtered remainder)
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
    3. Process and deduplicate data (in-batch, within and across job sites, by Title+Company)
    3.5. Drop jobs already tracked in the database (same Title+Company match)
    4. Fetch LinkedIn descriptions for the remaining jobs
    5. Store new jobs in database (if enabled)
    6. Apply title/keyword filters and mark ignored jobs
    7. Extract LLM compensation + build recommendations together, for every kept job
    8. Return summary statistics

    Steps 3.5 and 6 exist specifically so that the expensive LinkedIn fetch (step 4) and
    LLM compensation/recommendation work (step 7) only ever run against jobs that are both
    new and pass the keyword filter — not the full scraped batch.
    
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

        # Multi-country + job-type (from config; empty -> single default country)
        countries = config.get('countries') or []
        job_type = config.get('job_type') or None

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
            'location': location,
            'countries': countries,
            'job_type': job_type
        }
        
        logger.info(f"  Search terms: {search_terms}")
        logger.info(f"  Sites: {sites}")
        
        # Step 2: Execute concurrent scraping
        _countries_txt = ', '.join(countries) if countries else DEFAULT_COUNTRY
        _jt_txt = f' · {job_type}' if job_type else ''
        update_progress('scraping', 10, {'message': (
            f'Searching {len(search_terms)} term(s) on {len(sites)} site(s) · '
            f'{_countries_txt}{_jt_txt}'
        )})
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
            progress_callback=scraper_progress_handler,
            countries=countries,
            job_type=job_type
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
        
        # Step 3: Process and deduplicate data (in-batch, within and across job sites,
        # by Title+Company — see data_processor.deduplicate_jobs)
        update_progress('processing', 80, {'message': f'Processing {len(raw_jobs)} raw jobs...'})
        logger.info("Step 3: Processing and deduplicating data...")
        processed_jobs = process_scraped_jobs(raw_jobs)
        update_progress('processing', 82, {'message': f'Deduplicated {len(raw_jobs)} → {len(processed_jobs)} unique jobs'})

        results['steps']['processing'] = {
            'processed_count': len(processed_jobs),
            'statistics': get_job_statistics(processed_jobs)
        }

        logger.info(f"  Processed {len(processed_jobs)} unique jobs")

        # Step 3.5: Drop jobs already tracked in the database (same Title+Company match as
        # the in-batch dedup above), *before* fetching LinkedIn descriptions or running any
        # LLM calls on them — those are the expensive steps this ordering is meant to protect.
        from ..database.operations import get_existing_job_keys
        existing_keys = get_existing_job_keys()
        before_db_dedup = len(processed_jobs)
        processed_jobs = [
            j for j in processed_jobs
            if (str(j.get('title', '')).strip().lower(), str(j.get('company', '')).strip().lower())
            not in existing_keys
        ]
        removed_existing = before_db_dedup - len(processed_jobs)
        results['steps']['db_dedup'] = {'removed': removed_existing, 'remaining': len(processed_jobs)}
        update_progress('processing', 83, {
            'message': f'Removed {removed_existing} job(s) already in database · {len(processed_jobs)} remaining'
        })
        logger.info(f"  Removed {removed_existing} already-tracked jobs, {len(processed_jobs)} remaining")

        if not processed_jobs:
            logger.info("No new jobs remain after database dedup. Workflow complete.")
            results['success'] = True
            update_progress('completed', 100, {'message': 'No new jobs found', 'jobs_found': 0})
            return results

        # Step 4: Fetch LinkedIn descriptions
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
                update_progress('fetching_descriptions', 84, {
                    'message': f'Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs...'
                })
                logger.info(f"Step 4: Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs (after title filtering)...")

                def linkedin_progress(current, total):
                    # Map LinkedIn progress to 84-88% of overall workflow
                    percent = 84 + (current / total) * 4
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

        # Step 5: Save new jobs to database. Every job remaining here already passed the
        # in-batch dedup (step 3) and the database dedup (step 3.5), so no per-job
        # duplicate lookup is needed before inserting.
        job_ids = []
        if save_to_database:
            update_progress('saving', 88, {'message': 'Saving to database...'})
            logger.info("Step 5: Storing jobs in database...")
            from ..database.operations import add_job

            stored_count = 0

            for job_data in processed_jobs:
                try:
                    job_id = add_job(job_data)
                    job_ids.append(job_id)
                    stored_count += 1
                except Exception as e:
                    logger.error(f"Error storing job: {e}")
                    results['errors'].append(f"Store error: {e}")

            results['steps']['storage'] = {
                'stored_count': stored_count,
                'job_ids': job_ids
            }

            update_progress('saving', 90, {'message': f'Stored {stored_count} new job(s)'})
            logger.info(f"  Stored {stored_count} jobs")
        else:
            logger.info("Step 5: Skipping database storage (disabled)")
            results['steps']['storage'] = {'skipped': True}

        # Step 6: Apply title/description keyword filters, marking non-matching jobs ignored
        update_progress('filtering', 91, {'message': 'Applying filters...'})
        logger.info("Step 6: Applying filters...")
        if job_ids:
            # Mark jobs as ignored if they don't match criteria
            filter_results = filter_and_mark_jobs(job_ids)
            results['steps']['filtering'] = filter_results
            update_progress('filtering', 92, {'message': f"Filtered: kept {filter_results['kept']} · ignored {filter_results['ignored']}"})
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

        # Step 7: Compensation extraction + recommendation scoring, run together on every
        # job that survived filtering (however many that is) — this is the whole point of
        # the reorder: neither step touches jobs that were already-tracked duplicates or
        # that got filtered out, so LinkedIn/LLM cost only goes toward jobs that are kept.
        if save_to_database and job_ids:
            from ..database.operations import get_jobs_by_ids
            kept_jobs = [j for j in get_jobs_by_ids(job_ids) if not j.get('ignore')]

            # Step 7a: LLM compensation extraction — recover pay that is only written in
            # the description prose (common on LinkedIn, which shows "Not specified"
            # otherwise). Gated by the LLM endpoint being enabled + the runtime toggle;
            # non-fatal.
            try:
                from ..recommend.runtime_config import get_runtime_config
                comp_rc = get_runtime_config()
                if comp_rc.get('enable_llm_compensation') and kept_jobs:
                    from ..llm.config import load_llm_endpoint_config
                    if load_llm_endpoint_config().get('enabled'):
                        from ..recommend.compensation import extract_compensation_llm, needs_compensation
                        from ..llm.client import OpenAIClient
                        from ..database.operations import update_job
                        pending = [j for j in kept_jobs if needs_compensation(j)]
                        if pending:
                            update_progress('extracting_compensation', 93, {
                                'message': f'Extracting compensation from {len(pending)} description(s) via LLM...'
                            })
                            client = OpenAIClient.from_config()
                            extracted = extract_compensation_llm(
                                kept_jobs, client, max_workers=comp_rc.get('llm_workers', 4)
                            )
                            for job in pending:
                                if job.get('compensation'):
                                    update_job(job['id'], {'compensation': job['compensation']})
                            results['steps']['compensation'] = {'candidates': len(pending), 'extracted': extracted}
                            update_progress('extracting_compensation', 95, {
                                'message': f'Recovered compensation for {extracted} job(s)'
                            })
                            logger.info(f"  LLM compensation: extracted {extracted}/{len(pending)}")
            except Exception as e:
                logger.error(f"Compensation extraction failed (non-fatal): {e}")
                results['errors'].append(f"Compensation error: {e}")

            # Step 7b: Recommendation analysis (RAG) — embed + score against the active
            # profile. Optional and non-fatal (e.g. the embedding model may be unavailable
            # offline); gated by runtime config + an existing profile. analyze_jobs already
            # restricts itself to non-ignored jobs, so passing the full job_ids list scores
            # every kept job regardless of count.
            try:
                from ..recommend.runtime_config import get_runtime_config
                from ..database.operations import get_active_profile
                runtime_cfg = get_runtime_config()
                if runtime_cfg.get('enable_analysis') and get_active_profile() is not None:
                    update_progress('analyzing', 97, {'message': 'Scoring against your profile...'})
                    from ..recommend.service import analyze_jobs
                    analysis_result = analyze_jobs(job_ids=job_ids, runtime=runtime_cfg)
                    results['steps']['analysis'] = {'analyzed': analysis_result.get('analyzed', 0)}
                    update_progress('analyzing', 99, {'message': f"Scored {analysis_result.get('analyzed', 0)} job(s) against your profile"})
                    logger.info(f"  Analyzed {analysis_result.get('analyzed', 0)} jobs against profile")
            except Exception as e:
                logger.error(f"Analysis step failed (non-fatal): {e}")
                results['errors'].append(f"Analysis error: {e}")

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
