"""
Database package for Magnification Job Search Application.

This package provides database functionality including:
- config: Database configuration and constants
- models: SQLAlchemy ORM models
- init_db: Database initialization and session management
- operations: CRUD operations and queries
- utils: Helper functions and validation
"""

from .config import (
    DATABASE_PATH,
    DATABASE_URL,
    APPLICATION_STATUSES,
    STATUS_INDEX,
)

from .models import (
    Base,
    Job,
    ApplicationStatus,
)

from .init_db import (
    engine,
    SessionLocal,
    init_database,
    get_db_session,
    get_db_context,
    reset_database,
)

from .operations import (
    # Job operations
    add_job,
    update_job,
    delete_job,
    clear_jobs_database,
    get_job_by_id,
    get_all_jobs,
    get_active_jobs,
    set_job_ignore,
    get_jobs_by_ids,
    create_application_status_records,
    # Application status operations
    update_application_status,
    get_application_status_by_job,
    get_status_by_name,
    reset_application_status,
    # Query operations
    get_jobs_by_status,
    get_jobs_by_company,
    get_timeline_for_job,
    get_job_by_criteria,
)

from .utils import (
    validate_status,
    validate_job_data,
    validate_date_format,
    format_date,
    format_job_for_display,
    get_status_list,
    get_next_status,
    is_status_progression_valid,
)

__all__ = [
    # Config
    'DATABASE_PATH',
    'DATABASE_URL', 
    'APPLICATION_STATUSES',
    'STATUS_INDEX',
    # Models
    'Base',
    'Job',
    'ApplicationStatus',
    # Init
    'engine',
    'SessionLocal',
    'init_database',
    'get_db_session',
    'get_db_context',
    'reset_database',
    # Job Operations
    'add_job',
    'update_job',
    'delete_job',
    'clear_jobs_database',
    'get_job_by_id',
    'get_all_jobs',
    'get_active_jobs',
    'set_job_ignore',
    'get_jobs_by_ids',
    'create_application_status_records',
    # Status Operations
    'update_application_status',
    'get_application_status_by_job',
    'get_status_by_name',
    'reset_application_status',
    # Query Operations
    'get_jobs_by_status',
    'get_jobs_by_company',
    'get_timeline_for_job',
    'get_job_by_criteria',
    # Utils
    'validate_status',
    'validate_job_data',
    'validate_date_format',
    'format_date',
    'format_job_for_display',
    'get_status_list',
    'get_next_status',
    'is_status_progression_valid',
]
