"""
Core CRUD Operations and Business Logic for Database Interactions.

This module provides all database operations for:
- Job management (add, update, delete, query)
- Application status management (create, update, query)
- Query helpers for filtering and searching
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Set, Tuple

from sqlalchemy import func, or_, select

from .init_db import get_db_context
from .models import (
    Job, ApplicationStatus, Profile, JobAnalysis, JobEvaluation, GeneratedDocument,
)
from .config import APPLICATION_STATUSES
from .utils import validate_job_data, validate_status, format_date


# Fields the caller may set on a Profile via create/update/upsert.
_PROFILE_FIELDS = (
    'name', 'is_active', 'source_filename', 'resume_text',
    'interests_paragraph', 'skills', 'job_titles', 'keyword_groups',
    'blocked_companies', 'title_blocklist', 'llm_instructions',
)

# Fields the caller may set on a JobAnalysis (job_id/profile_id handled separately).
_ANALYSIS_FIELDS = (
    'embedding', 'embedding_dim', 'extracted_skills',
    'semantic_score', 'bm25_score', 'keyword_score', 'skill_score', 'rag_score',
    'keyword_group_hits', 'skill_match', 'llm_score', 'llm_rationale',
)


# ==================== Job Operations ====================

def add_job(job_data: Dict[str, Any], create_statuses: bool = True) -> int:
    """
    Insert a new job into the database.
    
    Args:
        job_data: Dictionary containing job fields (title, company, location, etc.)
        create_statuses: If True and ignore=0, automatically create application status records
    
    Returns:
        int: The ID of the newly created job
    
    Raises:
        ValueError: If required fields are missing
    """
    validate_job_data(job_data)
    
    with get_db_context() as db:
        job = Job(
            title=job_data['title'],
            company=job_data['company'],
            location=job_data['location'],
            link=job_data.get('link'),
            description=job_data.get('description'),
            compensation=job_data.get('compensation'),
            site=job_data.get('site'),
            ignore=job_data.get('ignore', 0)
        )
        db.add(job)
        db.flush()  # Get the job ID before committing
        
        # Create application status records if job is not ignored
        if create_statuses and job.ignore == 0:
            _create_status_records_for_job(db, job.id)
        
        job_id = job.id
    
    return job_id


def _create_status_records_for_job(db, job_id: int):
    """
    Internal helper to create all 9 application status records for a job.
    
    Args:
        db: Database session
        job_id: ID of the job to create status records for
    """
    for status in APPLICATION_STATUSES:
        status_record = ApplicationStatus(
            job_id=job_id,
            status=status,
            checked=0,
            date_reached=None
        )
        db.add(status_record)


def create_application_status_records(job_id: int) -> bool:
    """
    Create all 9 application status records for a job.
    
    This is called automatically by add_job() for non-ignored jobs,
    but can be called manually if needed.
    
    Args:
        job_id: ID of the job to create status records for
    
    Returns:
        bool: True if records were created successfully
    """
    with get_db_context() as db:
        # Check if job exists and is not ignored
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job with ID {job_id} not found")
        if job.ignore == 1:
            raise ValueError(f"Cannot create status records for ignored job {job_id}")
        
        # Check if records already exist
        existing = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id
        ).count()
        if existing > 0:
            raise ValueError(f"Status records already exist for job {job_id}")
        
        _create_status_records_for_job(db, job_id)
    
    return True


def update_job(job_id: int, updates: Dict[str, Any]) -> bool:
    """
    Modify an existing job record.
    
    Args:
        job_id: ID of the job to update
        updates: Dictionary of field names and new values
    
    Returns:
        bool: True if job was updated successfully
    """
    with get_db_context() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return False
        
        for key, value in updates.items():
            if hasattr(job, key) and key != 'id':
                setattr(job, key, value)
        
        job.updated_at = datetime.utcnow()
    
    return True


def delete_job(job_id: int) -> bool:
    """
    Remove a job from the database.
    
    Note: Associated application status records are automatically deleted
    due to cascade relationship.
    
    Args:
        job_id: ID of the job to delete
    
    Returns:
        bool: True if job was deleted successfully
    """
    with get_db_context() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return False
        
        db.delete(job)

    return True


def clear_jobs_database() -> int:
    """
    Delete every job and all job-scoped data (application statuses and job
    analyses) while leaving profiles intact.

    Bulk ``Query.delete()`` bypasses ORM-level cascades, so the dependent rows
    are removed explicitly in FK-safe order (analyses + evaluations + generated
    documents + statuses before jobs) within a single transaction.

    Returns:
        int: number of Job rows deleted.
    """
    with get_db_context() as db:
        db.query(JobAnalysis).delete(synchronize_session=False)
        db.query(JobEvaluation).delete(synchronize_session=False)
        db.query(GeneratedDocument).delete(synchronize_session=False)
        db.query(ApplicationStatus).delete(synchronize_session=False)
        deleted = db.query(Job).delete(synchronize_session=False)

    return deleted


def get_job_by_id(job_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single job by ID.
    
    Args:
        job_id: ID of the job to retrieve
    
    Returns:
        Dict containing job data, or None if not found
    """
    with get_db_context() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        
        return _job_to_dict(job)


