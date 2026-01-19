# Find Jobs Feature - Implementation Plan

## Overview
This document outlines the comprehensive plan to implement the "Find Jobs" functionality, connecting the front-end button to the scraping system, jobs_config.json, and the database. The feature enables users to configure scraping parameters, execute job searches, and seamlessly integrate results into the application database.

---

## Architecture Overview

### Component Interaction Flow
1. **Front-End**: User clicks "Find Jobs" button → Modal opens with configuration options
2. **Configuration**: User adjusts parameters → Saves to jobs_config.json
3. **Backend API**: Triggers scraping workflow via new Flask route
4. **Scraping Pipeline**: JobSpyWrapper → DataProcessor → Database Operations
5. **Filtering**: JobFilter marks ignored jobs based on criteria
6. **Front-End Update**: Progress tracking → Page refresh on completion

---

## Phase 1: Front-End Modal Implementation

### 1.1 Modal Structure
Create a new modal component that appears when clicking the "Find Jobs" button in the header (currently in `header.html` line 26).

**Required Elements:**
- Modal overlay with backdrop
- Centered modal container with form
- Close button (X icon)
- Save/Go button to trigger scraping

### 1.2 Input Components

#### Hours Old Slider
- **Type**: Range slider with discrete steps
- **Values**: 1 day, 2 day, 3 day, 7 day, 14 day, 1 month (30 days), 2 month (60 days), 3 month (90 days)
- **Display Format**: "X day(s) (Y hours)" - e.g., "7 days (168 hours)"
- **Storage**: Convert to hours for jobs_config.json (1 day = 24 hours, 1 month = 720 hours)
- **Default**: 24 hours (1 day)

#### Site Name Multi-Select
- **Type**: Checkbox group or multi-select dropdown
- **Options**: Load from SUPPORTED_SITES in scraper_config.py:
  - indeed
  - linkedin
  - glassdoor
  - zip_recruiter
  - google
- **Default**: All sites selected
- **Validation**: At least one site must be selected

#### Search Terms (Dynamic List)
- **Type**: Tag/pill input component
- **Functionality**:
  - Input box to add new search term
  - Press Enter or click "Add" to create tag
  - Each tag has an "X" button to remove
  - Display all current search terms as removable pills
- **Storage**: Array of strings in jobs_config.json under "search_terms" key (NEW)
- **Purpose**: These will be used as additional job_title parameters when generating JobScrapeTask objects

#### Job Title Keywords (Dynamic List)
- **Type**: Tag/pill input component (same as Search Terms)
- **Functionality**: Identical to Search Terms
- **Storage**: Array of strings in jobs_config.json under "job_titles" key
- **Purpose**: Filter criteria - jobs must have titles containing these keywords to NOT be ignored
- **Note**: This is the existing "job_titles" field that JobFilter uses

#### Description Keywords (Dynamic List)
- **Type**: Tag/pill input component (same as above)
- **Functionality**: Identical to Search Terms
- **Storage**: Array of strings in jobs_config.json under "description_keywords" key
- **Purpose**: Filter criteria - jobs must have descriptions containing these keywords to NOT be ignored
- **Note**: This is the existing "description_keywords" field that JobFilter uses

### 1.3 Modal Behavior
- **Open**: Click "Find Jobs" button → Modal slides in/fades in
- **Load**: Populate form with current values from jobs_config.json
- **Close**: Click X, click outside modal, or press Escape key
- **Submit**: Click "Go" or "Search" button

### 1.4 JavaScript Files to Modify
- **handlers.js**: Add event handler for "Find Jobs" button click
- **renderers.js**: Add function to render the modal
- **helpers.js**: Add utility functions for:
  - Converting days/months to hours
  - Managing dynamic tag lists
  - Validating form inputs
- **app.js**: Add initialization for modal event listeners

---

## Phase 2: Configuration Management

### 2.1 jobs_config.json Schema Update
Expand the current structure from:
```
{
  "job_titles": [],
  "description_keywords": []
}
```

To include new fields:
```
{
  "search_terms": [],
  "job_titles": [],
  "description_keywords": [],
  "sites": [],
  "hours_old": 24,
  "results_wanted": 20
}
```

