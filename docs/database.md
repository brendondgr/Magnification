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
- `link` (String) - URL to the job posting
- `description` (String) - Full job description
- `compensation` (String) - Salary/compensation information
- `compensation_checked` (Integer, Default: 0) - Records that LLM compensation extraction has already run for this job (0 = not yet, 1 = checked). Set once the LLM has been asked — whether or not it found pay — so jobs whose descriptions state no pay are not re-queried on every "Analyze Matches"/scrape run (`recommend.compensation.needs_compensation_recovery`); a forced reanalyze re-attempts regardless. Added to pre-existing databases by the idempotent `migrate_job_compensation_checked` migration.
- `industry` (String(64)) - The job's detected industry/genre, one of a fixed taxonomy (Tech, Health, Finance, Business, Industrial, Science, Education, Government, Retail, Media, Legal, Energy, Other; source of truth: `recommend.compensation.INDUSTRIES`), extracted from the description by the LLM in the **same enrichment pass** as compensation. `NULL` until classified.
- `industry_checked` (Integer, Default: 0) - Records that LLM industry classification has already run for this job (0 = not yet, 1 = checked). Mirrors `compensation_checked` (`recommend.compensation.needs_industry_recovery`); a forced reanalyze re-attempts regardless. Added to pre-existing databases by the idempotent `migrate_job_industry` migration.
- `ignore` (Integer, Default: 0) - Flag to exclude from application tracking (0 = track, 1 = ignore)
- `saved` (Integer, Default: 0) - Flag pinning the job to the **Saved** lane (0 = not saved, 1 = saved). Saved jobs are hidden from the New Jobs feed and always shown under the Saved tab, even after being marked Applied. Independent of `ignore` — but a saved job is an explicit user keep and is therefore **never auto-hidden** by the scrape/profile filters (`job_filter.filter_and_mark_jobs` and `job_filter.apply_profile_filters` skip any job with `saved=1`); only the manual hide button (`PATCH /api/jobs/<id>/ignore`) can set `ignore=1` on a saved job. Indexed (`idx_jobs_saved`). Added to pre-existing databases by the idempotent `migrate_job_saved` migration.
- `date_first_applied` / `date_first_interview` / `date_first_offer` / `date_first_rejected` / `date_first_ghosted` (String, Nullable, YYYY-MM-DD) - **Durable, write-once pipeline timestamps** recording the *first* time the job reached each stage. Stamped by `update_application_status` the first time the mapped `application_statuses` milestone is checked (Applied → applied; any Interview 1-3 → interview; Offer/Accepted → offer; Rejected/Post-Interview Rejection → rejected; Ignored/Ghosted → ghosted) and **never cleared or overwritten** afterwards — so the pipeline history survives a card being dragged backward, unlike the mutable `application_statuses.date_reached`. "Found" is not a column here; the durable `created_at` already records it (exposed as `date_found`). Added to pre-existing databases by the idempotent `migrate_job_pipeline_dates` migration, which also **backfills** first-dates from existing checked status history.
- `created_at` (DateTime, Default: Current timestamp) - When the job was added to the database (also the durable "found" date, serialized as `date_found`)
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

---

### 3. Profiles Table (recommendation system)
Stores user profiles built from a resume; the active profile is the comparison target for RAG + LLM scoring.

**Table Name**: `profiles`

**Columns**:
- `id` (Integer, PK, Auto-increment)
- `name` (String(120), Not Null, default `"default"`) - human label
- `is_active` (Integer, default 0) - 1 for the single active profile used for scoring
- `source_filename` (String(512), Nullable) - original resume filename (pdf/tex/md)
- `resume_text` (Text, Nullable) - extracted plain text of the resume
- `interests_paragraph` (Text, Nullable) - open-body interests paragraph (LLM matching)
- `skills` (JSON, Nullable) - list of skill strings
- `job_titles` (JSON, Nullable) - list of search-query job titles
- `keyword_groups` (JSON, Nullable) - list of `{label, terms:[...]}`; **AND across groups, OR within a group** (same convention as `utils/backend/scrapers/job_filter`)
- `created_at` / `updated_at` (DateTime)

**Invariant**: at most one profile has `is_active=1` (enforced by `set_active_profile` / `upsert_active_profile` in `operations.py`). Index: `idx_profiles_active`.

---

### 4. Job Analyses Table (recommendation system)
Per-job recommendation artifacts, **1:1 with `jobs`**. The embedding is profile-independent and computed once on retrieval; the scores are computed against `profile_id` and overwritten on re-analysis.

**Table Name**: `job_analyses`

