# Plan — Save Jobs (a "Saved" pipeline lane)

## 1. Introduction

The New Jobs grid currently offers per-job **Block** and **Ignore (Hide)** actions and a
bottom-row **Applied / Details / Open** row. This plan adds a **Save** action directly to the
right of the Hide (Ignore) button on each job card (and in the job detail panel). Saving a job
moves it out of the New Jobs feed into a dedicated **Saved** tab so it is "out of the way," and
saved jobs remain visible in that tab permanently — even after they are marked **Applied** and
tracked on the kanban board.

The approach adds a persisted `saved` flag on the `Job` model (with an idempotent SQLite
migration for the existing shared database), a `PATCH /api/jobs/<id>/save` endpoint, and the
frontend wiring: a `Save` button, a `toggleSave` method, a new **Saved** tab (desktop nav +
mobile nav), a Saved grid, and exclusion of saved jobs from the New Jobs feed.

## 2. Gaps & Unanswered Questions

- **Does Save hide the job from New Jobs?** *Assumption:* Yes — "moves it out of the way" means
  saved jobs are excluded from the New Jobs grid (like applied jobs already are), and only appear
  under the Saved tab.
- **Does Save interact with Ignore?** *Assumption:* They are independent flags. A job can be
  saved and separately ignored; the Saved tab shows saved jobs regardless of the ignore flag
  (the whole point is that saved jobs are always reachable). Save does not clear `ignore`.
  **Follow-up fix (`docs/plans/saved-jobs-not-auto-hidden.md`):** while the flags stay independent,
  the *automatic* filters (`filter_and_mark_jobs`, `apply_profile_filters`) now skip saved jobs, so a
  saved job the user un-hid is never silently re-hidden by a search / profile save / block-company.
- **Do saved+applied jobs stay in the Tracker too?** *Assumption:* Yes. Save is additive and does
  not change application status; a saved job that is later Applied still appears on the Tracker
  kanban **and** in the Saved tab (requirement: "Saved jobs will always appear here, even [if]
  Applied").
- **Column name / default:** `saved` INTEGER DEFAULT 0 (mirrors `ignore`). Non-destructive.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Backend — `saved` column, migration, operation, endpoint, serialization
- **Locations:**
  - `utils/backend/database/models.py` — `Job` class: add `saved = Column(Integer, default=0)`
    + an `idx_jobs_saved` index in `__table_args__`.
  - `utils/backend/database/migrate_job_saved.py` — new idempotent migration (mirrors
    `migrate_profile_llm_instructions.py`) adding `jobs.saved INTEGER DEFAULT 0`.
  - `utils/backend/database/init_db.py` — `_run_migrations()`: import + call the new migration.
  - `utils/backend/database/operations.py` — add `set_job_saved(job_id, saved_value)`
    (mirrors `set_job_ignore`); add `'saved': job.saved` to `_job_to_dict()`.
  - `utils/backend/routes/job_routes.py` — add `PATCH /api/jobs/<int:job_id>/save`
    (mirrors `ignore_job`).
- **Rationale:** The saved state must persist across reloads and across worktrees (shared DB),
  and the frontend needs it in the `/api/jobs` payload and a way to toggle it.
- **Action:** Undergo the verification/tests/validation process for this phase (new isolated
  in-memory test `tests/database/test_job_saved.py`; `import app`). Once validated, commit to
  GitHub stating: Save Jobs (1/3) Complete: Added the `saved` column, migration, `set_job_saved`
  op, serialization, and `PATCH /api/jobs/<id>/save` endpoint.

### Step 2: Frontend — Save button, `toggleSave`, Saved tab + grid, New Jobs exclusion
- **Locations:** `utils/frontend/templates/index.html`
  - `mapDbJob()` — map `saved:j.saved?1:0`.
  - `toggleSave(id)` — new method mirroring `toggleIgnore` (optimistic patch + `PATCH .../save`).
  - `decorate()` — add `onSave` handler + `saveBtn` style (filled/active when saved).
  - New Jobs card template + detail-panel header — add a **Save** button immediately to the right
    of the Ignore button.
  - `renderVals()`:
    - New Jobs `all` filter → also exclude `j.saved`.
    - Add `savedJobs` list (`s.jobs.filter(j=>j.saved && matchSearch)` decorated) + `isSaved`
      flag + count.
    - `navTabs` → add `['saved','Saved']`; `mobTabs` → add a Saved mobile tab.
  - New **Saved** `<section>` (mirrors the New Jobs grid markup) gated on `isSaved`.
- **Rationale:** Delivers the visible feature: a Save control next to Hide, a place saved jobs
  live, and their removal from the New Jobs feed.
- **Action:** Undergo the verification/tests/validation process for this phase (preview tools:
  click Save → card leaves New Jobs, appears under Saved tab, persists after reload; mark that
  job Applied → still in Saved tab). Once validated, commit to GitHub stating: Save Jobs (2/3)
  Complete: Added the Save button, Saved tab + grid, and New-Jobs exclusion.

### Step 3: Docs + merge
- **Locations:** `docs/api-contract.md` (new save endpoint + `saved` field), `docs/database.md`
  (Job `saved` column), `docs/component-map.md` (Saved tab / `toggleSave`), `docs/structure.md`
  (new migration file), `docs/checklist.md` (this feature's Definition of Done), this plan.
- **Rationale:** Docs are the source of truth and must change in the same work.
- **Action:** Undergo the verification/tests/validation process for this phase (full offline
  `pytest`, `import app`). Once validated, commit to GitHub, then merge `save-jobs` → `main`.
  Commit stating: Save Jobs (3/3) Complete: Docs updated + merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| `Job.saved` column + index | Persisted saved flag | `utils/backend/database/models.py` |
| Migration | Idempotent add of `jobs.saved` | `utils/backend/database/migrate_job_saved.py` |
| Migration wiring | Call migration on startup | `utils/backend/database/init_db.py` |
| `set_job_saved` + serialization | Toggle op + expose `saved` | `utils/backend/database/operations.py` |
| Save endpoint | `PATCH /api/jobs/<id>/save` | `utils/backend/routes/job_routes.py` |
| Save button + Saved tab/grid | UI: button, tab, grid, `toggleSave` | `utils/frontend/templates/index.html` |
| Save-flag unit test | In-memory round-trip of `set_job_saved` + serialization | `tests/database/test_job_saved.py` |
| Doc updates | Contract/schema/component/structure/checklist | `docs/*.md` |
