"""
Concurrent Scraper for Magnification Job Search Application.

This module provides concurrent execution of scraping tasks using ThreadPool:
- JobSpyScraper class that manages multiple JobScrapeTask instances
- ThreadPoolExecutor for concurrent execution
- Result aggregation from all concurrent operations
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from multiprocessing import cpu_count
from typing import List, Dict, Any, Optional
import logging

import pandas as pd

from .scraper_config import (
    SUPPORTED_SITES,
    DEFAULT_RESULTS_WANTED,
    DEFAULT_HOURS_OLD,
    DEFAULT_COUNTRY,
    DEFAULT_DATA_DIR,
    MIN_THREAD_COUNT,
    THREAD_RESERVE
)
from .jobspy_wrapper import JobScrapeTask

logger = logging.getLogger(__name__)


class JobSpyScraper:
    """
    Main scraper class that manages multiple JobScrapeTask instances
    and runs them concurrently using a thread pool.
    
    Based on reference implementation from tests/job_scraper.py.
    """
    
    def __init__(
        self,
        job_titles: List[str],
        sites: Optional[List[str]] = None,
        data_dir: str = DEFAULT_DATA_DIR,
        results_wanted: int = DEFAULT_RESULTS_WANTED,
        hours_old: int = DEFAULT_HOURS_OLD,
        country_indeed: str = DEFAULT_COUNTRY,
        max_threads: Optional[int] = None,
        location: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ):
        """
        Initialize the JobSpyScraper.
        
        Args:
            job_titles: List of job titles to search for
            sites: Optional list of sites to scrape. If None, uses all supported sites.
            data_dir: Directory for saving results
            results_wanted: Number of jobs to fetch per search
            hours_old: Maximum age of job postings
            country_indeed: Country for job searches
            max_threads: Optional max thread count. If None, calculated automatically.
        """
        self.job_titles = job_titles
        self.sites = sites or SUPPORTED_SITES.copy()
        self.data_dir = data_dir
        self.results_wanted = results_wanted
        self.hours_old = hours_old
        self.country_indeed = country_indeed
        self._max_threads = max_threads
        self.location = location
        self.progress_callback = progress_callback
        
        # Create data directory
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Create task instances
        self.tasks: List[JobScrapeTask] = [
            JobScrapeTask(
                job_title=title,
                sites=self.sites,
                results_wanted=self.results_wanted,
                hours_old=self.hours_old,
                country_indeed=self.country_indeed,
                location=self.location
            )
            for title in self.job_titles
        ]
        
        # Results storage
        self.all_jobs: List[Dict[str, Any]] = []
        self.completed_tasks: List[JobScrapeTask] = []
    
    @property
    def num_threads(self) -> int:
        """
        Calculate number of threads as CPU count minus reserve, minimum 1.
        
        Returns:
            int: Number of threads to use
        """
        if self._max_threads is not None:
            return max(MIN_THREAD_COUNT, self._max_threads)
        return max(MIN_THREAD_COUNT, cpu_count() - THREAD_RESERVE)
    
    def run(self) -> pd.DataFrame:
        """
        Execute all scraping tasks concurrently using a thread pool.
        
        Returns:
            pd.DataFrame: Combined DataFrame of all scraped jobs
        """
        logger.info(f"Starting JobSpy scraper with {self.num_threads} threads...")
        logger.info(f"Job titles: {', '.join(self.job_titles)}")
        logger.info(f"Sites: {', '.join(self.sites)}")
        
        # Setup progress tracking
        progress_lock = Lock()
        total_jobs_found = 0
        sites_completed = 0
        total_sites_expected = sum(len(task.sites) for task in self.tasks)

        def progress_listener(new_jobs_count):
            nonlocal total_jobs_found, sites_completed
            with progress_lock:
                total_jobs_found += new_jobs_count
                sites_completed += 1
                
                percent = 0
                if total_sites_expected > 0:
                    percent = (sites_completed / total_sites_expected) * 100
                
                if self.progress_callback:
                    # We use a try-except block to prevent callback errors from crashing the thread
                    try:
                        self.progress_callback(percent, total_jobs_found)
                    except Exception as e:
                        logger.error(f"Progress callback error: {e}")

        # Inject callback into tasks
        for task in self.tasks:
            task.progress_callback = progress_listener

        # Use ThreadPoolExecutor to run tasks concurrently
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(task.run): task 
                for task in self.tasks
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    completed_task = future.result()
                    self.completed_tasks.append(completed_task)
                    self.all_jobs.extend(completed_task.jobs_data)
                    logger.info(f"✓ Completed: '{completed_task.job_title}' - {completed_task.total_jobs} jobs found")
                except Exception as e:
                    logger.error(f"✗ Task failed for '{task.job_title}': {e}")
        
        # Compile results
        return self._compile_results()
    
    def _compile_results(self) -> pd.DataFrame:
        """
        Compile all results into a DataFrame.
        
        Returns:
            pd.DataFrame: Combined results
        """
        logger.info("=" * 60)
        logger.info("Overall Job Summary")
        logger.info("=" * 60)
        
        if not self.all_jobs:
            logger.info("No jobs were scraped.")
            return pd.DataFrame()
        
        df = pd.DataFrame(self.all_jobs)
        
        logger.info(f"Total jobs scraped: {len(df)}")
        
        if 'site' in df.columns:
            logger.info(f"Jobs per site:")
            for site, count in df['site'].value_counts().items():
                logger.info(f"  {site}: {count}")
        
        if 'search_term' in df.columns:
            logger.info(f"Jobs per search term:")
            for term, count in df['search_term'].value_counts().items():
                logger.info(f"  {term}: {count}")
        
        return df
    
    def save_results(self, filename: str = "jobs.csv") -> str:
        """
        Save combined results to a CSV file.
        
        Args:
            filename: Name of the output file
        
        Returns:
            str: Path to the saved file
        """
        if not self.all_jobs:
            logger.warning("No jobs to save.")
            return ""
        
        df = pd.DataFrame(self.all_jobs)
        file_path = os.path.join(self.data_dir, filename)
        df.to_csv(file_path, index=False)
        logger.info(f"Saved {len(df)} jobs to {file_path}")
        return file_path
    
    def save_per_task_results(self):
        """Save individual task results to separate CSV files."""
        for task in self.completed_tasks:
            if task.jobs_data:
                task_df = pd.DataFrame(task.jobs_data)
                file_path = os.path.join(self.data_dir, f"{task.sanitized_title}_jobs.csv")
                task_df.to_csv(file_path, index=False)
                logger.info(f"Saved {len(task_df)} jobs for '{task.job_title}' to {file_path}")
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the scraping operation.
        
        Returns:
            Dict containing summary statistics
        """
        return {
            'total_jobs': len(self.all_jobs),
            'tasks_completed': len(self.completed_tasks),
            'tasks_total': len(self.tasks),
            'job_titles': self.job_titles,
            'sites': self.sites,
            'task_summaries': [task.get_summary() for task in self.completed_tasks]
        }


def execute_scraping_tasks(
    job_titles: List[str],
    sites: Optional[List[str]] = None,
    results_wanted: int = DEFAULT_RESULTS_WANTED,
    hours_old: int = DEFAULT_HOURS_OLD,
    location: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to execute scraping tasks and return raw results.
    
    Args:
        job_titles: List of job titles to search for
        sites: Optional list of sites to scrape
        results_wanted: Number of results per search
        hours_old: Maximum age of job postings
    
    Returns:
        List of job dictionaries (raw, not normalized)
    """
    scraper = JobSpyScraper(
        job_titles=job_titles,
        sites=sites,
        results_wanted=results_wanted,
        hours_old=hours_old,
        location=location
    )
    
    scraper.run()
    return scraper.all_jobs