**Field Definitions:**
- **search_terms**: Array of strings used as job_title parameters in scraping (what to search FOR)
- **job_titles**: Array of strings used for filtering (what to KEEP based on title)
- **description_keywords**: Array of strings used for filtering (what to KEEP based on description)
- **sites**: Array of site identifiers to scrape (subset of SUPPORTED_SITES)
- **hours_old**: Integer representing hours (24 = 1 day, 168 = 7 days, etc.)
- **results_wanted**: Integer for number of results per search (default 20)

### 2.2 Configuration Saving (Front-End)
Create a new API endpoint that accepts POST requests with the modal form data.

**Endpoint**: `/api/config/save`
**Method**: POST
**Request Body**:
```
{
  "search_terms": ["Software Engineer", "Backend Developer"],
  "job_titles": ["engineer", "developer"],
  "description_keywords": ["python", "flask"],
  "sites": ["indeed", "linkedin"],
  "hours_old": 168,
  "results_wanted": 20
}
```

**Response**:
```
{
  "success": true,
  "message": "Configuration saved successfully"
}
```

### 2.3 Configuration Loading (Front-End)
Create an API endpoint to retrieve current configuration.

**Endpoint**: `/api/config/load`
**Method**: GET
**Response**: Returns the current jobs_config.json contents

### 2.4 Backend Route Implementation
Create new file: `utils/backend/routes/config_routes.py`

**Functions Needed:**
- `save_config(config_data)`: Write validated config to jobs_config.json
- `load_config()`: Read and return jobs_config.json
- `validate_config(config_data)`: Ensure all fields are valid before saving

**Integration**: Register these routes in app.py using Flask blueprints

---

## Phase 3: Backend API for Scraping

### 3.1 Scraping Trigger Endpoint
Create new endpoint to initiate the scraping workflow.

**Endpoint**: `/api/scrape/start`
**Method**: POST
**Request Body**:
```
{
  "use_config": true  // If false, can pass custom parameters
}
```

**Response**:
```
{
  "success": true,
  "job_id": "scrape_123456",  // Unique identifier for this scraping job
  "message": "Scraping started"
}
```

### 3.2 Progress Tracking Endpoint
Create endpoint to check scraping progress in real-time.

**Endpoint**: `/api/scrape/status/<job_id>`
**Method**: GET
**Response**:
```
{
  "status": "in_progress",  // States: pending, in_progress, completed, failed
  "progress": {
    "total_tasks": 10,
    "completed_tasks": 3,
    "current_task": "Scraping LinkedIn for Software Engineer",
    "percent_complete": 30
  },
  "results": {
    "jobs_found": 45,
    "jobs_added": 40,
    "duplicates_removed": 5
  }
}
```

### 3.3 Backend Route Implementation
Create new file: `utils/backend/routes/scrape_routes.py`

**Key Functions:**
- `start_scraping()`: Initiates asynchronous scraping workflow
- `get_scraping_status(job_id)`: Returns current progress
- `cancel_scraping(job_id)`: Allows user to cancel ongoing scrape

**Threading/Async Approach:**
- Use Python threading or background tasks to run scraping without blocking
- Store progress state in memory (dict) or lightweight cache (Redis optional)
- JobSpyScraper already supports concurrent execution via ThreadPoolExecutor

---

## Phase 4: Scraping Workflow Integration

### 4.1 Workflow Orchestration
Leverage existing `scraping_service.py` with modifications to support progress tracking.

**Function**: `execute_full_scraping_workflow()` (already exists, needs enhancement)

**Enhancement Requirements:**
- Accept a progress_callback parameter to report status
- Return structured results including statistics
- Handle errors gracefully with detailed error messages

### 4.2 Data Pipeline Steps

#### Step 1: Load Configuration
- Read jobs_config.json using `task_generator.load_jobs_config()`
- Extract search_terms, sites, hours_old, results_wanted
- Validate that search_terms is not empty

#### Step 2: Generate Scraping Tasks
- Use `task_generator.generate_scraping_tasks()`
- Pass search_terms as job_titles parameter
- Create one JobScrapeTask per search term
- Each task scrapes all specified sites

#### Step 3: Execute Concurrent Scraping
- Use `JobSpyScraper` class from concurrent_scraper.py
- Initialize with configuration parameters
- Call `.run_all_tasks()` method
- Collect all results from each task