def get_all_jobs(include_ignored: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve all jobs with optional filtering.
    
    Args:
        include_ignored: If True, include jobs with ignore=1
    
    Returns:
        List of dictionaries containing job data
    """
    with get_db_context() as db:
        query = db.query(Job)
        if not include_ignored:
            query = query.filter(Job.ignore == 0)
        
        jobs = query.all()
        return [_job_to_dict(job) for job in jobs]


def get_active_jobs() -> List[Dict[str, Any]]:
    """
    Retrieve only jobs where ignore=0.

    Returns:
        List of dictionaries containing active job data
    """
    return get_all_jobs(include_ignored=False)


def _feed_filter():
    """SQLAlchemy predicate for the jobs the UI needs before "Show Ignored" is clicked.

    An ignored job is still required by the UI when it is saved (Saved lane) or has
    been applied to (Tracker board) — ignoring a company after applying must not make
    the card vanish. Everything else with ignore=1 is withheld until asked for.
    """
    applied = select(ApplicationStatus.job_id).where(ApplicationStatus.checked == 1)
    return or_(Job.ignore == 0, Job.saved == 1, Job.id.in_(applied))


def get_feed_jobs(include_ignored: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve the jobs the front-end feed renders.

    Args:
        include_ignored: If True, return every job. If False (default), withhold
            ignored jobs that are neither saved nor applied to — with a large
            blocklist that is the overwhelming majority of the table.

    Returns:
        List of dictionaries containing job data
    """
    with get_db_context() as db:
        query = db.query(Job)
        if not include_ignored:
            query = query.filter(_feed_filter())
        return [_job_to_dict(job) for job in query.all()]


def get_job_counts() -> Dict[str, int]:
    """
    Cheap counts describing the jobs table, without serializing any rows.

    Returns:
        {'total': all jobs, 'feed': rows get_feed_jobs() returns by default,
         'hidden': rows withheld until "Show Ignored" is toggled on}
    """
    with get_db_context() as db:
        total = db.query(func.count(Job.id)).scalar() or 0
        feed = db.query(func.count(Job.id)).filter(_feed_filter()).scalar() or 0
        return {'total': total, 'feed': feed, 'hidden': total - feed}


def get_feed_filter_facets() -> Dict[str, Any]:
    """
    What the New Jobs **Filter** popup can offer, measured over the jobs it can act on.

    The candidate set is exactly the one ``bulk_filter.apply_bulk_filters`` walks: visible
    (``ignore=0``) and not saved. Aggregating in SQL keeps the popup from having to download
    every job row just to build an industry checkbox list.

    Returns:
        ``{total, industries:[{label, count}], unclassified, scored, unscored, oldest, newest}``
        where ``industries`` is sorted by count descending (real labels only — jobs with no
        label yet are counted in ``unclassified``), ``scored`` counts jobs that have a
        ``rag_score`` to compare a threshold against, and ``oldest``/``newest`` are the
        found-date bounds as ``YYYY-MM-DD`` (or None on an empty feed).
    """
    candidate = (Job.ignore == 0) & (Job.saved == 0)
    with get_db_context() as db:
        total = db.query(func.count(Job.id)).filter(candidate).scalar() or 0

        rows = (db.query(Job.industry, func.count(Job.id))
                  .filter(candidate)
                  .group_by(Job.industry)
                  .all())
        industries, unclassified = [], 0
        for label, count in rows:
            if label and str(label).strip():
                industries.append({'label': str(label).strip(), 'count': count})
            else:
                unclassified += count
        industries.sort(key=lambda item: (-item['count'], item['label']))

        scored = (db.query(func.count(Job.id))
                    .join(JobAnalysis, JobAnalysis.job_id == Job.id)
                    .filter(candidate, JobAnalysis.rag_score.isnot(None))
                    .scalar() or 0)

        oldest, newest = db.query(func.min(Job.created_at), func.max(Job.created_at)) \
                           .filter(candidate).first()

    return {
        'total': total,
        'industries': industries,
        'unclassified': unclassified,
        'scored': scored,
        'unscored': total - scored,
        'oldest': format_date(oldest) if oldest else None,
        'newest': format_date(newest) if newest else None,
    }


def set_job_ignore(job_id: int, ignore_value: int = 1) -> bool:
    """
    Toggle the ignore flag on a job.
    
    Args:
        job_id: ID of the job to update
        ignore_value: 1 to ignore, 0 to track
    
    Returns:
        bool: True if job was updated successfully
    """
    return update_job(job_id, {'ignore': ignore_value})


def set_job_saved(job_id: int, saved_value: int = 1) -> bool:
    """
    Toggle the saved flag on a job.

    Saving a job pins it to the Saved lane: it leaves the New Jobs feed and always
    appears under the Saved tab (independent of the ignore flag and application status).

    Args:
        job_id: ID of the job to update
        saved_value: 1 to save, 0 to unsave

    Returns:
        bool: True if job was updated successfully
    """
    return update_job(job_id, {'saved': saved_value})


def get_jobs_by_ids(job_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Retrieve multiple jobs by their IDs.
    
    Args:
        job_ids: List of job IDs to retrieve
    
    Returns:
        List of dictionaries containing job data
    """
    with get_db_context() as db:
        jobs = db.query(Job).filter(Job.id.in_(job_ids)).all()
        return [_job_to_dict(job) for job in jobs]


# ==================== Application Status Operations ====================

# Maps each application status to the durable, write-once pipeline-date column on ``jobs``
# that records the FIRST time the job reached that pipeline stage. Multiple statuses can feed
# one pipeline event (e.g. any interview round → the first-interview date). "Found" has no
# entry here; the durable ``created_at`` already records it. See ``Job`` model docstring.
PIPELINE_DATE_COLUMN = {
    "Applied": "date_first_applied",
    "Interview 1": "date_first_interview",
    "Interview 2": "date_first_interview",
    "Interview 3": "date_first_interview",
    "Offer": "date_first_offer",
    "Accepted": "date_first_offer",
    "Rejected": "date_first_rejected",
    "Post-Interview Rejection": "date_first_rejected",
    "Ignored/Ghosted": "date_first_ghosted",
}


def _stamp_pipeline_date(job: Optional[Job], status_name: str, date_reached: Optional[str]) -> None:
    """Write-once: record ``date_reached`` on the job's mapped pipeline-date column the first
    time a stage is reached. Never overwrites an existing value and never clears one, so the
    pipeline history survives a card being dragged backward."""
    if job is None or not date_reached:
        return
    column = PIPELINE_DATE_COLUMN.get(status_name)
    if column and getattr(job, column, None) is None:
        setattr(job, column, date_reached)


def update_application_status(job_id: int, status_name: str, checked: int = 1,
                              date_reached: Optional[str] = None) -> bool:
    """
    Update a specific status record for a job.

    Args:
        job_id: ID of the job
        status_name: Name of the status to update
        checked: 1 if milestone reached, 0 if not
        date_reached: Date when milestone was reached (YYYY-MM-DD format)

    Returns:
        bool: True if status was updated successfully

    Side effect: when a milestone is checked, its durable write-once pipeline date is stamped
    on the ``jobs`` row (first occurrence only) so the pipeline history is never lost even if
    the card is later moved backward.
    """
    validate_status(status_name)

    if date_reached is None and checked == 1:
        date_reached = format_date(datetime.utcnow())

    with get_db_context() as db:
        status = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id,
            ApplicationStatus.status == status_name
        ).first()

        if not status:
            return False

        status.checked = checked
        status.date_reached = date_reached

        if checked == 1:
            job = db.query(Job).filter(Job.id == job_id).first()
            _stamp_pipeline_date(job, status_name, date_reached)

    return True


def get_application_status_by_job(job_id: int) -> List[Dict[str, Any]]:
    """
    Retrieve all application status records for a job.
    
    Args:
        job_id: ID of the job
    
    Returns:
        List of dictionaries containing status data
    """
    with get_db_context() as db:
        statuses = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id
        ).all()
        
        return [_status_to_dict(s) for s in statuses]


def get_statuses_for_jobs(job_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    """Retrieve application statuses for many jobs at once, keyed by job_id.

    One query instead of one per job; jobs with no status rows are omitted. IDs are
    chunked to stay under SQLite's bound-parameter ceiling.
    """
    if not job_ids:
        return {}
    grouped: Dict[int, List[Dict[str, Any]]] = {}
    CHUNK = 500
    with get_db_context() as db:
        for i in range(0, len(job_ids), CHUNK):
            chunk = job_ids[i:i + CHUNK]
            rows = db.query(ApplicationStatus).filter(
                ApplicationStatus.job_id.in_(chunk)
            ).all()
            for row in rows:
                grouped.setdefault(row.job_id, []).append(_status_to_dict(row))
    return grouped


def get_status_by_name(job_id: int, status_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific status record by status name.
    
    Args:
        job_id: ID of the job
        status_name: Name of the status to retrieve
    
    Returns:
        Dictionary containing status data, or None if not found
    """
    validate_status(status_name)
    
    with get_db_context() as db:
        status = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id,
            ApplicationStatus.status == status_name
        ).first()
        
        if not status:
            return None
        
        return _status_to_dict(status)


def reset_application_status(job_id: int) -> bool:
    """
    Clear all application status records for a job.
    
    Resets all checked values to 0 and clears date_reached.
    
    Args:
        job_id: ID of the job
    
    Returns:
        bool: True if statuses were reset successfully
    """
    with get_db_context() as db:
        statuses = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id
        ).all()
        
        for status in statuses:
            status.checked = 0
            status.date_reached = None
    
    return True


