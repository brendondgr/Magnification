"""
Database Initialization and Session Management for Magnification Job Search Application.

This module handles:
- SQLAlchemy engine initialization
- Session factory creation
- Database table creation
"""

from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from .config import DATABASE_URL, ENGINE_OPTIONS, SESSION_OPTIONS
from .models import Base


# Create the database engine
engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)

# Create session factory
SessionLocal = sessionmaker(bind=engine, **SESSION_OPTIONS)


def init_database():
    """
    Initialize the database by creating all tables.

    This function should be called once at application startup.
    Tables are only created if they don't already exist. Lightweight, idempotent
    column migrations for pre-existing databases run afterwards.
    """
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations():
    """Run idempotent additive migrations for databases created before newer columns."""
    from .migrate_profile_blocklists import migrate as migrate_profile_blocklists
    from .migrate_profile_llm_instructions import migrate as migrate_profile_llm_instructions
    from .migrate_profile_favorites import migrate as migrate_profile_favorites
    from .migrate_job_saved import migrate as migrate_job_saved
    from .migrate_job_compensation_checked import migrate as migrate_job_compensation_checked
    from .migrate_job_industry import migrate as migrate_job_industry
    from .migrate_job_pipeline_dates import migrate as migrate_job_pipeline_dates
    from .migrate_clean_bad_compensation import migrate as migrate_clean_bad_compensation
    from .migrate_reset_unlabeled_industry import migrate as migrate_reset_unlabeled_industry
    migrate_profile_blocklists()
    migrate_profile_llm_instructions()
    migrate_profile_favorites()
    migrate_job_saved()
    migrate_job_compensation_checked()
    migrate_job_industry()
    migrate_job_pipeline_dates()
    # Data repair (must run after the columns above exist).
    migrate_clean_bad_compensation()
    migrate_reset_unlabeled_industry()


def get_db_session() -> Session:
    """
    Get a new database session.
    
    Returns:
        Session: A new SQLAlchemy session instance
    
    Note:
        The caller is responsible for closing the session.
        Consider using get_db_context() for automatic cleanup.
    """
    return SessionLocal()


@contextmanager
def get_db_context():
    """
    Context manager for database sessions.
    
    Provides automatic session cleanup and rollback on errors.
    
    Usage:
        with get_db_context() as db:
            jobs = db.query(Job).all()
    
    Yields:
        Session: A SQLAlchemy session that auto-commits on success,
                 rolls back on exception, and always closes.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def drop_all_tables():
    """
    Drop all database tables.
    
    WARNING: This will delete all data! Use only for testing/development.
    """
    Base.metadata.drop_all(bind=engine)


def reset_database():
    """
    Reset the database by dropping and recreating all tables.
    
    WARNING: This will delete all data! Use only for testing/development.
    """
    drop_all_tables()
    init_database()
