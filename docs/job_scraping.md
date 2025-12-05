# Job Scraping Implementation Plan - Magnification

## Overview
This document outlines the implementation plan for integrating the `jobspy` Python library into the Magnification job search application. The scraping system will collect job listings from multiple job boards concurrently, process and deduplicate results, store them in the database, and apply user-defined filters to mark irrelevant jobs as ignored.

---

## Jobspy Integration Strategy

### Supported Job Boards
The system will scrape jobs from the following platforms:
- **LinkedIn**
- **Google Jobs**
- **Indeed**
- **ZipRecruiter**
- **Glassdoor**

### Data Extraction Goals
Each scraping operation will attempt to extract the following information (as available from jobspy):
- Job title
- Company name
- Location
- Full job description
- Compensation/salary information

**Note**: The exact data structure returned by jobspy for each job board requires experimentation and will be documented once implementation begins. Each board may return data in slightly different formats or with varying levels of detail.

---

## Architecture Overview

### High-Level Workflow
1. **Job Search Configuration**: Load job titles from configuration
2. **Task Generation**: Create scraping tasks for each combination of job title × job board
3. **Concurrent Scraping**: Execute all tasks concurrently using a ThreadPool
4. **Data Aggregation**: Collect results from all scraping operations
5. **Deduplication**: Remove duplicate job listings based on identifying criteria
6. **Data Transformation**: Convert jobspy results into database-compatible format
7. **Database Storage**: Insert jobs into the database with default `ignore=0`
8. **Filtering & Classification**: Apply user-defined filters to mark irrelevant jobs
9. **UI Refresh**: Trigger frontend update to display new jobs

---

## File Structure & Implementation

### Directory Organization
All job scraping functionality will reside in:
**Location**: `utils/backend/scrapers/`

This directory will contain multiple focused files to maintain clean separation of concerns:

---

### File: `scraper_config.py`
**Location**: `utils/backend/scrapers/scraper_config.py`

**Purpose**: Centralized configuration for scraping operations

**Contents**:
- Constants for supported job boards (LinkedIn, Google Jobs, Indeed, ZipRecruiter, Glassdoor)
- ThreadPool size configuration (number of concurrent workers)
- Timeout settings for scraping operations
- Retry logic parameters (max retries, backoff strategy)
- Field mapping configuration (map jobspy fields to database columns)
- Error handling settings

**Implementation Details**:
- Define enumeration or list of supported job boards
- Create configuration class or dictionary with scraping parameters
- Include default values that can be overridden via environment variables
- Document expected data structure from jobspy (to be filled in after experimentation)

---

### File: `task_generator.py`
**Location**: `utils/backend/scrapers/task_generator.py`

**Purpose**: Generate scraping tasks from configuration

**Contents**:
- Function to read job titles from `config/jobs_config.json`
- Function to create task objects for each job title × job board combination
- Task data structure definition (contains job title and job board)
- Validation to ensure job titles and boards are valid before task creation

**Implementation Details**:
- `generate_scraping_tasks()` function:
  - Reads job titles from JSON config file
  - Iterates through each job title
  - For each title, creates a task for each of the 5 job boards
  - Returns list of task objects (dictionaries or named tuples)
  - Example: 3 job titles × 5 boards = 15 tasks

**Task Object Structure**:
```
{
    'job_title': str,
    'job_board': str,
    'task_id': str (optional, for tracking)
}
```

---

### File: `jobspy_wrapper.py`
**Location**: `utils/backend/scrapers/jobspy_wrapper.py`

**Purpose**: Wrapper interface for jobspy library operations

**Contents**:
- Abstraction layer over jobspy API calls
- Function to execute single scraping operation for one job title on one board
- Error handling and retry logic for failed scrapes
- Data normalization from jobspy format to internal format
- Logging for each scraping operation

**Implementation Details**:
- `scrape_jobs(job_title, job_board)` function:
  - Accepts job title string and job board identifier
  - Calls appropriate jobspy function/method (implementation pending experimentation)
  - Returns standardized list of job dictionaries
  - Handles exceptions and returns empty list on failure
  - Logs scraping start, completion, and any errors

- Data transformation helper functions:
  - Convert jobspy response to list of dictionaries
  - Extract relevant fields (title, company, location, description, compensation)
  - Handle missing or null values gracefully
  - Normalize data types (strings, handle encoding issues)

**Note**: The exact jobspy API calls and parameters will be determined through experimentation with the library. This file will serve as the single point of integration with jobspy, making future updates easier.

---