# ==================== Query Operations ====================

def get_jobs_by_status(status_name: str) -> List[Dict[str, Any]]:
    """
    Find all jobs at a particular application stage.
    
    Args:
        status_name: Name of the status to filter by
    
    Returns:
        List of dictionaries containing job data
    """
    validate_status(status_name)
    
    with get_db_context() as db:
        # Get job IDs that have this status checked
        status_records = db.query(ApplicationStatus).filter(
            ApplicationStatus.status == status_name,
            ApplicationStatus.checked == 1
        ).all()
        
        job_ids = [s.job_id for s in status_records]
        
        if not job_ids:
            return []
        
        jobs = db.query(Job).filter(Job.id.in_(job_ids)).all()
        return [_job_to_dict(job) for job in jobs]


def get_jobs_by_company(company_name: str) -> List[Dict[str, Any]]:
    """
    Find all jobs from a specific company.
    
    Args:
        company_name: Name of the company (case-insensitive partial match)
    
    Returns:
        List of dictionaries containing job data
    """
    with get_db_context() as db:
        jobs = db.query(Job).filter(
            Job.company.ilike(f"%{company_name}%")
        ).all()
        
        return [_job_to_dict(job) for job in jobs]


def get_timeline_for_job(job_id: int) -> List[Dict[str, Any]]:
    """
    Get chronological view of all checked statuses for a job.
    
    Args:
        job_id: ID of the job
    
    Returns:
        List of dictionaries containing checked status data, sorted by date
    """
    with get_db_context() as db:
        statuses = db.query(ApplicationStatus).filter(
            ApplicationStatus.job_id == job_id,
            ApplicationStatus.checked == 1
        ).order_by(ApplicationStatus.date_reached).all()
        
        return [_status_to_dict(s) for s in statuses]


