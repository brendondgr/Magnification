"""
Task Generator for Job Scraping Operations.

This module generates scraping tasks from configuration:
- Reads job titles from jobs_config.json
- Creates task objects for each job title
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import logging

from .scraper_config import SUPPORTED_SITES, DEFAULT_RESULTS_WANTED, DEFAULT_HOURS_OLD, DEFAULT_COUNTRY
from ..paths import get_project_root

logger = logging.getLogger(__name__)

# Shared root (same across the main checkout and every git worktree); see utils/backend/paths.py.
CONFIG_DIR = get_project_root() / "config"
JOBS_CONFIG_PATH = CONFIG_DIR / "jobs_config.json"


@dataclass
class ScrapingTask:
    """
    Represents a scraping task for a single job title.
    
    Each task will scrape all specified sites for its job_title.
    """
    job_title: str
    sites: List[str] = field(default_factory=lambda: SUPPORTED_SITES.copy())
    results_wanted: int = DEFAULT_RESULTS_WANTED
    hours_old: int = DEFAULT_HOURS_OLD
    country: str = DEFAULT_COUNTRY
    task_id: Optional[str] = None
    
    def __post_init__(self):
        if self.task_id is None:
            self.task_id = self._generate_task_id()
    
    def _generate_task_id(self) -> str:
        """Generate a unique identifier for this task."""
        sanitized_title = self.job_title.replace(" ", "_").replace("/", "_").lower()
        return f"task_{sanitized_title}"


def load_jobs_config() -> Dict[str, Any]:
    """
    Load job configuration from jobs_config.json.
    
    Returns:
        Dict containing job_titles and description_keywords lists
    
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is malformed
    """
    if not JOBS_CONFIG_PATH.exists():
        logger.error(f"Config file not found: {JOBS_CONFIG_PATH}")
        raise FileNotFoundError(f"Config file not found: {JOBS_CONFIG_PATH}")
    
    with open(JOBS_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Validate expected keys exist
    if 'job_titles' not in config:
        config['job_titles'] = []
    if 'search_terms' not in config:
        config['search_terms'] = []
    if 'description_keywords' not in config:
        config['description_keywords'] = []
    
    logger.info(f"Loaded config with {len(config.get('search_terms', []))} search terms and {len(config['job_titles'])} title filters")
    return config


def generate_scraping_tasks(
    job_titles: Optional[List[str]] = None,
    sites: Optional[List[str]] = None,
    results_wanted: int = DEFAULT_RESULTS_WANTED,
    hours_old: int = DEFAULT_HOURS_OLD,
    country: str = DEFAULT_COUNTRY
) -> List[ScrapingTask]:
    """
    Generate scraping tasks from configuration or provided job titles.
    
    Args:
        job_titles: Optional list of job titles. If None, loads from config.
        sites: Optional list of sites to scrape. If None, uses all supported sites.
        results_wanted: Number of results to fetch per search
        hours_old: Maximum age of job postings in hours
        country: Country for job searches
    
    Returns:
        List of ScrapingTask objects, one per job title
    """
    # Load job titles from config if not provided
    if job_titles is None:
        config = load_jobs_config()
        job_titles = config.get('job_titles', [])
    
    # Use default sites if not provided
    if sites is None:
        sites = SUPPORTED_SITES.copy()
    
    # Validate sites
    valid_sites = [s for s in sites if s in SUPPORTED_SITES]
    if len(valid_sites) < len(sites):
        invalid = set(sites) - set(valid_sites)
        logger.warning(f"Ignoring invalid sites: {invalid}")
    
    if not job_titles:
        logger.warning("No job titles provided. No tasks will be generated.")
        return []
    
    if not valid_sites:
        logger.warning("No valid sites provided. No tasks will be generated.")
        return []
    
    # Create tasks
    tasks = [
        ScrapingTask(
            job_title=title,
            sites=valid_sites,
            results_wanted=results_wanted,
            hours_old=hours_old,
            country=country
        )
        for title in job_titles
    ]
    
    logger.info(f"Generated {len(tasks)} scraping tasks for {len(valid_sites)} sites each")
    return tasks


def get_total_task_count(tasks: List[ScrapingTask]) -> int:
    """
    Calculate total number of individual scraping operations.
    
    Each task may scrape multiple sites, so total = sum of sites per task.
    
    Args:
        tasks: List of ScrapingTask objects
    
    Returns:
        Total number of individual site scrapes
    """
    return sum(len(task.sites) for task in tasks)
