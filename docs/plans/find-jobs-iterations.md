# Plan — Find Jobs: Max Results → 100 + Max Iterations (1–5)

## 1. Introduction

Two changes to the **Find Jobs** page. First, raise the **Max Results** slider ceiling from 50 to
**100**. Second, add a **Max Iterations** control (1–5) directly below Max Results: the scraper
re-runs the search up to N times, each pass fetching a **different page** (via a jobspy `offset`
that advances by `results_wanted` per iteration) so the loop surfaces additional unique/various
jobs instead of the same first page.

Both the manual Web-UI search (`/api/scrape/start`) and the automatic daily bot read the same
`config/jobs_config.json`, so wiring `max_iterations` into `execute_full_scraping_workflow`
covers both. Uniqueness across iterations is guaranteed by the existing dedup: in-batch dedup
(step 3) plus the database dedup (step 3.5, `get_existing_job_keys`), which already drops jobs
saved by earlier iterations. Steps 6–7 (keyword filter + compensation + LLM analysis) run **once**
over the accumulated new-job ids, so the LLM-coverage guarantee from `llm-fit-coverage` is
preserved and not multiplied per iteration.

## 2. Gaps & Unanswered Questions

- **How do iterations produce "various" results?** *Assumption*: advance a jobspy `offset` by
  `results_wanted` each pass (page 1, 2, …). Re-running the identical query would mostly return
  the same first page; offset paging is the mechanism that yields new jobs. jobspy's `scrape_jobs`
  accepts `offset`; sites that ignore it degrade gracefully (dedup removes repeats).
- **Non-database mode (`save_to_database=False`).** Cross-iteration dedup relies on the DB.
  *Assumption*: when not saving to the DB, run a single pass (offset 0) regardless of
  `max_iterations`, since there is no store to dedup against.
- **Cost.** More iterations = more scraping (and, for new jobs, more LLM fit calls in step 7).
  *Assumption*: acceptable and user-controlled; default stays `1` (today's behavior).
- **Bounds.** *Assumption*: clamp `max_iterations` to `[1, 5]` server-side; the UI slider is 1–5.

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Worktree + plan doc
- **Locations**: worktree `.claude/worktrees/find-jobs-iterations` (branch
  `find-jobs-iterations`); this file `docs/plans/find-jobs-iterations.md`.
- **Action**: Validate (`import app` clean). Commit (no push): Find Jobs Iterations (1/5)
  Complete: worktree + plan doc.

#### Step 2: Backend — offset paging + iteration loop
- **Locations**:
  - `utils/backend/scrapers/jobspy_wrapper.py` → `JobScrapeTask` gains an `offset` field passed
    into `scrape_args`; module `scrape_and_run`/`JobSpyScraper` threads `offset` through.
  - `utils/backend/scrapers/concurrent_scraper.py` → `JobSpyScraper.__init__` + task construction
    accept/forward `offset`.
  - `utils/backend/scrapers/scraping_service.py` → extract steps 2–5 (scrape → process → db-dedup
    → LinkedIn → save) into a helper `_scrape_process_store(..., offset)` returning the new
    `job_ids`; `execute_full_scraping_workflow` resolves `max_iterations` from config (clamped
    1–5; forced 1 when `save_to_database=False`), loops the helper with `offset = i *
    results_wanted`, accumulates `job_ids`, then runs steps 6–7 once. Iteration progress messages.
  - `utils/backend/routes/config_routes.py` → default config gains `"max_iterations": 1`.
- **Rationale**: One shared workflow drives both manual and bot searches; the loop + offset is the
  core behavior. Steps 6–7 stay single-pass to preserve dedup and the LLM-coverage contract.
- **Action**: Validate — `PYTHONPATH=. uv run pytest tests/recommend tests/database -q` +
  `import app`; add a test that the workflow calls the scraper `max_iterations` times with
  advancing offsets and de-dupes across passes (mocked scraper, offline). Commit (no push): Find
  Jobs Iterations (2/5) Complete: offset paging + max_iterations loop in the scraping workflow.

#### Step 3: Frontend — Max Results 100 + Max Iterations control
- **Locations**: `utils/frontend/templates/index.html`
  - Max Results slider (line ~819): `max="50"` → `max="100"`.
  - Add a **Max Iterations** slider (min 1, max 5, step 1) with a live value label directly below
    Max Results; state `maxIterations` (default 1), `onMaxIter`, prop registration.
  - `configToSave()` includes `max_iterations:s.maxIterations`; `applyConfig`/load reads
    `c.max_iterations`; embedded default runtime/state includes `maxIterations:1`.
- **Rationale**: The Find modal owns these inputs and persists them to `jobs_config.json`, which
  both search paths consume.
- **Action**: Validate — `import app`; verify the served page renders the new slider + `max=100`
  and the config round-trips (`max_iterations` persists). Commit (no push): Find Jobs Iterations
  (3/5) Complete: Max Results ceiling 100 + Max Iterations (1–5) control wired to config.

#### Step 4: Documentation
- **Locations**: `docs/find_jobs.md` (Max Results range + new Max Iterations behavior),
  `docs/job_scraping.md` (iteration/offset paging in the pipeline), `docs/data-flow.md` (scrape
  loop note), `docs/checklist.md` (new DoD section). Cross-check `docs/api-contract.md` config.
- **Action**: Validate — `PYTHONPATH=. uv run pytest tests/docs -q`. Commit (no push): Find Jobs
  Iterations (4/5) Complete: docs for Max Results 100 + Max Iterations.

#### Step 5: Full verification + merge
- **Locations**: repo root; merge `find-jobs-iterations` → `main`; remove worktree.
- **Action**: Validate — offline suite subset + `import app`; check checklist boxes. Commit (no
  push): Find Jobs Iterations (5/5) Complete: verified + merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Plan doc | This plan | `docs/plans/find-jobs-iterations.md` |
| Offset paging | `offset` threaded scraper → jobspy | `utils/backend/scrapers/jobspy_wrapper.py`, `concurrent_scraper.py` |
| Iteration loop | `max_iterations` loop + accumulate job_ids | `utils/backend/scrapers/scraping_service.py` |
| Config default | `max_iterations: 1` | `utils/backend/routes/config_routes.py` |
| UI controls | Max Results 100 + Max Iterations 1–5 | `utils/frontend/templates/index.html` |
| Tests | Iteration count + advancing offset + cross-pass dedup (mocked) | `tests/scrapers/test_iterations.py` |
| Docs | find_jobs / job_scraping / data-flow / checklist | `docs/*.md` |
</content>
