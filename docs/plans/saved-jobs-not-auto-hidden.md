# Plan — Saved Jobs Are Never Auto-Hidden

## 1. Introduction

The user reports that jobs in the **Saved** lane are being hidden even though they never
clicked the hide (ignore) button, and that after un-hiding them a server restart or a new job
search re-hides the same jobs. "Hidden" here means the `jobs.ignore = 1` flag (the card renders
dimmed/red and is dropped from the New Jobs feed). Investigation confirmed the cause: the two
auto-hide filters that set `ignore=1` — `filter_and_mark_jobs()` (runs during a job search) and
`apply_profile_filters()` (runs on Profile Save / Block Company, over **all** jobs) — evaluate a
job purely against the `jobs_config` keyword filter and the profile's block rules. Neither exempts
jobs the user has explicitly **saved**. Because blocking is deliberately one-directional (rules
only ever set `ignore=1`, never clear it), every re-application silently re-hides the saved job
the user just un-hid. These two functions are the only non-user writers of `ignore=1` in the code
base (verified by an exhaustive grep; the third writer is the user's own `PATCH /api/jobs/<id>/ignore`).

The approach is a surgical, protective fix: a **saved job is an explicit user keep and must never
be auto-hidden**. We add a `saved`-guard to both filter functions so they skip any job where
`saved = 1`, add isolated regression tests, and update the docs. Save and Ignore remain
independent flags (the user can still manually hide a saved job); only the *automatic* filters
stop touching saved jobs.

## 2. Gaps & Unanswered Questions

- **Should saving a job also clear an existing `ignore=1`?** *Assumption:* No. `docs/plans/save-jobs.md`
  deliberately keeps Save and Ignore independent, and the manual hide button must keep working on a
  saved job. This fix only stops the *automatic* filters from hiding saved jobs; it does not change
  the manual toggle or auto-clear existing flags. The 9 already-ignored saved jobs in the current DB
  can be un-hidden once by the user and — after this fix — will stay un-hidden.
- **Should the scrape-time filter also skip saved jobs even though new jobs can't be saved yet?**
  *Assumption:* Yes, add the guard there too. A freshly-scraped job always has `saved=0`, so the guard
  is a no-op in practice for new jobs, but adding it keeps both writers consistent and future-proof
  (e.g. if `filter_and_mark_jobs` is ever called over a wider id set).
- **Exact trigger for the "server restart" report.** *Assumption:* App startup itself re-applies no
  filter (verified). The re-hide observed around a restart comes from `apply_profile_filters()` on the
  next Profile Save/Block, or the systemd daily-search-on-boot running `filter_and_mark_jobs`. The
  `saved`-guard covers **every** auto-hide writer, so the fix holds regardless of which one fires.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Protect saved jobs in both auto-hide filters
- **Locations:**
  - `utils/backend/scrapers/job_filter.py` — `filter_and_mark_jobs()`: in the per-job loop, skip
    (never call `set_job_ignore(..., 1)` on) any job where `job.get('saved')` is truthy; count it as
    kept/exempt.
  - `utils/backend/scrapers/job_filter.py` — `apply_profile_filters()`: in the per-job loop, add the
    same `if job.get('saved'): continue` guard alongside the existing `if job.get('ignore'): continue`.
  - Update both function docstrings to state that saved jobs are exempt from auto-hiding.
- **Rationale:** These are the only two functions that set `ignore=1` without user action; guarding
  both there is the single point that fixes the reported bug for every trigger (search, profile save,
  block-company, daily-search-on-boot).
- **Action:** Undergo the verification/tests/validation process for this phase (import check +
  targeted reproduction against an isolated DB). Once validated, commit to GitHub (do **not** push)
  stating: `Saved Jobs Not Auto-Hidden (1/3) Complete: filter_and_mark_jobs and apply_profile_filters now skip saved jobs.`

### Step 2: Regression tests
- **Locations:**
  - `tests/scrapers/test_saved_job_filter_exempt.py` — new test module, using the isolated in-memory
    SQLite engine pattern from `tests/database/test_job_saved.py` (patch `init_db.SessionLocal`; never
    touch the real dev DB). Cases:
    1. `apply_profile_filters()` leaves a `saved=1` job with `ignore=0` even when it matches a profile
       block rule (blocked company / title blocklist / unsatisfied keyword group); a non-saved job that
       matches the same rule is still hidden.
    2. `filter_and_mark_jobs([...])` leaves a `saved=1` job un-hidden even when it fails the
       `jobs_config` keyword filter; a non-saved job failing the same filter is hidden.
- **Rationale:** Locks the fix in and documents the intended contract (saved = protected keep) so a
  future refactor of the filters can't silently reintroduce the bug.
- **Action:** Undergo the verification/tests/validation process for this phase
  (`uv run pytest tests/scrapers tests/database`). Once validated, commit to GitHub (do **not** push)
  stating: `Saved Jobs Not Auto-Hidden (2/3) Complete: added isolated regression tests for the saved-job exemption.`

### Step 3: Documentation
- **Locations:**
  - `docs/data-flow.md` — Status Updates / Scrape Pipeline notes: state that saved jobs are exempt
    from the auto-hide filters.
  - `docs/database.md` — the `saved` column note: add that saved jobs are never auto-hidden by the
    filters (only the manual ignore toggle affects them).
  - `docs/plans/save-jobs.md` — cross-reference this fix under the Save/Ignore-independence note.
  - `docs/checklist.md` — add a "Saved Jobs Not Auto-Hidden — Definition of Done" section.
- **Rationale:** Documentation-maintenance rule: a data-flow/behavior change must update the matching
  docs in the same change.
- **Action:** Undergo the verification/tests/validation process for this phase (full offline test
  subset green + `import app` clean). Once validated, commit to GitHub (do **not** push) stating:
  `Saved Jobs Not Auto-Hidden (3/3) Complete: docs updated and change verified end-to-end.`

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Saved-guard in scrape filter | `filter_and_mark_jobs()` skips saved jobs | `utils/backend/scrapers/job_filter.py` |
| Saved-guard in retroactive filter | `apply_profile_filters()` skips saved jobs | `utils/backend/scrapers/job_filter.py` |
| Regression tests | Isolated in-memory tests proving saved jobs are exempt from both filters | `tests/scrapers/test_saved_job_filter_exempt.py` |
| Doc updates | Data-flow, database, save-jobs plan, checklist reflect the exemption | `docs/data-flow.md`, `docs/database.md`, `docs/plans/save-jobs.md`, `docs/checklist.md` |
