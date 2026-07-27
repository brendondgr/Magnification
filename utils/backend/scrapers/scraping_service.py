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
        Dict containing workflow statistics and results. Alongside `steps`, the payload carries
        run-level totals accumulated across **every** iteration: `jobs_found` (raw listings
        returned by the boards), `jobs_unique` (after in-batch dedup), `jobs_saved`/`jobs_added`
        (rows inserted), and `jobs_kept` (survived filtering). The same totals are pushed through
        `progress_callback` as `details.jobs_found` / `details.jobs_saved` / `details.jobs_kept`
        so a client polling mid-run sees cumulative, monotonic counters rather than per-pass ones.
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
        
        # Resolve the number of search iterations. Each iteration re-runs steps 2–5 with a
        # deeper page `offset` (advanced by results_wanted) to surface *additional* unique jobs;
        # cross-iteration uniqueness is guaranteed by the in-batch dedup (step 3) + the database
        # dedup (step 3.5), which drop anything an earlier pass already saved. Non-DB mode can't
        # dedup across passes, so it always runs a single pass.
        try:
            max_iterations = min(5, max(1, int(config.get('max_iterations', 1) or 1)))
        except (TypeError, ValueError):
            max_iterations = 1
        if not save_to_database:
            max_iterations = 1

        # Run-level cumulative counters. Every iteration builds a *fresh* JobSpyScraper (whose
        # own tally restarts at zero) and overwrites its slice of `results['steps']`, so the
        # numbers the UI shows — "Jobs Found" / "Jobs Saved" — must be accumulated here instead
        # of read off a single pass. `cum_raw` is every raw listing the boards returned,
        # `cum_processed` the in-batch-unique remainder, `cum_stored` the rows actually inserted.
        totals = {'raw': 0, 'processed': 0, 'db_dedup_removed': 0, 'stored': 0}
        iteration_passes = []
        all_job_ids = []

        def _scrape_process_store(iteration, offset):
            """One scrape → process → db-dedup → LinkedIn → save pass at the given page offset.

            Returns (job_ids, raw_count, processed_jobs). Passes that find nothing return
            ([], raw_count, []) so the outer loop can try the next page rather than ending the
            whole workflow.

            Updates `totals` in place as each stage completes, and reports the *cumulative*
            `jobs_found` / `jobs_saved` through the progress callback so the client never sees a
            counter walk backwards at an iteration boundary.
            """
            iter_tag = f'[iter {iteration}/{max_iterations}] ' if max_iterations > 1 else ''
            raw_before = totals['raw']

            # Step 2: Execute concurrent scraping
            _countries_txt = ', '.join(countries) if countries else DEFAULT_COUNTRY
            _jt_txt = f' · {job_type}' if job_type else ''
            update_progress('scraping', 10, {'message': (
                f'{iter_tag}Searching {len(search_terms)} term(s) on {len(sites)} site(s) · '
                f'{_countries_txt}{_jt_txt}'
            )})
            logger.info(f"Step 2: Executing concurrent scraping (offset={offset})...")

            # Create a callback to bridge scraper progress to workflow progress (10% -> 80%)
            # Only emit once per 20% bucket of scraper progress to avoid flooding the
            # activity feed with a "Scraping..." update for every completed site/term.
            last_logged_bucket = [-1]

            def scraper_progress_handler(scraper_percent, jobs_count):
                bucket = int(scraper_percent // 20)
                if bucket == last_logged_bucket[0] and scraper_percent < 100:
                    return
                last_logged_bucket[0] = bucket

                # `jobs_count` is this pass' own tally (a fresh scraper per iteration), so add
                # the earlier passes' raw total to keep the reported figure run-cumulative.
                running_found = raw_before + jobs_count
                # Map 0-100% scraper progress to 10-80% workflow progress
                workflow_percent = 10 + (scraper_percent * 0.7)
                update_progress('scraping', workflow_percent, {
                    'message': f'{iter_tag}Scraping... ({int(scraper_percent)}% done) - Found {running_found} jobs',
                    'jobs_found': running_found,
                    'jobs_saved': totals['stored'],
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
                job_type=job_type,
                offset=offset
            )

            scraper.run()
            raw_jobs = scraper.all_jobs
            totals['raw'] += len(raw_jobs)

            # `raw_jobs_count` is the run total across every iteration; `last_pass_count` and
            # `summary` describe the pass that just finished.
            results['steps']['scraping'] = {
                'raw_jobs_count': totals['raw'],
                'last_pass_count': len(raw_jobs),
                'summary': scraper.get_summary()
            }

            logger.info(f"  Scraped {len(raw_jobs)} raw jobs (run total {totals['raw']})")

            if not raw_jobs:
                logger.warning(f"{iter_tag}No jobs scraped this pass.")
                return [], 0, []

            # Step 3: Process and deduplicate data (in-batch, within and across job sites,
            # by Title+Company — see data_processor.deduplicate_jobs)
            update_progress('processing', 80, {'message': f'{iter_tag}Processing {len(raw_jobs)} raw jobs...'})
            logger.info("Step 3: Processing and deduplicating data...")
            processed_jobs = process_scraped_jobs(raw_jobs)
            totals['processed'] += len(processed_jobs)
            update_progress('processing', 82, {
                'message': f'{iter_tag}Deduplicated {len(raw_jobs)} → {len(processed_jobs)} unique jobs',
                'jobs_found': totals['raw'],
                'jobs_saved': totals['stored'],
            })

            results['steps']['processing'] = {
                'processed_count': totals['processed'],
                'last_pass_count': len(processed_jobs),
                'statistics': get_job_statistics(processed_jobs)
            }

            logger.info(f"  Processed {len(processed_jobs)} unique jobs")

            # Step 3.5: Drop jobs already tracked in the database (same Title+Company match as
            # the in-batch dedup above), *before* fetching LinkedIn descriptions or running any
            # LLM calls on them — those are the expensive steps this ordering is meant to protect.
            # This is also what makes each iteration surface only *new* jobs vs. earlier passes.
            from ..database.operations import get_existing_job_keys
            existing_keys = get_existing_job_keys()
            before_db_dedup = len(processed_jobs)
            processed_jobs = [
                j for j in processed_jobs
                if (str(j.get('title', '')).strip().lower(), str(j.get('company', '')).strip().lower())
                not in existing_keys
            ]
            removed_existing = before_db_dedup - len(processed_jobs)
            totals['db_dedup_removed'] += removed_existing
            results['steps']['db_dedup'] = {
                'removed': totals['db_dedup_removed'],
                'last_pass_removed': removed_existing,
                'remaining': len(processed_jobs),
            }
            update_progress('processing', 83, {
                'message': f'{iter_tag}Removed {removed_existing} job(s) already in database · {len(processed_jobs)} remaining',
                'jobs_found': totals['raw'],
                'jobs_saved': totals['stored'],
            })
            logger.info(f"  Removed {removed_existing} already-tracked jobs, {len(processed_jobs)} remaining")

            if not processed_jobs:
                logger.info(f"{iter_tag}No new jobs remain after database dedup this pass.")
                return [], len(raw_jobs), []

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
                        'message': f'{iter_tag}Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs...'
                    })
                    logger.info(f"Step 4: Fetching descriptions for {len(linkedin_jobs_to_scrape)} LinkedIn jobs (after title filtering)...")

                    def linkedin_progress(current, total):
                        # Map LinkedIn progress to 84-88% of overall workflow
                        percent = 84 + (current / total) * 4
                        update_progress('fetching_descriptions', percent, {
                            'message': f'{iter_tag}Fetching LinkedIn descriptions ({current}/{total})...'
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
            iter_job_ids = []
            if save_to_database:
                update_progress('saving', 88, {
                    'message': f'{iter_tag}Saving to database...',
                    'jobs_found': totals['raw'],
                    'jobs_saved': totals['stored'],
                })
                logger.info("Step 5: Storing jobs in database...")
                from ..database.operations import add_job

                stored_count = 0

                for job_data in processed_jobs:
                    try:
                        job_id = add_job(job_data)
                        iter_job_ids.append(job_id)
                        stored_count += 1
                    except Exception as e:
                        logger.error(f"Error storing job: {e}")
                        results['errors'].append(f"Store error: {e}")

                # Roll the newly-inserted rows into the run total the moment they land, so
                # "Jobs Saved" ticks up per iteration rather than only at completion.
                totals['stored'] += stored_count
                all_job_ids.extend(iter_job_ids)
                results['steps']['storage'] = {
                    'stored_count': totals['stored'],
                    'last_pass_count': stored_count,
                    'job_ids': list(all_job_ids)
                }

                update_progress('saving', 90, {
                    'message': (
                        f'{iter_tag}Stored {stored_count} new job(s)'
                        + (f" · {totals['stored']} saved so far" if max_iterations > 1 else '')
                    ),
                    'jobs_found': totals['raw'],
                    'jobs_saved': totals['stored'],
                })
                logger.info(f"  Stored {stored_count} jobs (run total {totals['stored']})")
            else:
                logger.info("Step 5: Skipping database storage (disabled)")
                results['steps']['storage'] = {'skipped': True}

            return iter_job_ids, len(raw_jobs), processed_jobs

        # Run the scrape/store block once per iteration, paging deeper each pass and
        # accumulating the newly-saved job ids. Steps 6–7 run ONCE over the accumulation.
        job_ids = []
        processed_jobs = []
        for _i in range(max_iterations):
            _ids, _raw, _proc = _scrape_process_store(_i + 1, _i * results_wanted)
            job_ids.extend(_ids)
            processed_jobs = _proc  # last pass' processed jobs (used by the non-DB filter path)
            iteration_passes.append({
                'iteration': _i + 1,
                'offset': _i * results_wanted,
                'raw': _raw,
                'stored': len(_ids),
            })
            if max_iterations > 1:
                update_progress('saving', 90, {
                    'message': (
                        f'Iteration {_i + 1}/{max_iterations} done · +{len(_ids)} new job(s) '
                        f'(total {len(job_ids)})'
                    ),
                    'jobs_found': totals['raw'],
                    'jobs_saved': totals['stored'],
                })
        total_raw = totals['raw']
        if max_iterations > 1:
            results['steps']['iterations'] = {
                'count': max_iterations,
                'total_raw': total_raw,
                'total_unique': totals['processed'],
                'total_new_stored': len(job_ids),
                'passes': iteration_passes,
            }

        # No new jobs across all passes (DB mode): nothing to filter/analyze — complete here.
        # Report the *real* cumulative raw total; zeroing `jobs_found` here would wipe a
        # legitimately non-zero counter just because everything deduped away.
        if save_to_database and not job_ids:
            logger.info("No new jobs found across all iterations. Workflow complete.")
            results['success'] = True
            results['jobs_found'] = total_raw
            results['jobs_unique'] = totals['processed']
            results['jobs_saved'] = 0
            results['jobs_kept'] = 0
            results['jobs_added'] = 0
            update_progress('completed', 100, {
                'message': f'No new jobs found ({total_raw} listing(s) checked)',
                'jobs_found': total_raw,
                'jobs_unique': totals['processed'],
                'jobs_saved': 0,
                'jobs_kept': 0,
                'jobs_added': 0,
            })
            return results

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

            # Step 7a: description enrichment — pull compensation + industry out of each
            # description in one LLM pass. This is the SAME code path "Analyze Matches"
            # runs (utils/backend/recommend/enrichment.py); the gating, candidate
            # selection, and persistence live there, not here. Non-fatal.
            try:
                from ..recommend.enrichment import enrich_jobs
                from ..recommend.runtime_config import get_runtime_config
                enriched = enrich_jobs(
                    kept_jobs, get_runtime_config(),
                    on_progress=lambda msg: update_progress(
                        'extracting_enrichment', 93, {'message': msg})
                )
                if enriched['candidates']:
                    results['steps']['enrichment'] = enriched
            except Exception as e:
                logger.error(f"Enrichment (pay/industry) extraction failed (non-fatal): {e}")
                results['errors'].append(f"Enrichment error: {e}")

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
        _kept = (filter_results.get('kept', 0) if isinstance(filter_results.get('kept'), int)
                 else len(filter_results.get('kept', [])))
        # Run totals on the returned payload too — `scheduler/daily_runner` logs
        # result['jobs_found'/'jobs_kept'/'jobs_added'], which previously had no such keys.
        results['jobs_found'] = total_raw
        results['jobs_unique'] = totals['processed'] if save_to_database else len(processed_jobs)
        results['jobs_saved'] = len(job_ids) if save_to_database else 0
        results['jobs_kept'] = _kept
        results['jobs_added'] = len(job_ids) if save_to_database else 0
        update_progress('completed', 100, {
            'message': 'Completed',
            # Every raw listing the boards returned across all iterations — the same figure the
            # live counter climbs to, so it never drops at the end of the run.
            'jobs_found': total_raw,
            # The in-batch-unique remainder, and the rows actually inserted (DB mode).
            'jobs_unique': totals['processed'] if save_to_database else len(processed_jobs),
            'jobs_saved': len(job_ids) if save_to_database else 0,
            'jobs_kept': _kept,
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
