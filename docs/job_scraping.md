# Job Scraping Pipeline — Magnification

How Magnification pulls listings from job boards, cleans/dedups them, stores them, and hands the
survivors off to enrichment + recommendation scoring. Source of truth: `utils/backend/scrapers/`,
`utils/backend/routes/scrape_routes.py`, `utils/backend/scheduler/`.

For the config/UI side (Find Jobs modal, `jobs_config.json` fields, progress popup) see
`docs/find_jobs.md`. For the end-to-end system diagram see `docs/data-flow.md`. For the DB schema
see `docs/database.md`.

## Entry points

Both entry points call the **same** orchestrator, `scraping_service.execute_full_scraping_workflow`:

- **`POST /api/scrape/start`** (`utils/backend/routes/scrape_routes.py`) — spawns a daemon thread
  running `run_scraping_background`, which calls `execute_full_scraping_workflow` with a
  `progress_callback` that writes into an in-memory `scrape_jobs[job_id]` record (`status`,
  `progress`, an append-only `events` log capped at 200 entries, `results`). The client polls
  `GET /api/scrape/status/<job_id>`.
- **The scheduler's daily runner** (`utils/backend/scheduler/daily_runner.run_daily_search`) — an
  LLM-gated, once-per-day driver invoked out-of-band (e.g. via systemd timer). It re-checks
  `check_llm_ready` up to `max_attempts` times (default 6, 10 min apart) and, the first time the
  LLM answers, calls `execute_full_scraping_workflow(save_to_database=True)` with no
  `progress_callback`. A stamp file (`data/daily_search_state.json`) guarantees at most one real
  run per calendar day; the outcome (`success` / `scrape_error` / `scrape_failed` /
  `llm_unavailable`) is recorded there.

## Module map (`utils/backend/scrapers/`)

| File | Owns |
| --- | --- |
| `scraping_service.py` | The orchestrator — `execute_full_scraping_workflow` (the shared entry point) and `scrape_jobs_quick`/`get_workflow_status` helpers. |
| `task_generator.py` | `load_jobs_config` (reads `config/jobs_config.json`) and the `ScrapingTask` dataclass (unused by the live workflow, which builds tasks via `JobSpyScraper` directly). |
| `jobspy_wrapper.py` | `JobScrapeTask` — runs `jobspy.scrape_jobs` once per site for one job title/country; `build_compensation_string` (the one place min/max/currency/interval become a display string, NaN-safe); `normalize_job_data`. |
| `concurrent_scraper.py` | `JobSpyScraper` — builds one `JobScrapeTask` per (title × country), runs them on a `ThreadPoolExecutor`, aggregates `all_jobs` and per-task summaries. |
| `data_processor.py` | `process_scraped_jobs` — in-batch dedup, field cleaning (incl. compensation), validation, transform to DB-row shape; `get_job_statistics`. |
| `linkedin_scraper.py` | `fetch_descriptions_for_jobs` — fetches LinkedIn's guest-API description HTML for jobs missing one; forced serial (see below). |
| `job_filter.py` | `load_filter_config`, `apply_title_filter`/`apply_keyword_filter` (flat-OR or nested-AND-of-OR), `filter_and_mark_jobs` (DB-backed, also applies profile block rules), `apply_profile_filters` (retroactive re-apply). |
| `profile_filter.py` | Pure predicates for the active profile's block rules: `company_blocked`, `title_blocked`, `keyword_groups_satisfied`, combined in `job_blocked_by_profile`. No I/O. |
| `scraper_config.py` | Constants: `SUPPORTED_SITES` (`indeed`, `linkedin`, `glassdoor`, `zip_recruiter`, `google`), defaults, thread/LinkedIn-fetch tuning, `FIELD_MAPPING`. |
| `scraper_utils.py` | Standalone string helpers (`normalize_location`, `normalize_company_name`, `extract_salary_info`, …) — not wired into the live pipeline. |

## The run, step by step

`execute_full_scraping_workflow` (`scraping_service.py`) resolves `search_terms` / `sites` /
`results_wanted` / `hours_old` / `location` / `countries` / `job_type` from `jobs_config.json`
when the caller doesn't override them, then loops an inner closure,
`_scrape_process_store(iteration, offset)`, once per **iteration**:

1. **`init`** — load config, compute `max_iterations` (`config.max_iterations`, clamped `1..5`;
   forced to `1` when `save_to_database=False`, since only DB mode can dedup across passes).
2. **`scraping`** — `JobSpyScraper(job_titles=search_terms, sites, results_wanted, hours_old,
   countries, job_type, offset)` builds one `JobScrapeTask` per (title × country) and runs them
   concurrently (`ThreadPoolExecutor`, `cpu_count() - THREAD_RESERVE` workers, min 1). Each task
   calls `jobspy.scrape_jobs` once per site sequentially. `offset` advances by `results_wanted`
   each iteration so later passes page deeper into each board's results.
3. **`processing`** — `data_processor.process_scraped_jobs`: `deduplicate_jobs` (in-batch, within
   and across sites, keyed on lowercased `(title, company)` — location is deliberately excluded
   so the same opening re-posted in multiple cities collapses to one row), then per-job
   `clean_job_data` (string trim, `job_url`→`link` fallback) which builds the compensation string
   via `jobspy_wrapper.build_compensation_string` whenever the board didn't already supply one
   (`_finite_amount`/`_clean_token` reject jobspy's NaN salary fields so a board with no pay data
   yields `''`, not `"USDnan - USDnan"`), then `validate_job` (requires title/company/location)
   and `transform_to_db_format`.
