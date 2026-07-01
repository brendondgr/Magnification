# Plan — Clear Database: Two Scoped Options via Slide-Down

## 1. Introduction

The sidebar currently exposes a single **Clear Database** button that resets the
*entire* database (jobs, application statuses, analyses, **and** the résumé
profile) by calling `POST /api/database/clear` → `reset_database()`. Losing the
carefully-built profile every time the user only wants to wipe scraped jobs is a
foot-gun.

This plan replaces that single button with a **Clear Database** control that
slides down to reveal two scoped choices:

- **Full Database (Jobs + Profile)** — the existing full reset.
- **Jobs Database** — clears jobs, application statuses, and job analyses while
  **preserving** the profile(s).

The approach: add a scoped backend operation + accept a `scope` param on the
existing endpoint, then rework the sidebar button into a toggle that reveals the
two options as a slide-down, wiring each to the endpoint with the right scope.

## 2. Gaps & Unanswered Questions

- **"Jobs Database" table set.** Jobs live in `jobs`, with `application_statuses`
  and `job_analyses` cascading off each job. *Assumption*: "Jobs Database" clears
  all three (everything keyed to a job) and leaves `profiles` untouched.
- **Bulk-delete vs ORM cascade.** SQLAlchemy `Query.delete()` bypasses ORM-level
  cascades. *Assumption*: explicitly delete `job_analyses` and
  `application_statuses` before `jobs` in one transaction so no orphans remain,
  rather than relying on ORM cascade.
- **Confirmation copy.** *Assumption*: keep a `window.confirm` per option with
  scope-specific wording; no new modal component.
- **Slide-down mechanism.** The dc-runtime template has no generic dropdown.
  *Assumption*: drive visibility with a new `clearMenuOpen` state flag and a
  `sc-if` block beneath the button (mirrors existing `sc-if` usage).

No complex gaps require human intervention.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Backend — scoped clear operation + endpoint

- **Locations**:
  - `utils/backend/database/operations.py` — new `clear_jobs_database()` that
    deletes `JobAnalysis`, then `ApplicationStatus`, then `Job` rows in one
    session/transaction.
  - `utils/backend/database/__init__.py` — export `clear_jobs_database`.
  - `utils/backend/routes/job_routes.py` — `clear_database()` view reads
    `scope` from the JSON body: `full` (default) → `reset_database()`;
    `jobs` → `clear_jobs_database()`. Unknown scope → 400.
- **Rationale**: The UI needs two behaviors from one action. Keeping the scope
  decision server-side (a named operation) keeps the destructive logic tested and
  reusable, and preserves backward compatibility (missing scope = full reset).
- **Action**: Undergo the verification/tests/validation process for this phase
  (new `tests/database/` test: seed a profile + job + status + analysis, call
  `clear_jobs_database()`, assert jobs/statuses/analyses gone and profile kept;
  `uv run python -c "import app"`). Once validated, commit stating:
  Clear DB Options (1/3) Complete: Added scoped `clear_jobs_database()` op and a
  `scope`-aware `/api/database/clear` endpoint.

### Step 2: Frontend — slide-down with two scoped options

- **Locations**: `utils/frontend/templates/index.html`
  - Sidebar markup (~line 100): replace the single button with a **Clear
    Database** toggle button plus a `sc-if value="{{ clearMenuOpen }}"`
    slide-down containing two buttons — **Full Database (Jobs + Profile)** and
    **Jobs Database**.
  - `constructor` state (~line 888): add `clearMenuOpen:false`.
  - `clearDatabase()` method (~line 1070): accept a `scope` argument, send it in
    the POST body, scope-specific confirm text + toast, close the menu.
  - `render()` return object (~line 1496): expose `clearMenuOpen`,
    `toggleClearMenu`, and `clearDatabase` bound with each scope
    (`clearJobsDb`, `clearFullDb`).
- **Rationale**: A toggle + `sc-if` matches the runtime's existing conditional
  pattern and needs no new component; scoping in the handler keeps one code path.
- **Action**: Undergo the verification/tests/validation process for this phase
  (preview: open app, click Clear Database, confirm the two options slide down;
  exercise "Jobs Database" and confirm the profile survives while jobs clear).
  Once validated, commit stating: Clear DB Options (2/3) Complete: Sidebar Clear
  Database now slides down to Full vs Jobs-only scoped options.

### Step 3: Docs + merge

- **Locations**: `docs/api-contract.md` (scope param on `/api/database/clear`),
  `docs/component-map.md` (sidebar clear control), `docs/data-flow.md` if it
  references the clear flow, `docs/checklist.md` (new Definition of Done block),
  and this plan doc.
- **Rationale**: Docs are the source of truth and must move with the code.
- **Action**: Undergo the verification/tests/validation process for this phase
  (`uv run pytest` offline subset green, `import app` clean). Once validated,
  commit stating: Clear DB Options (3/3) Complete: Documented the scoped clear
  endpoint + UI and merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Scoped clear op | `clear_jobs_database()` deletes job-scoped rows, keeps profiles | `utils/backend/database/operations.py` |
| Export | Re-export of the new op | `utils/backend/database/__init__.py` |
| Endpoint scope | `scope`-aware clear view | `utils/backend/routes/job_routes.py` |
| Slide-down UI | Clear Database toggle + two scoped options | `utils/frontend/templates/index.html` |
| Scoped-clear test | Seed profile+job+status+analysis, clear jobs, assert profile kept | `tests/database/test_clear_jobs.py` |
| Doc updates | api-contract, component-map, data-flow, checklist, this plan | `docs/` |