### File: `concurrent_scraper.py`
**Location**: `utils/backend/scrapers/concurrent_scraper.py`

**Purpose**: Concurrent execution of scraping tasks using ThreadPool

**Contents**:
- ThreadPool initialization and management
- Task execution coordination
- Result aggregation from all concurrent operations
- Progress tracking (optional)

**Implementation Details**:
- `execute_scraping_tasks(tasks)` function:
  - Accepts list of task objects from task_generator
  - Creates ThreadPoolExecutor with configured number of workers
  - Submits each task to the thread pool
  - Each task calls `jobspy_wrapper.scrape_jobs()`
  - Collects results as they complete
  - Waits for all tasks to finish
  - Returns aggregated list of all scraped jobs

- Concurrency considerations:
  - Thread-safe result collection
  - Handle task failures without blocking other tasks
  - Optional timeout for individual tasks
  - Graceful shutdown of thread pool

- Logging:
  - Log thread pool initialization
  - Track task completion progress
  - Report total jobs scraped from all boards

---

### File: `data_processor.py`
**Location**: `utils/backend/scrapers/data_processor.py`

**Purpose**: Process, clean, and deduplicate scraped job data

**Contents**:
- Deduplication logic to identify and remove duplicate job listings
- Data cleaning functions (remove unnecessary fields, normalize text)
- Validation functions to ensure data meets database requirements
- Transformation from scraped format to database model format

**Implementation Details**:
- `deduplicate_jobs(job_list)` function:
  - Accepts list of job dictionaries from all scraping operations
  - Identifies duplicates based on composite key (title + company + location)
  - May also use fuzzy matching for similar job descriptions
  - Returns list of unique jobs
  - Logs number of duplicates removed

- `clean_job_data(job)` function:
  - Validates required fields (title, company, location)
  - Strips unnecessary whitespace
  - Handles encoding issues
  - Removes or filters out irrelevant data fields
  - Returns cleaned job dictionary

- `transform_to_db_format(job)` function:
  - Converts processed job dictionary to format matching database schema
  - Maps fields to database column names
  - Sets default values (e.g., `ignore=0`, `created_at=current_timestamp`)
  - Returns dictionary ready for database insertion

- `process_scraped_jobs(raw_jobs)` function:
  - Orchestrates the full processing pipeline
  - Calls deduplicate, clean, and transform functions in sequence
  - Returns list of job objects ready for database storage

---

### File: `job_filter.py`
**Location**: `utils/backend/scrapers/job_filter.py`

**Purpose**: Apply user-defined filters to mark irrelevant jobs

**Contents**:
- Load filter criteria from `config/jobs_config.json`
- Matching logic for job titles and description keywords
- Function to mark jobs as ignored based on filter results
- Update database to set `ignore=1` for filtered jobs

**Implementation Details**:
- `load_filter_config()` function:
  - Reads `config/jobs_config.json`
  - Extracts `job_titles` and `description_keywords` lists
  - Returns filter configuration object

- `apply_filters(job, filter_config)` function:
  - Accepts a single job and filter configuration
  - Checks if job title matches any in the filter list (case-insensitive)
  - Checks if any description keywords appear in job description
  - Returns boolean: True if job should be kept, False if should be ignored

- `filter_and_mark_jobs(job_ids)` function:
  - Accepts list of job IDs that were just inserted into database
  - Loads filter configuration
  - For each job ID:
    - Retrieves job from database
    - Applies filters
    - If job fails filters, updates database to set `ignore=1`
  - Logs number of jobs marked as ignored
  - Interacts with database operations from `utils/backend/database/operations.py`

**Filter Matching Strategy**:
- **Job Title Filter**: If `job_titles` list is not empty, only jobs with titles matching the list are kept
- **Description Keyword Filter**: If `description_keywords` list is not empty, only jobs containing at least one keyword are kept
- If both lists are empty, no filtering is applied (all jobs remain `ignore=0`)

---

### File: `scraping_service.py`
**Location**: `utils/backend/scrapers/scraping_service.py`

**Purpose**: Main orchestration service for the entire scraping workflow

**Contents**:
- High-level function that coordinates all scraping operations
- Calls task generation, concurrent scraping, processing, storage, and filtering
- Error handling and logging for the entire workflow
- Integration point with database operations
- Trigger for frontend refresh

