# Database Architecture Plan - Magnification Job Search Application

## Overview
This document outlines the SQLite database architecture for the Magnification job search application. The database consists of two primary tables: a Jobs table that stores job listings and an Application Status table that tracks the progression of applications through various stages.

---

## Database Design

### Core Principles
- **Single SQLite Database**: All data stored in a single `.db` file for simplicity and portability
- **Relational Structure**: Jobs and Application Status linked via foreign key relationship
- **Conditional Population**: Application Status records only created for jobs where `ignore` is not set to 1
- **Audit Trail**: Date tracking for status transitions enables analysis of application timelines

---

## Table Schemas

### 1. Jobs Table
The primary table storing job listing information retrieved from web scrapers.

**Table Name**: `jobs`

**Columns**:
- `id` (Integer, Primary Key, Auto-increment)
- `title` (String, Not Null) - Job title
- `company` (String, Not Null) - Company name
- `location` (String, Not Null) - Job location
- `description` (String) - Full job description
- `compensation` (String) - Salary/compensation information
- `ignore` (Integer, Default: 0) - Flag to exclude from application tracking (0 = track, 1 = ignore)
- `created_at` (DateTime, Default: Current timestamp) - When the job was added to the database
- `updated_at` (DateTime, Default: Current timestamp) - Last update timestamp

---

### 2. Application Status Table
Tracks the progression of applications through various interview and decision stages.

**Table Name**: `application_statuses`

**Columns**:
- `id` (Integer, Primary Key, Auto-increment)
- `job_id` (Integer, Foreign Key → `jobs.id`) - Reference to the job application
- `status` (String, Not Null) - Current status of the application
- `checked` (Integer, Default: 0) - Checkpoint indicator (0 = not reached, 1 = reached)
- `date_reached` (String, Nullable) - Date when the status was checked/reached (format: YYYY-MM-DD)

**Status Values** (Enumerated):
1. `Applied` - Initial application submitted
2. `Interview 1` - First interview stage
3. `Interview 2` - Second interview stage
4. `Interview 3` - Third interview stage
5. `Post-Interview Rejection` - Rejected after interview rounds
6. `Offer` - Job offer received
7. `Accepted` - Offer accepted by candidate
8. `Rejected` - Application rejected (pre-interview)
9. `Ignored/Ghosted` - No response or dropped communication

**Relationship Rules**:
- Each `job_id` will have exactly 9 application status records (one for each status value)
- Records are only created for jobs where `jobs.ignore` = 0
- Jobs with `jobs.ignore` = 1 will never have corresponding records in this table
- The `checked` field enables tracking which milestones have been reached
- The `date_reached` field stores when a milestone transitioned from 0 to 1

---

## File Organization & Implementation Plan

### Database Models Directory
**Location**: `utils/backend/database/`

This directory will contain all database-related code, organized into separate files for clarity and maintainability.

#### Models File: `models.py`
**Purpose**: SQLAlchemy ORM model definitions

**Contents**:
- Import SQLAlchemy and related dependencies
- Define `Job` model class with all columns specified in the Jobs table schema
- Define `ApplicationStatus` model class with all columns specified in the Application Status table schema
- Establish foreign key relationship between `ApplicationStatus.job_id` and `Job.id`
- Add model methods for common operations (e.g., `get_status_by_name()`, `is_ignored()`)
- Include relationship decorators to enable easy navigation from Job to its ApplicationStatus records

#### Database Initialization File: `init_db.py`
**Purpose**: Database initialization and schema creation

**Contents**:
- Initialize SQLAlchemy connection and engine
- Create database session factory
- Define function to create all tables on first run
- Include database path configuration (should point to `data/magnificiation.db`)
- Handle database migrations if schema changes occur

#### Database Operations File: `operations.py`
**Purpose**: Core CRUD operations and business logic for database interactions

**Contents**:
- Job operations:
  - `add_job()` - Insert new job into the database
  - `update_job()` - Modify existing job record
  - `delete_job()` - Remove job from database
  - `get_job_by_id()` - Retrieve single job
  - `get_all_jobs()` - Retrieve all jobs with filtering options
  - `get_active_jobs()` - Retrieve only jobs where `ignore` = 0
  - `set_job_ignore()` - Toggle ignore flag on a job
  
- Application Status operations:
  - `create_application_status_records()` - Create all 9 status records for a new job (helper function to populate new application statuses)
  - `update_application_status()` - Update a specific status record (mark as checked and record date)
  - `get_application_status_by_job()` - Retrieve all application status records for a job
  - `get_status_by_name()` - Retrieve a specific status record by status name
  - `reset_application_status()` - Clear application status records for a job
  
- Query operations:
  - `get_jobs_by_status()` - Find all jobs at a particular application stage
  - `get_jobs_by_company()` - Find all jobs from a specific company
  - `get_timeline_for_job()` - Get chronological view of all checked statuses for a job
  - `get_job_by_criteria()` - Find job by title, company, and location (for duplicate checking during scraping)
  - `get_jobs_by_ids()` - Retrieve multiple jobs by their IDs (for batch operations during filtering)

#### Database Utilities File: `utils.py`
**Purpose**: Helper functions and utilities for database operations

**Contents**:
- Validation functions:
  - `validate_status()` - Verify status value is one of the 9 allowed values
  - `validate_job_data()` - Validate required fields before insertion
  - `validate_date_format()` - Ensure dates follow YYYY-MM-DD format
  
- Conversion/Formatting functions:
  - `format_job_for_display()` - Format job data for frontend presentation
  - `get_status_list()` - Return list of valid status values
  - `format_date()` - Handle date formatting and conversion
  
