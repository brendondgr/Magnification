"""
Core CRUD Operations and Business Logic for Database Interactions.

This module provides all database operations for:
- Job management (add, update, delete, query)
- Application status management (create, update, query)
- Query helpers for filtering and searching
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from .init_db import get_db_context
from .models import Job, ApplicationStatus
from .config import APPLICATION_STATUSES
from .utils import validate_job_data, validate_status, format_date


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


def get_job_by_criteria(title: str, company: str, location: str) -> Optional[Dict[str, Any]]:
    """
    Find job by title, company, and location (for duplicate checking during scraping).
    
    Args:
        title: Job title (exact match)
        company: Company name (exact match)
        location: Job location (exact match)
    
    Returns:
        Dictionary containing job data, or None if not found
    """
    with get_db_context() as db:
        job = db.query(Job).filter(
            Job.title == title,
            Job.company == company,
            Job.location == location
        ).first()
        
        if not job:
            return None
        
        return _job_to_dict(job)


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
        'site': job.site,
        'ignore': job.ignore,
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
