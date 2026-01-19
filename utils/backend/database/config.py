"""
Database Configuration and Constants for Job Finder Job Search Application.

This module contains all database-related configuration including:
- Database path settings
- Status enumeration constants
- SQLAlchemy engine settings
"""

import os
from pathlib import Path

# Get project root directory (3 levels up from this file: database -> backend -> utils -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Database path configuration
DATABASE_DIR = PROJECT_ROOT / "data"
DATABASE_NAME = "magnificiation.db"
DATABASE_PATH = DATABASE_DIR / DATABASE_NAME

# SQLAlchemy connection string
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Ensure data directory exists
DATABASE_DIR.mkdir(parents=True, exist_ok=True)


# Application status enumeration
# These are the valid status values for the application_statuses table
APPLICATION_STATUSES = [
    "Applied",
    "Interview 1",
    "Interview 2", 
    "Interview 3",
    "Post-Interview Rejection",
    "Offer",
    "Accepted",
    "Rejected",
    "Ignored/Ghosted"
]

# Status index mapping for quick lookups
STATUS_INDEX = {status: idx for idx, status in enumerate(APPLICATION_STATUSES)}

# Number of status records to create per job
NUM_STATUSES = len(APPLICATION_STATUSES)


# SQLAlchemy engine configuration
ENGINE_OPTIONS = {
    "echo": False,  # Set to True for SQL query logging
    "pool_pre_ping": True,  # Check connection health before use
}

# Session configuration
SESSION_OPTIONS = {
    "autocommit": False,
    "autoflush": False,
}