- Status management:
  - `get_next_status_index()` - Determine next logical status in sequence
  - `is_status_progression_valid()` - Validate logical application flow

#### Configuration File: `config.py`
**Purpose**: Database configuration and constants

**Contents**:
- Database path configuration (relative to project root: `data/magnificiation.db`)
- Valid status enumeration as constants
- SQLAlchemy configuration options
- Connection string and engine settings

---

## Integration Points

### Job Scraping Integration
**Location**: `utils/backend/scrapers/`

The job scraping system integrates with database operations as follows:
- `scraping_service.py` calls `operations.add_job()` to store each scraped and processed job
- Jobs are inserted with default `ignore=0` flag
- `operations.create_application_status_records()` is automatically invoked for jobs with `ignore=0`
- `job_filter.py` calls `operations.set_job_ignore()` to mark filtered jobs with `ignore=1`
- Jobs marked as ignored do not receive application status records

### Backend Services Integration
**Location**: `utils/backend/services/`

The database operations will be called from service layer files that handle business logic:
- Job scraping workflow orchestration via `scrapers/scraping_service.py`
- Application tracking services will use `operations.update_application_status()` to record status changes

### API Routes Integration
**Location**: `utils/backend/routes/`

Flask routes will expose endpoints that interact with the database:
- `GET /api/jobs` - Retrieve all active jobs
- `POST /api/jobs` - Add new job
- `GET /api/jobs/<id>` - Get specific job and its application timeline
- `PATCH /api/jobs/<id>/status` - Update application status for a job
- `PATCH /api/jobs/<id>/ignore` - Toggle ignore flag

### Frontend Data Consumption
**Location**: `utils/frontend/static/js/`

JavaScript services will make API calls to retrieve and display data:
- Application status tracking displays will consume `/api/jobs/<id>` endpoint
- Job lists will use `/api/jobs` endpoint with filtering
- Status update forms will POST to `/api/jobs/<id>/status` endpoint

---

## Database Storage Location

**Database File Path**: `data/magnificiation.db`

The SQLite database file will be stored in the `data/` directory at the project root. This follows the project structure convention of keeping persistent data separate from application code.

**Access Pattern**:
- All file paths should be relative to the project root
- The application will construct the full path at runtime from configuration
- This enables consistent operation regardless of current working directory

---

## Key Implementation Considerations

### Data Integrity
1. **Foreign Key Constraints**: Enforce referential integrity between Jobs and Application Status tables
2. **Cascade Rules**: When a job is deleted, its associated application status records should be deleted
3. **Required Fields**: Enforce `NOT NULL` constraints on critical fields (title, company, location)

### Application Logic
1. **Atomic Operations**: When a job is added with `ignore=0`, automatically create 9 application status records in a transaction
2. **Status Integrity**: Validate that status values match the predefined enumeration
3. **Date Handling**: Always use YYYY-MM-DD format for date storage and conversion

### Performance Considerations
1. **Indexing**: Add indexes on frequently queried columns:
   - `jobs.company` (for filtering by company)
   - `jobs.ignore` (for active jobs queries)
   - `application_statuses.job_id` (foreign key lookups)
   - `application_statuses.checked` (for milestone tracking)

2. **Query Optimization**: Use relationships and eager loading to minimize database roundtrips

### Future Extensibility
1. **Migration Strategy**: Implement a migration system if schema changes are needed
2. **Backup Mechanism**: Plan for regular database backups to the `data/` directory
3. **Logging**: All database operations should be logged via the project's logging system

---

## Example Workflows

### Adding a New Job (via Scraping Workflow)
1. Scraping system collects jobs from multiple job boards concurrently
2. Data processor deduplicates and cleans job data
3. For each unique job:
   - Transform data to match database schema
   - Call `validate_job_data()` to ensure all required fields are present
   - Call `add_job()` to insert into Jobs table with `ignore=0`
   - `create_application_status_records()` automatically creates 9 status records
4. Job filter evaluates each job against user-defined criteria
5. Jobs failing filters have `set_job_ignore(job_id, 1)` called to mark them as ignored
6. All operations wrapped in transaction for atomicity

### Tracking Application Progress
1. User indicates application was submitted
2. API endpoint receives status update request
3. Call `update_application_status()` with status name, check value (1), and current date
4. Record persists with date_reached populated
5. Frontend queries `get_application_status_by_job()` to display updated timeline

### Filtering Active Applications
1. Frontend requests list of jobs in "Interview 1" stage
2. Call `get_jobs_by_status()` with `"Interview 1"` parameter
3. Query joins Jobs and ApplicationStatus tables with filters
4. Returns all jobs where the Interview 1 status has `checked=1`

---

## Testing Strategy

Test files should be created in `utils/backend/tests/`:
- `test_models.py` - Unit tests for ORM models
- `test_operations.py` - Unit tests for CRUD operations
- `test_utils.py` - Unit tests for utility functions
- `test_integration.py` - Integration tests for complete workflows

Each test should verify:
1. Correct data persistence
2. Foreign key relationships
3. Status validation
4. Date handling
5. Edge cases (ignored jobs, null values, etc.)

---

## Summary

This database architecture provides a clean, maintainable structure for storing job listings and tracking application progress through multiple interview stages. By separating models, operations, and utilities into distinct files within `utils/backend/database/`, the codebase remains organized and testable. The relational design with Jobs and Application Status tables enables comprehensive tracking of the entire application lifecycle while maintaining data integrity and enabling future extensions.