#### Step 4: Process and Clean Data
- Use `data_processor.deduplicate_jobs()` to remove duplicates by title+company+location
- Use `data_processor.clean_job_data()` to sanitize fields
- Map jobspy fields to database schema:
  - "title" → "title"
  - "company" → "company"
  - "location" → "location"
  - "job_url" → "link"
  - "description" → "description"
  - "min_amount" + "max_amount" → "compensation" (combined as range string)

#### Step 5: Check Database for Existing Jobs
- Query database using `database.operations.get_all_jobs(include_ignored=True)`
- Create lookup set of (title, company, location) tuples
- Filter out scraped jobs that already exist in database
- This prevents duplicate entries beyond the scraper's deduplication

#### Step 6: Insert New Jobs
- Use `database.operations.add_job()` for each new job
- Set ignore=0 initially for all jobs
- The add_job function automatically creates ApplicationStatus records (9 per job)
- Collect list of newly inserted job IDs

#### Step 7: Apply Filters
- Use `job_filter.filter_and_mark_jobs(job_ids)` with new job IDs
- This function:
  - Loads job_titles and description_keywords from config
  - Checks each job against filter criteria
  - Sets ignore=1 for jobs that DON'T match filters
- Jobs with ignore=1 will not appear in "New Jobs" view

### 4.3 Progress Reporting Structure
During scraping, report progress at these milestones:
- Task generation complete (5%)
- Starting scraping (10%)
- Each task completion (10% + (80% / total_tasks) per task)
- Data processing complete (90%)
- Database insertion complete (95%)
- Filtering complete (100%)

---

## Phase 5: Front-End Progress Tracking

### 5.1 Progress Modal
When user clicks "Go" button:
1. Close configuration modal
2. Open new progress tracking modal
3. Show animated progress bar
4. Display current activity text
5. Show statistics counter (jobs found so far)

### 5.2 Polling Mechanism
- Start polling `/api/scrape/status/<job_id>` every 1-2 seconds
- Update progress bar and status text
- When status becomes "completed", show success message
- Wait 2 seconds, then refresh page to show new jobs

### 5.3 Error Handling
- If status becomes "failed", show error message
- Provide option to retry or close modal
- Log errors for debugging

### 5.4 JavaScript Implementation
- **handlers.js**: Add polling function using setInterval
- **renderers.js**: Add progress modal rendering function
- **helpers.js**: Add utility to parse and format status responses

---

## Phase 6: Database Integration Details

### 6.1 Schema Alignment
The Job model in `models.py` has these fields:
- id (auto-generated)
- title (required)
- company (required)
- location (required)
- link (optional)
- description (optional)
- compensation (optional)
- ignore (default 0)
- created_at (auto-generated)
- updated_at (auto-generated)

JobSpy results provide these fields (from jobspy_wrapper.py):
- title
- company
- location
- job_url (maps to link)
- description
- min_amount, max_amount (combine to compensation)
- currency, interval (use for compensation formatting)
- site (metadata, not stored in Job table)
- search_term (metadata, not stored in Job table)

### 6.2 Compensation Field Construction
Logic in `data_processor.clean_job_data()` already handles this:
- If both min_amount and max_amount exist: "$50,000 - $80,000"
- If only min_amount: "$50,000"
- If only max_amount: "$80,000"
- Append interval if present: "$50,000 - $80,000 per year"

### 6.3 Duplicate Detection Strategy
Two levels of deduplication:

**Level 1 - Within Scraped Data** (before database):
- Function: `data_processor.deduplicate_jobs()`
- Key: (title, company, location) tuple (case-insensitive)
- Removes duplicates within the current scraping session

**Level 2 - Against Existing Database** (before insertion):
- Query all existing jobs from database
- Create set of (title, company, location) tuples from DB
- Filter scraped jobs to exclude any matching existing jobs
- Only insert truly new jobs

### 6.4 Filtering Process
After jobs are inserted with ignore=0:

**Function**: `job_filter.filter_and_mark_jobs(job_ids)`