4. **DB dedup** — `database.operations.get_existing_job_keys()` returns every `(title, company)`
   already in the table; any processed job matching one is dropped *before* the LinkedIn fetch or
   any LLM call runs, so those expensive steps only ever touch jobs that are both new and pass
   this check.
5. **`fetching_descriptions`** — for the remaining LinkedIn-sourced jobs, `apply_title_filter`
   (against `jobs_config.job_titles`) narrows the set first, then
   `linkedin_scraper.fetch_descriptions_for_jobs` fetches descriptions for that narrowed set only.
6. **`saving`** — if `save_to_database`, each remaining job is inserted via
   `database.operations.add_job`; every job here already passed steps 3–5, so no per-job duplicate
   check happens here.

Steps 2–6 repeat once per iteration (offset increasing each time); job ids from every iteration
accumulate into one list. After the loop:

7. **`filtering`** — `job_filter.filter_and_mark_jobs(job_ids)` runs **once** over every job saved
   across all iterations: applies `jobs_config` title/keyword filters *and* the active profile's
   block rules (`profile_filter.job_blocked_by_profile`), setting `ignore=1` on non-matches.
   Jobs with `saved=1` are always kept (never auto-hidden).
8. **`extracting_enrichment`** then **`analyzing`** — run once, on every non-ignored job from this
   run (see next section). **`completed`** (or **`failed`** on an unhandled exception, with the
   error message in `details.message`).

## Counters / progress semantics

Every iteration builds a **fresh** `JobSpyScraper` whose own tally restarts at zero, so
`execute_full_scraping_workflow` accumulates run-level totals itself in a local `totals` dict
(`raw`, `processed`, `db_dedup_removed`, `stored`) rather than reading them off a single pass.
Both the `progress_callback` payload (`details.jobs_found` / `jobs_saved` / `jobs_kept`) and the
final `results` dict expose these **cumulative, monotonically non-decreasing** run totals; each
corresponding entry in `results['steps']` (e.g. `scraping.raw_jobs_count`,
`processing.processed_count`, `storage.stored_count`) also carries the pass-local figure as
`last_pass_count` (`db_dedup.last_pass_removed` for the dedup step). Multi-iteration runs get an
extra `results['steps']['iterations']` with a `passes` list. This is the exact contract documented
in `docs/api-contract.md`'s Scrape section and `docs/data-flow.md` — this file doesn't restate the
tile-by-tile UI mapping, see those instead.

## LinkedIn description fetch: forced serial

`linkedin_scraper._resolve_fetch_settings` **ignores** its `max_workers` argument and the
`runtime_config.linkedin_workers` setting and always returns a worker count of **1** —
`fetch_descriptions_for_jobs` runs one request at a time regardless of what's configured. Each
request still waits a jittered pre-request delay (`runtime_config.linkedin_delay`, default from
`LINKEDIN_FETCH_DELAY = 0.5`s). This is deliberate: LinkedIn's guest-API endpoint
(`jobs-guest/jobs/api/jobPosting/{id}`) rate-limits aggressively (HTTP 429) under concurrent
requests, so serial + jittered delay trades wall-clock time for reliability. `linkedin_workers` is
kept in `runtime_config` for reference/back-compat but has no effect on this fetch.

## Failure handling + logging

- The scraper modules (`scraping_service.py`, `concurrent_scraper.py`, `jobspy_wrapper.py`,
  `data_processor.py`, `job_filter.py`, `linkedin_scraper.py`) log through Python's standard
  `logging` module (`logging.getLogger(__name__)`); the scheduler (`daily_runner.py`,
  `llm_health.py`) and `recommend/enrichment.py` use `loguru`.
- Per-site scrape failures are caught inside `JobScrapeTask.run`: an exception scraping one site
  for one title is recorded in that task's `errors` dict and logged, `site_counts[site]` is set to
  0, and the loop continues to the next site — one bad board never aborts the run.
- Per-job store failures inside the saving step are caught individually; the job is skipped, the
  error appended to `results['errors']`, and the loop continues.
- The enrichment call (step 7a) and the recommendation-analysis call (step 7b) are each wrapped in
  their own `try/except`: a failure there is logged and appended to `results['errors']` but does
  **not** fail the overall workflow (`results['success']` can still be `True`).
- Only an exception escaping the outer `try` in `execute_full_scraping_workflow` itself produces
  `results['success'] = False` and the `failed` progress stage.

## Post-scrape enrichment (shared with Analyze Matches)

Step 7a calls `recommend.enrichment.enrich_jobs(kept_jobs, get_runtime_config(), on_progress=...)`
— the **same function** `POST /api/recommend/analyze` uses — to extract compensation and industry
from each job's description in one combined LLM pass, gated by
`runtime_config.enable_llm_compensation` / `enable_llm_industry` and a reachable LLM endpoint. Step
7b optionally calls `recommend.service.analyze_jobs(job_ids)` (gated by
`runtime_config.enable_analysis` and an active profile existing) to embed, score, and persist a
`JobAnalysis` row per job. Both are non-fatal to the scrape. See `docs/recommendation.md` for what
each of those steps actually does.

## See also

- `docs/find_jobs.md` — the Find Jobs modal, `jobs_config.json` fields, and the progress-popup UI.
- `docs/data-flow.md` — the full read/write data-flow diagram this pipeline sits inside.
- `docs/database.md` — the `jobs` table schema and related models.
- `docs/api-contract.md` — the `/api/scrape/*` request/response contract.
- `docs/recommendation.md` — enrichment + hybrid RAG scoring that runs after a scrape.