**Implementation Details**:
- `execute_full_scraping_workflow()` function:
  - **Step 1**: Generate scraping tasks
    - Calls `task_generator.generate_scraping_tasks()`
    - Logs number of tasks generated
  
  - **Step 2**: Execute concurrent scraping
    - Calls `concurrent_scraper.execute_scraping_tasks(tasks)`
    - Logs total jobs scraped
  
  - **Step 3**: Process and deduplicate data
    - Calls `data_processor.process_scraped_jobs(raw_jobs)`
    - Logs number of unique jobs after processing
  
  - **Step 4**: Store jobs in database
    - Imports `add_job()` from `utils/backend/database/operations.py`
    - Iterates through processed jobs and inserts each into database
    - Collects list of newly inserted job IDs
    - Logs number of jobs stored
  
  - **Step 5**: Apply filters and mark ignored jobs
    - Calls `job_filter.filter_and_mark_jobs(job_ids)`
    - Logs number of jobs marked as ignored
  
  - **Step 6**: Trigger frontend refresh
    - Calls appropriate service to notify frontend of new data
    - Details TBD based on frontend implementation
  
  - Returns summary statistics (total scraped, stored, ignored)

- Error handling:
  - Wrap entire workflow in try-except
  - Log errors at each step
  - Continue processing even if some tasks fail
  - Return partial results if available

- `schedule_scraping_job()` function (optional):
  - If automated scraping is desired
  - Sets up periodic execution of scraping workflow
  - Uses scheduler library (APScheduler or similar)

---

### File: `scraper_utils.py`
**Location**: `utils/backend/scrapers/scraper_utils.py`

**Purpose**: Helper utilities for scraping operations

**Contents**:
- Common utility functions used across scraping modules
- String normalization and cleaning functions
- Date/time formatting utilities
- Validation helpers

**Implementation Details**:
- `normalize_location(location)` function:
  - Standardizes location strings (e.g., "New York, NY" vs "New York City")
  - Handles remote work indicators
  
- `normalize_company_name(company)` function:
  - Removes legal entity suffixes (Inc., LLC, etc.)
  - Standardizes capitalization
  
- `extract_salary_info(text)` function:
  - Parses salary information from various formats
  - Returns standardized compensation string
  
- `calculate_task_id(job_title, job_board)` function:
  - Generates unique identifier for a scraping task
  - Used for tracking and logging

---

## Database Integration

### Interaction with Database Layer
The scraping system will interact with the database operations defined in `utils/backend/database/operations.py`.

**Primary Database Operations Used**:

1. **Adding Jobs**:
   - Function: `add_job(job_data)` from `operations.py`
   - Called for each processed job in the storage step
   - Automatically sets `created_at` and `updated_at` timestamps
   - Returns job ID for newly inserted record

2. **Creating Application Status Records**:
   - Function: `create_application_status_records(job_id)` from `operations.py`
   - Automatically called by `add_job()` for jobs with `ignore=0`
   - Creates all 9 application status tracking records
   - Ensures jobs are ready for application tracking

3. **Updating Ignore Flag**:
   - Function: `set_job_ignore(job_id, ignore_value)` from `operations.py`
   - Called by `job_filter.py` for jobs that fail filters
   - Sets `ignore=1` for filtered jobs
   - Note: Application status records are not created for ignored jobs

4. **Checking for Duplicates** (optional enhancement):
   - Function: `get_job_by_criteria(title, company, location)` from `operations.py`
   - Could be used to check database for existing jobs before insertion
   - Helps prevent database-level duplicates
   - May be implemented as future enhancement

**Transaction Handling**:
- All database operations should be wrapped in transactions
- If any step fails during job insertion, rollback to maintain consistency
- Ensures that a job and its application status records are created atomically

---

## Configuration File Integration

### jobs_config.json Structure
**Location**: `config/jobs_config.json`

**Current Structure**:
```json
{
    "job_titles": [],
    "description_keywords": []
}
```

**Usage in Scraping**:

1. **Job Titles Array**:
   - Used by `task_generator.py` to create scraping tasks
   - Each title becomes a search query across all job boards
   - If empty, no scraping tasks are generated (fail safely)

2. **Description Keywords Array**:
   - Used by `job_filter.py` to filter scraped jobs
   - Jobs containing these keywords in description are kept
   - Jobs without matching keywords are marked as `ignore=1`
   - If empty, no keyword filtering is applied

**Future Enhancements**:
- Add location filters
- Add salary range filters
- Add company blacklist/whitelist
- Add job posting age filters (e.g., only jobs posted within last 7 days)

---

## Logging Strategy

All scraping operations will utilize the project's logging system located in `utils/libs/logger/`.

**Log Categories**:

1. **Task Generation Logs**:
   - Number of job titles loaded from config
   - Number of tasks generated
   - List of job boards being queried