**Logic** (from job_filter.py):
- For each job, check title against job_titles array (case-insensitive substring match)
- If job_titles is empty, all jobs pass title filter
- For each job, check description against description_keywords array (case-insensitive substring match)
- If description_keywords is empty, all jobs pass keyword filter
- Jobs must pass BOTH filters to be kept (ignore=0)
- Jobs that fail are marked with ignore=1

**Important Note**: The search_terms field is NOT used for filtering - it's only used for scraping. The job_titles field is used for filtering (this is counterintuitive but matches the current codebase structure).

---

## Phase 7: Testing Strategy

### 7.1 Component Testing
- **Modal**: Test opening, closing, form validation
- **Tag Input**: Test adding, removing, edge cases (empty, duplicates)
- **Slider**: Test all discrete values, display formatting
- **Config Save**: Test API endpoint with valid/invalid data
- **Config Load**: Test API endpoint returns correct data

### 7.2 Integration Testing
- **End-to-End Flow**: Fill modal → Save config → Start scrape → Monitor progress → Verify results
- **Error Scenarios**: Invalid config, network failures, empty results
- **Duplicate Handling**: Run scrape twice, verify no duplicates created
- **Filtering**: Configure filters, verify only matching jobs have ignore=0

### 7.3 Database Testing
- **Job Insertion**: Verify all fields mapped correctly
- **ApplicationStatus Creation**: Verify 9 records created per non-ignored job
- **Duplicate Prevention**: Verify existing jobs not re-inserted
- **Filter Application**: Verify ignore flag set correctly

---

## Phase 8: File Structure and Modifications

### New Files to Create
1. `utils/backend/routes/__init__.py` - Package initializer
2. `utils/backend/routes/config_routes.py` - Configuration management endpoints
3. `utils/backend/routes/scrape_routes.py` - Scraping workflow endpoints
4. `utils/frontend/static/js/modal.js` - Modal component logic (optional, can integrate into handlers.js)

### Existing Files to Modify
1. `app.py` - Register new Flask blueprints for routes
2. `config/jobs_config.json` - Expand schema with new fields
3. `utils/frontend/templates/parts/header.html` - Add event handler to Find Jobs button
4. `utils/frontend/static/js/handlers.js` - Add modal open/close, form submit handlers
5. `utils/frontend/static/js/renderers.js` - Add modal rendering functions
6. `utils/frontend/static/js/helpers.js` - Add utility functions
7. `utils/backend/scrapers/task_generator.py` - Update to handle new search_terms field
8. `utils/backend/scrapers/scraping_service.py` - Add progress callback support

### Files to Reference (No Changes Needed)
- `utils/backend/scrapers/jobspy_wrapper.py` - JobScrapeTask class
- `utils/backend/scrapers/concurrent_scraper.py` - JobSpyScraper class
- `utils/backend/scrapers/data_processor.py` - Deduplication and cleaning functions
- `utils/backend/scrapers/job_filter.py` - Filtering logic
- `utils/backend/scrapers/scraper_config.py` - Constants and defaults
- `utils/backend/database/models.py` - Job and ApplicationStatus models
- `utils/backend/database/operations.py` - CRUD operations

---

## Phase 9: Clarifications and Design Decisions

### 9.1 Terminology Clarification
- **search_terms**: What you search FOR on job boards (e.g., "Software Engineer", "Backend Developer")
- **job_titles**: Filter criteria - what job titles to KEEP (e.g., "engineer", "developer")
- **description_keywords**: Filter criteria - what description keywords to KEEP (e.g., "python", "flask")

This distinction is important because:
- search_terms generates the scraping tasks (input to JobScrapeTask)
- job_titles and description_keywords filter the results (input to JobFilter)

### 9.2 Default Values
When modal opens for the first time (empty config):
- hours_old: 24 (1 day)
- sites: All supported sites selected
- results_wanted: 20
- search_terms: Empty array
- job_titles: Empty array (means NO title filtering, keep all)
- description_keywords: Empty array (means NO keyword filtering, keep all)

### 9.3 Validation Rules
- At least one search_term must be provided to start scraping
- At least one site must be selected
- hours_old must be one of the predefined values
- results_wanted should be between 1 and 100
- All keyword arrays can be empty (means no filtering)