def get_existing_job_keys() -> Set[Tuple[str, str]]:
    """
    Return the (title, company) key of every job in the database, lowercased and
    trimmed, for duplicate checking during scraping.

    One bulk query against the whole table is far cheaper than a per-candidate
    lookup when checking a batch of newly scraped jobs. Location is intentionally
    excluded: the same opening reposted across cities should still be recognized
    as already tracked.

    Returns:
        Set of (title, company) tuples.
    """
    with get_db_context() as db:
        rows = db.query(Job.title, Job.company).all()
        return {(str(t).strip().lower(), str(c).strip().lower()) for t, c in rows}


# ==================== Profile Operations ====================

def create_profile(profile_data: Dict[str, Any]) -> int:
    """
    Create a new profile.

    Args:
        profile_data: dict with any of name, is_active, source_filename, resume_text,
            interests_paragraph, skills, job_titles, keyword_groups.

    Returns:
        int: the new profile's ID.
    """
    with get_db_context() as db:
        profile = Profile()
        for key in _PROFILE_FIELDS:
            if key in profile_data:
                setattr(profile, key, profile_data[key])
        db.add(profile)
        db.flush()
        profile_id = profile.id
        # Keep the single-active invariant if this one was created active.
        if profile.is_active:
            _deactivate_other_profiles(db, profile_id)
    return profile_id