2. **Scraping Execution Logs**:
   - Start of each scraping task (job title + board)
   - Completion of each task with result count
   - Errors encountered during scraping
   - ThreadPool initialization and shutdown

3. **Processing Logs**:
   - Total jobs collected before deduplication
   - Number of duplicates removed
   - Number of jobs passing validation
   - Data transformation issues

4. **Storage Logs**:
   - Number of jobs inserted into database
   - Any database insertion errors
   - Transaction commit/rollback events

5. **Filtering Logs**:
   - Filter configuration loaded
   - Number of jobs evaluated
   - Number of jobs marked as ignored
   - Specific reasons for filtering (title/keyword mismatch)

6. **Workflow Summary Logs**:
   - Total execution time
   - Final statistics (scraped, stored, ignored, active)

**Log Levels**:
- **INFO**: Normal operation progress
- **WARNING**: Recoverable issues (e.g., scraping failure for one board)
- **ERROR**: Serious issues that prevent part of workflow
- **DEBUG**: Detailed information for troubleshooting (e.g., individual job data)

---

## Error Handling Strategy

### Failure Scenarios & Recovery

1. **Jobspy API Failures**:
   - **Issue**: Jobspy library throws exception or returns error
   - **Handling**: Catch exception in `jobspy_wrapper.py`, log error, return empty list
   - **Recovery**: Other scraping tasks continue unaffected

2. **Network Timeouts**:
   - **Issue**: Job board not responding or slow response
   - **Handling**: Set timeout in jobspy calls, catch timeout exception
   - **Recovery**: Optionally retry with exponential backoff

3. **Invalid Configuration**:
   - **Issue**: `jobs_config.json` is empty or malformed
   - **Handling**: Validate configuration in `task_generator.py`
   - **Recovery**: Log error and exit workflow gracefully

4. **Database Connection Issues**:
   - **Issue**: Cannot connect to database during storage step
   - **Handling**: Catch database exceptions, log error
   - **Recovery**: Optionally queue jobs for retry or manual inspection

5. **Duplicate Key Violations**:
   - **Issue**: Job already exists in database (unlikely after deduplication)
   - **Handling**: Catch unique constraint violation, skip insertion
   - **Recovery**: Continue with next job

6. **Thread Pool Exhaustion**:
   - **Issue**: Too many concurrent tasks causing resource issues
   - **Handling**: Limit thread pool size in configuration
   - **Recovery**: Tasks queue and execute as threads become available

**General Principles**:
- Fail gracefully for individual tasks without stopping entire workflow
- Log all errors with sufficient context for debugging
- Return partial results when some operations succeed
- Never crash the entire application due to scraping failures

---

## Frontend Integration

### Refresh Mechanism
After the scraping workflow completes, the frontend Jobs Board must be notified to display new jobs.

**Implementation Approach** (details TBD based on frontend architecture):

1. **Service Layer Notification**:
   - File: `utils/backend/services/job_service.py`
   - Function: `notify_jobs_updated()`
   - Sends signal or event to frontend components

2. **Possible Refresh Methods**:
   - **WebSocket**: Push notification to connected clients
   - **Server-Sent Events (SSE)**: Stream update to frontend
   - **Polling**: Frontend periodically checks for updates
   - **Timestamp Endpoint**: Frontend checks last update timestamp

3. **Frontend Action**:
   - Receives notification
   - Calls API endpoint to fetch updated job list
   - Re-renders job board with new data
   - Optionally highlights newly added jobs

**API Endpoint for Job Retrieval**:
- Endpoint: `GET /api/jobs`
- Implemented in: `utils/backend/routes/` (specific route file TBD)
- Returns list of active jobs (`ignore=0`)
- Supports filtering, pagination, sorting

---

## Testing Strategy

### Test Files
**Location**: `utils/backend/tests/`

**Test Coverage**:

1. **test_task_generator.py**:
   - Test task generation with various configurations
   - Test with empty job titles list
   - Test with multiple job titles
   - Verify correct number of tasks created (titles × boards)

2. **test_jobspy_wrapper.py**:
   - Mock jobspy library responses
   - Test successful scraping
   - Test error handling for failed scrapes
   - Test data transformation functions
   - **Note**: Requires experimentation with jobspy first

3. **test_concurrent_scraper.py**:
   - Test ThreadPool execution
   - Test result aggregation
   - Test handling of task failures
   - Test thread safety of result collection