### 9.4 Progress Tracking State Management
Use a simple in-memory dictionary on backend:
```
scrape_jobs = {
  "scrape_123456": {
    "status": "in_progress",
    "progress": {...},
    "results": {...},
    "start_time": "...",
    "end_time": None
  }
}
```

For production, consider Redis or database-backed task queue, but in-memory is sufficient for initial implementation.

---

## Phase 10: Implementation Order

### Recommended Sequence
1. **Config Schema Update**: Update jobs_config.json with new fields
2. **Backend Config Routes**: Create config_routes.py with save/load endpoints
3. **Front-End Modal HTML/CSS**: Design and style the modal component
4. **Front-End Modal JavaScript**: Implement modal interactions and form handling
5. **Backend Scrape Routes**: Create scrape_routes.py with start/status endpoints
6. **Scraping Service Enhancement**: Add progress tracking to scraping_service.py
7. **Task Generator Update**: Modify to use search_terms field
8. **Front-End Progress Modal**: Implement progress tracking UI
9. **Integration**: Connect all components via app.py
10. **Testing**: Execute comprehensive testing plan

### Estimated Complexity by Component
- **Easy**: Config schema, config routes, task generator update
- **Medium**: Modal HTML/CSS, modal JavaScript, backend scrape routes
- **Complex**: Progress tracking system, scraping service enhancement, front-end polling

---

## Phase 11: Edge Cases and Error Handling

### Front-End Errors
- Empty search terms: Show validation message, disable Go button
- No sites selected: Show validation message
- Invalid hours_old: Prevent non-standard values
- Network failure on save: Show error toast, allow retry

### Backend Errors
- jobspy library failure: Catch exception, mark task as failed, continue with other tasks
- Database connection failure: Return error status, preserve scraped data temporarily
- Config file write failure: Return error response, don't modify existing config
- Duplicate job detection failure: Log warning, skip insertion, continue

### Scraping Errors
- Site timeout: Handled by jobspy_wrapper.py retry logic (MAX_RETRIES = 3)
- Zero results: Not an error, just continue
- Partial results: Log sites with errors, return partial data

### Progress Tracking Errors
- Client loses connection: Allow re-polling on reconnect
- Backend restart during scrape: Scraping state lost, show error to user
- Long-running scrape: Add timeout (e.g., 10 minutes max)

---

## Phase 12: Future Enhancements (Post-MVP)

### Advanced Features to Consider
1. **Saved Configurations**: Allow users to save/load multiple config presets
2. **Scheduled Scraping**: Run scraping automatically on a schedule (daily, weekly)
3. **Email Notifications**: Alert user when scraping completes
4. **Advanced Filters**: Salary range, job type, remote/on-site, experience level
5. **Export Results**: Download scraped jobs as CSV/JSON before adding to tracker
6. **Scraping History**: Log of all previous scraping sessions with timestamps
7. **Site-Specific Options**: Different parameters per job board site
8. **Regex Filters**: More powerful pattern matching for title/description filtering

### Performance Optimizations
1. **Caching**: Cache jobspy results temporarily to avoid re-scraping
2. **Batch Insertion**: Insert jobs in batches instead of one-by-one
3. **Async Backend**: Use Flask-SocketIO for real-time updates instead of polling
4. **Database Indexing**: Add indexes on title+company+location for faster duplicate checks

---

## Summary

This implementation plan provides a complete roadmap for adding "Find Jobs" functionality to the Job Finder application. The feature integrates seamlessly with existing scraping infrastructure (JobSpyWrapper, JobSpyScraper, DataProcessor, JobFilter) and database operations, while adding a user-friendly configuration interface and real-time progress tracking.

**Key Integration Points:**
- **jobspy_wrapper.py**: Provides JobScrapeTask for individual scraping operations
- **concurrent_scraper.py**: JobSpyScraper orchestrates parallel scraping
- **data_processor.py**: Handles deduplication and data cleaning
- **job_filter.py**: Applies filters and marks ignored jobs
- **scraping_service.py**: Main orchestrator for full workflow
- **database/operations.py**: add_job() inserts jobs and creates ApplicationStatus records
- **jobs_config.json**: Central configuration storage

By following this plan phase-by-phase, you'll build a robust, user-friendly job scraping feature that fits naturally into the existing application architecture.