**Columns**:
- `id` (Integer, PK, Auto-increment)
- `job_id` (Integer, FK → `jobs.id` ON DELETE CASCADE, **unique** → 1:1)
- `profile_id` (Integer, FK → `profiles.id` ON DELETE SET NULL, Nullable)
- `embedding` (LargeBinary, Nullable) - packed float32 bytes of the bge-small-en-v1.5 vector
- `embedding_dim` (Integer, Nullable) - 384 for bge-small-en-v1.5
- `extracted_skills` (JSON, Nullable) - skills found in the job description
- `semantic_score` / `bm25_score` / `keyword_score` / `skill_score` (Float, Nullable) - component signals
- `rag_score` (Float, Nullable) - combined hybrid relevance (0..1)
- `keyword_group_hits` (JSON, Nullable) - `{group_label: [matched terms]}`
- `skill_match` (JSON, Nullable) - `{matched:[...], missing:[...]}`
- `llm_score` (Float, Nullable) - optional LLM verdict (0..100)
- `llm_rationale` (Text, Nullable) - optional LLM explanation
- `analyzed_at` (DateTime)

**Relationship Rules**:
- Deleting a `Job` cascades to its `JobAnalysis` (ORM-level cascade via the `Job.analysis` backref).
- Indexes: `idx_job_analyses_job_id` (unique), `idx_job_analyses_profile_id`, `idx_job_analyses_rag_score`.

> Both tables are created by `Base.metadata.create_all()` in `init_db.init_database()`; no destructive migration is required since they are new tables.
- The `checked` field enables tracking which milestones have been reached
- The `date_reached` field stores when a milestone transitioned from 0 to 1

---

### 5–8. Retired tables (Uploaded Documents / Behavioral / Writing-Style / Templates)

The `uploaded_documents`, `behavioral_profiles`, `writing_style_profiles`, and `document_templates`
tables — and the upload-ingestion pipeline that fed them — were **retired** in favor of a single
editable **Document Guidance** document (plain text in `config/document_guidance.json`, not a DB
table). Their ORM models and CRUD were removed, so fresh databases no longer create these tables; a
pre-existing database keeps them as harmless orphans (no destructive `DROP` migration was run). See
`docs/plans/documents-sidebar-simplify.md` and `utils/backend/agents/document_guidance.py`.

---

### 9. Job Evaluations Table (agentic documents system)
Per-job application-fit verdict — **1:1 with `jobs`**, upserted by `job_id`. Distinct from Job Analyses (§4): Job Analyses is the RAG/embedding relevance signal, Job Evaluations is the agentic fit verdict (emphasize/gaps/risks/talking points).

**Table Name**: `job_evaluations`

**Columns**:
- `id` (Integer, PK, Auto-increment)
- `job_id` (Integer, FK → `jobs.id` ON DELETE CASCADE, **unique** → 1:1)
- `profile_id` (Integer, FK → `profiles.id` ON DELETE SET NULL, Nullable)
- `verdict` (String, Nullable)
- `fit_score` (Float, Nullable)
- `emphasize` (JSON, Nullable) - list of points to emphasize
- `gaps` (JSON, Nullable) - list of gap strings
- `risks` (Text, Nullable)
- `talking_points` (JSON, Nullable) - list of talking-point strings
- `created_at` / `updated_at` (DateTime)

**Relationship Rules**:
- Deleting a `Job` cascades to its `JobEvaluation` (same FK-cascade pattern as `JobAnalysis`, §4).
- One evaluation per job: `job_evaluations` upserts by `job_id` rather than accumulating rows.

---

### 10. Generated Documents Table (agentic documents system)
Job-linked storage for generated cover letters/résumés. Currently a **dormant substrate**: the table and its CRUD exist, but the generation graphs that populate it are a later, deferred phase.

**Table Name**: `generated_documents`

**Columns**:
- `id` (Integer, PK, Auto-increment)
- `job_id` (Integer, FK → `jobs.id` ON DELETE CASCADE)
- `kind` (String) - `cover_letter` or `resume`
- `content` (Text, Nullable)
- `format` (String, Nullable)
- `status` (String, default `draft`) - `draft` or `approved`
- `match_before` / `match_after` (Float, Nullable) - fit score before/after generation
- `revision` (Integer, default 0)
- `checkpoint_state` (JSON, Nullable) - in-progress generation state
- `created_at` / `updated_at` (DateTime)

**Relationship Rules**:
- Deleting a `Job` cascades to its `GeneratedDocument` rows (same FK-cascade pattern as `JobAnalysis`, §4).
- Not unique on `job_id`: multiple documents/revisions per job are expected (different `kind`, or successive `revision`s).

---

> Tables 5-10 are created by `Base.metadata.create_all()` in `init_db.init_database()` — same as Job Analyses (§4), no migration is required since they are new tables.

> `clear_jobs_database()` now also bulk-deletes `job_evaluations` and `generated_documents` alongside `application_statuses`/`job_analyses` (bulk delete bypasses the ORM cascade, so job-linked agentic-documents rows must be purged explicitly).

> These six tables are the data foundation for the agentic documents system described in [`docs/plans/agentic-documents-system.md`](plans/agentic-documents-system.md) (build order §8.1-§8.2): document ingestion and profile/template storage are implemented now, while the cover-letter/résumé generation graphs remain a deferred phase.

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