4. **test_data_processor.py**:
   - Test deduplication with identical jobs
   - Test deduplication with similar jobs
   - Test data cleaning functions
   - Test transformation to database format
   - Test validation of required fields

5. **test_job_filter.py**:
   - Test filter loading from config
   - Test job title matching
   - Test description keyword matching
   - Test combined filters
   - Test with empty filter lists

6. **test_scraping_service.py**:
   - Integration test for full workflow
   - Mock all external dependencies (jobspy, database)
   - Verify correct sequence of operations
   - Test error propagation and handling

**Testing Approach**:
- Use `pytest` as testing framework
- Mock external dependencies (jobspy, database)
- Use fixtures for test data
- Aim for high coverage of business logic
- Integration tests for end-to-end workflow

---

## Implementation Phases

### Phase 1: Experimentation & Research
- Install and explore jobspy library
- Test scraping from each job board individually
- Document data structures returned by jobspy
- Identify field mappings to database schema
- Determine API parameters and options

### Phase 2: Core Scraping Infrastructure
- Implement `scraper_config.py`
- Implement `jobspy_wrapper.py` with basic scraping function
- Implement `task_generator.py`
- Write unit tests for these modules

### Phase 3: Concurrent Execution
- Implement `concurrent_scraper.py` with ThreadPool
- Test concurrent execution with mock tasks
- Add logging and error handling
- Write unit tests

### Phase 4: Data Processing
- Implement `data_processor.py` with deduplication logic
- Implement data cleaning and transformation
- Test with sample scraped data
- Write unit tests

### Phase 5: Database Integration
- Integrate with `utils/backend/database/operations.py`
- Implement job storage logic
- Test database insertion and transaction handling
- Verify application status record creation

### Phase 6: Filtering System
- Implement `job_filter.py`
- Test filter logic with various configurations
- Integrate with database to update ignore flags
- Write unit tests

### Phase 7: Orchestration & Service Layer
- Implement `scraping_service.py` to coordinate workflow
- Add comprehensive logging throughout
- Test end-to-end scraping workflow
- Write integration tests

### Phase 8: Frontend Integration
- Implement refresh mechanism
- Test frontend notification and data retrieval
- End-to-end testing with full application

### Phase 9: Optimization & Polish
- Performance tuning (thread pool size, timeouts)
- Enhanced error handling
- Additional logging
- Documentation updates based on implementation learnings

---

## Future Enhancements

### Potential Improvements
1. **Incremental Scraping**:
   - Track last scrape timestamp per job board
   - Only fetch new jobs since last scrape
   - Reduces redundant data collection

2. **Smart Deduplication**:
   - Use fuzzy matching algorithms for job descriptions
   - Detect similar jobs from different boards
   - Machine learning-based duplicate detection

3. **Rate Limiting**:
   - Respect job board rate limits
   - Implement backoff strategies
   - Distribute requests over time

4. **Job Board Priority**:
   - Configure which boards to scrape first
   - Prioritize boards with higher quality results
   - Dynamic board selection based on past success rates

5. **Advanced Filtering**:
   - Machine learning-based job relevance scoring
   - Use LLM integration (from `utils/libs/llm/`) to analyze job fit
   - Multi-criteria filtering (location, salary, company rating)

6. **Scheduled Scraping**:
   - Automated periodic scraping (daily, weekly)
   - Configurable schedule via admin interface
   - Email/notification when new relevant jobs are found

7. **Scraping Analytics**:
   - Track scraping success rates per board
   - Monitor data quality metrics
   - Visualize scraping history and trends

8. **Job Update Detection**:
   - Detect when existing jobs are updated (description, salary changes)
   - Track job removal (no longer posted)
   - Maintain historical job data

---

## Summary

This job scraping implementation plan provides a modular, scalable architecture for integrating the jobspy library into the Magnification application. By separating concerns across multiple focused files within `utils/backend/scrapers/`, the system maintains clean code organization and testability.

**Key Architecture Decisions**:
- **Concurrent execution** via ThreadPool for efficient multi-board scraping
- **Modular design** with single-responsibility files
- **Robust error handling** to ensure partial failures don't crash the workflow
- **Clean integration** with existing database operations
- **Flexible filtering** system based on user configuration
- **Comprehensive logging** for monitoring and debugging

The phased implementation approach allows for iterative development, starting with experimentation to understand jobspy's behavior, followed by systematic construction of each component, and culminating in full integration with the database and frontend systems.

Once the jobspy library has been explored and its data structures are understood, the detailed implementation of each file can proceed with confidence, filling in the specific API calls and data transformations required for each job board.
