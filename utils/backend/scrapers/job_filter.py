"""
Job Filter for Magnification Job Search Application.

This module applies user-defined filters to mark irrelevant jobs:
- Load filter criteria from jobs_config.json
- Filter by job title matching
- Filter by description keyword matching
- Update database to set ignore=1 for filtered jobs
"""

import json
from typing import List, Dict, Any, Optional
import logging

from .scraper_config import SUPPORTED_SITES
from ..paths import get_project_root

logger = logging.getLogger(__name__)

# Shared root (same across the main checkout and every git worktree); see utils/backend/paths.py.
CONFIG_DIR = get_project_root() / "config"
JOBS_CONFIG_PATH = CONFIG_DIR / "jobs_config.json"


def load_filter_config() -> Dict[str, Any]:
    """
    Load filter configuration from jobs_config.json.
    
    Returns:
        Dict containing job_titles and description_keywords lists
    """
    if not JOBS_CONFIG_PATH.exists():
        logger.warning(f"Filter config not found: {JOBS_CONFIG_PATH}")
        return {'job_titles': [], 'description_keywords': []}
    
    try:
        with open(JOBS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return {
            'job_titles': config.get('job_titles', []),
            'description_keywords': config.get('description_keywords', [])
        }
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing filter config: {e}")
        return {'job_titles': [], 'description_keywords': []}


def apply_title_filter(job: Dict[str, Any], allowed_titles: List[Any]) -> bool:
    """
    Check if job title matches allowed criteria.
    Supports flat list (OR) or nested list (AND groups of OR terms).
    
    Args:
        job: Job dictionary
        allowed_titles: List of allowed job title patterns (str) or List of Lists (str)
    
    Returns:
        bool: True if job should be KEPT
    """
    if not allowed_titles:
        return True
    
    job_title = str(job.get('title', '')).lower()
    
    # Check structure: matches if ALL groups are satisfied
    # If flat list, treat as single group [allowed_titles]
    
    # Detect if nested
    is_nested = allowed_titles and isinstance(allowed_titles[0], list)
    
    groups = allowed_titles if is_nested else [allowed_titles]
    
    for group in groups:
        # For this group (AND condition), we need at least one match (OR condition)
        # Empty group? If user configured an empty group, does it match everything or nothing?
        # Usually empty filter implies no restriction, but here explicit empty group might mean "match nothing" 
        # or it might be an artifact. Let's assume empty group is ignored (matches).
        if not group:
            continue
            
        group_match = False
        for pattern in group:
            if str(pattern).lower() in job_title:
                group_match = True
                break
        
        if not group_match:
            return False # Failed one of the AND groups
            
    return True


def apply_keyword_filter(job: Dict[str, Any], keywords: List[Any]) -> bool:
    """
    Check if job description matches required keywords.
    Supports flat list (OR) or nested list (AND groups of OR terms).
    
    Args:
        job: Job dictionary
        keywords: List of keywords (str) or List of Lists (str)
    
    Returns:
        bool: True if job should be KEPT
    """
    if not keywords:
        return True
    
    description = str(job.get('description', '')).lower()
    
    is_nested = keywords and isinstance(keywords[0], list)
    groups = keywords if is_nested else [keywords]
    
    for group in groups:
        if not group:
            continue
            
        group_match = False
        for keyword in group:
            if str(keyword).lower() in description:
                group_match = True
                break
        
        if not group_match:
            return False
            
    return True


def apply_filters(job: Dict[str, Any], filter_config: Optional[Dict[str, Any]] = None) -> bool:
    """
    Apply all filters to determine if a job should be kept or ignored.
    
    Args:
        job: Job dictionary
        filter_config: Optional filter configuration. If None, loads from config file.
    
    Returns:
        bool: True if job should be KEPT, False if should be ignored
    """
    if filter_config is None:
        filter_config = load_filter_config()
    
    allowed_titles = filter_config.get('job_titles', [])
    keywords = filter_config.get('description_keywords', [])
    
    # If no filters are configured, keep all jobs
    if not allowed_titles and not keywords:
        return True
    
    # Apply title filter (if configured)
    if allowed_titles and not apply_title_filter(job, allowed_titles):
        return False
    
    # Apply keyword filter (if configured)
    if keywords and not apply_keyword_filter(job, keywords):
        return False
    
    return True


def filter_jobs(jobs: List[Dict[str, Any]], filter_config: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Filter a list of jobs into kept and ignored categories.
    
    Args:
        jobs: List of job dictionaries
        filter_config: Optional filter configuration
    
    Returns:
        Dict with 'kept' and 'ignored' lists of jobs
    """
    if filter_config is None:
        filter_config = load_filter_config()
    
    kept = []
    ignored = []
    
    for job in jobs:
        if apply_filters(job, filter_config):
            kept.append(job)
        else:
            ignored.append(job)
    
    logger.info(f"Filtering complete: {len(kept)} kept, {len(ignored)} ignored")
    return {'kept': kept, 'ignored': ignored}


def filter_and_mark_jobs(job_ids: List[int]) -> Dict[str, Any]:
    """
    Apply filters to existing jobs in database and mark ignored ones.

    This function retrieves jobs from the database, applies the per-search
    ``jobs_config`` title/description keyword filter AND the active profile's
    block rules (blocked companies, title blocklist, scoped keyword groups),
    and sets ignore=1 for jobs that don't pass either.

    Jobs the user has explicitly **saved** (``saved=1``) are an intentional keep
    and are never auto-hidden here — they are counted as kept and skipped.

    Args:
        job_ids: List of job IDs to filter

    Returns:
        Dict containing statistics about the filtering operation
    """
    # Import here to avoid circular imports
    from ..database.operations import get_jobs_by_ids, set_job_ignore, get_active_profile
    from . import profile_filter

    filter_config = load_filter_config()
    profile = get_active_profile()

    # Get jobs from database
    jobs = get_jobs_by_ids(job_ids)

    kept_count = 0
    ignored_count = 0

    for job in jobs:
        if job.get('saved'):
            # Saved is an explicit user keep — never auto-hide it.
            kept_count += 1
            continue
        keep = apply_filters(job, filter_config) and not profile_filter.job_blocked_by_profile(job, profile)
        if keep:
            kept_count += 1
        else:
            # Mark as ignored in database
            set_job_ignore(job['id'], 1)
            ignored_count += 1

    logger.info(f"Filter and mark complete: {kept_count} kept, {ignored_count} ignored")

    return {
        'total_processed': len(jobs),
        'kept': kept_count,
        'ignored': ignored_count,
        'filter_config': filter_config
    }


def apply_profile_filters(job_ids: Optional[List[int]] = None,
                          profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Retroactively hide jobs that the active profile's block rules match.

    Used when the user blocks a company / edits their blocklists so the change takes effect on
    the current feed, not just the next scrape. One-directional: only sets ignore=1 on currently
    visible jobs; never un-hides. Pass ``job_ids`` to scope to specific jobs, else all jobs.

    Jobs the user has explicitly **saved** (``saved=1``) are an intentional keep and are never
    auto-hidden here, even when they match a block rule — so a saved job the user un-hid stays
    visible across profile saves / block-company actions.

    Returns a summary dict with the number of jobs newly blocked.
    """
    from ..database.operations import (
        get_jobs_by_ids, get_all_jobs, set_job_ignore, get_active_profile,
    )
    from . import profile_filter

    profile = profile or get_active_profile()
    if not profile:
        return {'blocked': 0, 'checked': 0}

    jobs = get_jobs_by_ids(job_ids) if job_ids else get_all_jobs(include_ignored=True)

    blocked = 0
    for job in jobs:
        if job.get('saved'):
            continue  # explicit user keep — never auto-hide it
        if job.get('ignore'):
            continue  # already hidden — leave it
        if profile_filter.job_blocked_by_profile(job, profile):
            set_job_ignore(job['id'], 1)
            blocked += 1

    logger.info(f"Applied profile block rules: {blocked} newly hidden of {len(jobs)} checked")
    return {'blocked': blocked, 'checked': len(jobs)}


def apply_all_filters(job_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Re-apply **both** rule sets to the jobs currently visible in the feed.

    Backs the New Jobs "Filter" button: the per-search ``jobs_config`` title/description keyword
    filter *and* the active profile's block rules (blocked companies, title blocklist, scoped
    keyword groups) are evaluated together, so a user who tightened either one sees it take effect
    without re-scraping.

    Scope and semantics match the other on-demand helper (``apply_profile_filters``):

      * only currently visible jobs are considered — already-hidden rows are left alone;
      * jobs the user explicitly **saved** (``saved=1``) are an intentional keep and are never
        auto-hidden;
      * one-directional — a job is only ever hidden, never un-hidden.

    Args:
        job_ids: Optional scope. When omitted, every visible job is checked.

    Returns:
        Dict with ``checked`` (jobs evaluated) and ``hidden`` (newly hidden).
    """
    from ..database.operations import (
        get_jobs_by_ids, get_all_jobs, set_job_ignore, get_active_profile,
    )
    from . import profile_filter

    filter_config = load_filter_config()
    profile = get_active_profile()

    jobs = get_jobs_by_ids(job_ids) if job_ids else get_all_jobs(include_ignored=False)

    checked = 0
    hidden = 0
    for job in jobs:
        if job.get('saved'):
            continue  # explicit user keep — never auto-hide it
        if job.get('ignore'):
            continue  # already hidden — leave it
        checked += 1
        keep = apply_filters(job, filter_config) and not profile_filter.job_blocked_by_profile(job, profile)
        if not keep:
            set_job_ignore(job['id'], 1)
            hidden += 1

    logger.info(f"Applied all filters on demand: {hidden} newly hidden of {checked} checked")
    return {'checked': checked, 'hidden': hidden}


def get_filter_summary(filter_config: Optional[Dict[str, Any]] = None) -> str:
    """
    Get a human-readable summary of the current filter configuration.
    
    Args:
        filter_config: Optional filter configuration
    
    Returns:
        String describing the active filters
    """
    if filter_config is None:
        filter_config = load_filter_config()
    
    titles = filter_config.get('job_titles', [])
    keywords = filter_config.get('description_keywords', [])
    
    parts = []
    
    if titles:
        parts.append(f"Title patterns: {', '.join(titles)}")
    else:
        parts.append("No title filter")
    
    if keywords:
        parts.append(f"Keywords: {', '.join(keywords)}")
    else:
        parts.append("No keyword filter")
    
    return " | ".join(parts)