def update_profile(profile_id: int, updates: Dict[str, Any]) -> bool:
    """Update an existing profile's fields. Returns True if the profile existed."""
    with get_db_context() as db:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            return False
        for key in _PROFILE_FIELDS:
            if key in updates:
                setattr(profile, key, updates[key])
        if updates.get('is_active'):
            _deactivate_other_profiles(db, profile_id)
    return True


def get_profile_by_id(profile_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single profile by ID, or None."""
    with get_db_context() as db:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        return _profile_to_dict(profile) if profile else None


def get_active_profile() -> Optional[Dict[str, Any]]:
    """Retrieve the active profile (is_active=1), or None if there is none."""
    with get_db_context() as db:
        profile = db.query(Profile).filter(Profile.is_active == 1).order_by(
            Profile.updated_at.desc()
        ).first()
        return _profile_to_dict(profile) if profile else None


def list_profiles() -> List[Dict[str, Any]]:
    """Retrieve all profiles, newest first."""
    with get_db_context() as db:
        profiles = db.query(Profile).order_by(Profile.created_at.desc()).all()
        return [_profile_to_dict(p) for p in profiles]


def set_active_profile(profile_id: int) -> bool:
    """Mark the given profile active and deactivate all others."""
    with get_db_context() as db:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            return False
        profile.is_active = 1
        _deactivate_other_profiles(db, profile_id)
    return True


def upsert_active_profile(profile_data: Dict[str, Any]) -> int:
    """
    Convenience for the single-profile UI: update the active profile if one exists,
    otherwise create a new active "default" profile. Returns the profile ID.
    """
    active = get_active_profile()
    if active:
        update_profile(active['id'], profile_data)
        return active['id']
    data = dict(profile_data)
    data.setdefault('name', 'default')
    data['is_active'] = 1
    return create_profile(data)


def delete_profile(profile_id: int) -> bool:
    """Delete a profile. Returns True if it existed."""
    with get_db_context() as db:
        profile = db.query(Profile).filter(Profile.id == profile_id).first()
        if not profile:
            return False
        db.delete(profile)
    return True


def _deactivate_other_profiles(db, keep_id: int) -> None:
    """Set is_active=0 on every profile except keep_id (call inside a session)."""
    db.query(Profile).filter(Profile.id != keep_id).update(
        {Profile.is_active: 0}, synchronize_session=False
    )


# ==================== Job Analysis Operations ====================

def save_job_analysis(job_id: int, analysis: Dict[str, Any],
                      profile_id: Optional[int] = None) -> int:
    """
    Upsert the analysis row for a job (1:1 by job_id).

    Args:
        job_id: the job this analysis belongs to.
        analysis: dict with any of the JobAnalysis score/embedding fields.
        profile_id: the profile the scores were computed against (optional).

    Returns:
        int: the JobAnalysis row ID.
    """
    with get_db_context() as db:
        record = db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).first()
        if not record:
            record = JobAnalysis(job_id=job_id)
            db.add(record)
        if profile_id is not None:
            record.profile_id = profile_id
        for key in _ANALYSIS_FIELDS:
            if key in analysis:
                setattr(record, key, analysis[key])
        db.flush()
        analysis_id = record.id
    return analysis_id


def get_analysis_for_job(job_id: int, include_embedding: bool = False) -> Optional[Dict[str, Any]]:
    """Retrieve the analysis for a single job, or None."""
    with get_db_context() as db:
        record = db.query(JobAnalysis).filter(JobAnalysis.job_id == job_id).first()
        return _analysis_to_dict(record, include_embedding) if record else None


def get_analysis_for_jobs(job_ids: List[int],
                          include_embedding: bool = False) -> Dict[int, Dict[str, Any]]:
    """Retrieve analyses for many jobs, keyed by job_id (missing jobs are omitted)."""
    if not job_ids:
        return {}
    with get_db_context() as db:
        records = db.query(JobAnalysis).filter(JobAnalysis.job_id.in_(job_ids)).all()
        return {r.job_id: _analysis_to_dict(r, include_embedding) for r in records}


# ==================== Helper Functions ====================

def _job_to_dict(job: Job) -> Dict[str, Any]:
    """Convert a Job model instance to a dictionary."""
    return {
        'id': job.id,
        'title': job.title,
        'company': job.company,
        'location': job.location,
        'link': job.link,
        'description': job.description,
        'compensation': job.compensation,
        'compensation_checked': bool(job.compensation_checked),
        'industry': job.industry,
        'industry_checked': bool(job.industry_checked),
        'site': job.site,
        'ignore': job.ignore,
        'saved': job.saved,
        # Durable, write-once pipeline history (YYYY-MM-DD; None until the stage is reached).
        # "found" reuses the durable created_at date so the full pipeline is available in one place.
        'date_found': format_date(job.created_at) if job.created_at else None,
        'date_first_applied': job.date_first_applied,
        'date_first_interview': job.date_first_interview,
        'date_first_offer': job.date_first_offer,
        'date_first_rejected': job.date_first_rejected,
        'date_first_ghosted': job.date_first_ghosted,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'updated_at': job.updated_at.isoformat() if job.updated_at else None,
    }


def _status_to_dict(status: ApplicationStatus) -> Dict[str, Any]:
    """Convert an ApplicationStatus model instance to a dictionary."""
    return {
        'id': status.id,
        'job_id': status.job_id,
        'status': status.status,
        'checked': status.checked,
        'date_reached': status.date_reached,
    }


def _profile_to_dict(profile: Profile) -> Dict[str, Any]:
    """Convert a Profile model instance to a dictionary."""
    return {
        'id': profile.id,
        'name': profile.name,
        'is_active': profile.is_active,
        'source_filename': profile.source_filename,
        'resume_text': profile.resume_text,
        'interests_paragraph': profile.interests_paragraph,
        'skills': profile.skills or [],
        'job_titles': profile.job_titles or [],
        'keyword_groups': profile.keyword_groups or [],
        'blocked_companies': profile.blocked_companies or [],
        'title_blocklist': profile.title_blocklist or [],
        'llm_instructions': profile.llm_instructions or '',
        'created_at': profile.created_at.isoformat() if profile.created_at else None,
        'updated_at': profile.updated_at.isoformat() if profile.updated_at else None,
    }


def _analysis_to_dict(analysis: JobAnalysis, include_embedding: bool = False) -> Dict[str, Any]:
    """
    Convert a JobAnalysis model instance to a dictionary.

    The raw ``embedding`` bytes are excluded by default (not JSON-serializable);
    callers that need the vector pass include_embedding=True.
    """
    data = {
        'id': analysis.id,
        'job_id': analysis.job_id,
        'profile_id': analysis.profile_id,
        'embedding_dim': analysis.embedding_dim,
        'has_embedding': analysis.embedding is not None,
        'extracted_skills': analysis.extracted_skills or [],
        'semantic_score': analysis.semantic_score,
        'bm25_score': analysis.bm25_score,
        'keyword_score': analysis.keyword_score,
        'skill_score': analysis.skill_score,
        'rag_score': analysis.rag_score,
        'keyword_group_hits': analysis.keyword_group_hits or {},
        'skill_match': analysis.skill_match or {},
        'llm_score': analysis.llm_score,
        'llm_rationale': analysis.llm_rationale,
        'analyzed_at': analysis.analyzed_at.isoformat() if analysis.analyzed_at else None,
    }
    if include_embedding:
        data['embedding'] = analysis.embedding
    return data
