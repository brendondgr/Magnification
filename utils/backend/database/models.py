"""
SQLAlchemy ORM Model Definitions for Magnification Job Search Application.

This module defines the database models:
- Job: Stores job listing information
- ApplicationStatus: Tracks application progression through interview stages
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Job(Base):
    """
    Job model representing a job listing from web scrapers.
    
    Attributes:
        id: Primary key
        title: Job title (required)
        company: Company name (required)
        location: Job location (required)
        link: URL to the job posting
        description: Full job description
        compensation: Salary/compensation information
        site: The job board site where the job was found
        ignore: Flag to exclude from application tracking (0=track, 1=ignore)
        created_at: When the job was added to the database
        updated_at: Last update timestamp
    """
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    link = Column(String(2048), nullable=True)
    description = Column(Text, nullable=True)
    compensation = Column(String(255), nullable=True)
    site = Column(String(50), nullable=True)
    ignore = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to application statuses - cascade delete when job is deleted
    application_statuses = relationship(
        "ApplicationStatus",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    # Indexes for frequently queried columns
    __table_args__ = (
        Index('idx_jobs_company', 'company'),
        Index('idx_jobs_ignore', 'ignore'),
    )
    
    def is_ignored(self) -> bool:
        """Check if job is marked as ignored."""
        return self.ignore == 1
    
    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}')>"


class ApplicationStatus(Base):
    """
    ApplicationStatus model tracking the progression of job applications.
    
    Each job (where ignore=0) will have 9 ApplicationStatus records,
    one for each stage of the application process.
    
    Attributes:
        id: Primary key
        job_id: Foreign key to jobs table
        status: Current status name (one of the 9 predefined values)
        checked: Checkpoint indicator (0=not reached, 1=reached)
        date_reached: Date when status was checked/reached (YYYY-MM-DD format)
    """
    __tablename__ = 'application_statuses'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    status = Column(String(50), nullable=False)
    checked = Column(Integer, default=0)
    date_reached = Column(String(10), nullable=True)  # YYYY-MM-DD format
    
    # Relationship back to job
    job = relationship("Job", back_populates="application_statuses")
    
    # Indexes for frequently queried columns
    __table_args__ = (
        Index('idx_app_status_job_id', 'job_id'),
        Index('idx_app_status_checked', 'checked'),
    )
    
    def is_checked(self) -> bool:
        """Check if this status milestone has been reached."""
        return self.checked == 1
    
    def __repr__(self):
        return f"<ApplicationStatus(id={self.id}, job_id={self.job_id}, status='{self.status}', checked={self.checked})>"
