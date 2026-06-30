# Plan: Wire the New "Job Finder" Design Into the Flask Backend

## 1. Introduction

The product owner has provided a finished Claude design-tool export (`Job Finder.html` + `support.js`) that is to **completely replace** the current modular Flask/Tailwind frontend. The export is a single self-contained **dc-runtime React component** (`class Component extends DCLogic`) whose template + logic live inline. Today it renders entirely from **mock data**; the goal of this plan is to make it work **end-to-end** against the existing, already-built Flask API (`/api/jobs`, `/api/scrape/*`, `/api/config/*`, `/api/database/clear`).

The approach is to keep the design's markup and visual system **exactly as exported**, vendor the `dc-runtime` (`support.js`) as a local static asset, and **rewrite only the data layer** of the `Component` class so every piece of state is sourced from / persisted to the real API. A status/column model mismatch between the design (4 columns, 6 timeline stages) and the database (9 application statuses) is reconciled with explicit mapping helpers. The LLM server/model-management UI from the old frontend is dropped (per owner decision); only the design's "LLM refinement" checkbox is kept and folded into the saved scrape config. React/Babel/fonts load from CDN (per owner decision).

## 2. Gaps & Unanswered Questions

- **LLM management UI** — *Resolved (owner): drop entirely.* The old `llm-dropdown` / model-management panel is removed from the UI. `llm_routes.py` stays on the server but is no longer called by the frontend.
- **CDN vs offline** — *Resolved (owner): CDN is fine.* `dc-runtime` loads React 18 UMD + Babel from unpkg; fonts from Google Fonts. Requires internet at page load.
- **Status ↔ Column mapping** — *Assumption.* DB `APPLICATION_STATUSES` = [Applied, Interview 1, Interview 2, Interview 3, Post-Interview Rejection, Offer, Accepted, Rejected, Ignored/Ghosted]. Map to the design's 4 tracker columns as: **archived** = Rejected/Post-Interview Rejection/Ignored/Ghosted checked; **offers** = Offer/Accepted checked; **interviewing** = any Interview N checked; **applied** = Applied checked and nothing further. A job is "new" (New Jobs grid) when `Applied.checked === 0`. The detail-panel timeline is driven by the **9 real DB statuses** (not the design's 6 mock names) so each toggle persists via `PATCH /api/jobs/<id>/status`.
- **Find-modal config mapping** — *Assumption.* `terms`→`search_terms`; `location`→`location`; `maxResults`→`results_wanted`; `ageIndex`(0–5)→`hours_old` via [24,72,168,336,504,720]; `sites` object → lowercase config list (Indeed→indeed, LinkedIn→linkedin, Glassdoor→glassdoor, ZipRecruiter→zip_recruiter, Google→google); `keywordGroups`→`description_keywords`; `useLLM`→`use_llm`. Other existing config keys (e.g. `job_titles`) are preserved by loading the full config first and overriding only modal-controlled keys.
- **`created_at` → "days ago"** — *Assumption.* `daysAgo` is derived from the job's `created_at` ISO timestamp; the design's site badge uses the DB `site` value (title-cased for display).
- **Drag-drop persistence** — *Assumption.* Moving a card to a column issues the minimal set of `PATCH .../status` calls to reach that column's representative state (e.g. → interviewing ensures Applied + Interview 1 checked), mirroring the old `handlers.js drop()` semantics.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Establish Worktree, Plan, and Vendor the Runtime
- **Locations**: git worktree `frontend-redesign` branch; `utils/frontend/static/js/dc-runtime.js` (new — copy of provided `support.js`); `docs/plans/2026-06-30-frontend-redesign-wiring.md` (this file).
- **Rationale**: Isolate the redesign in its own branch/worktree before touching the app. The dc-runtime must be served as a same-origin static asset so the page can boot the React component.
- **Action**: Undergo the verification/tests/validation process for this phase (confirm `support.js` copied byte-for-byte, worktree builds, Flask still imports). Once validated, commit to GitHub stating: Frontend Redesign (1/5) Complete: Vendored dc-runtime and scaffolded the redesign branch + plan.

### Step 2: Assemble the New `index.html` Design Shell
- **Locations**: `utils/frontend/templates/index.html` (replaced); reference source `/tmp/.../template_decoded.html` (the decoded `<x-dc>` template). New `app.py` static route for `dc-runtime.js` if needed (served from existing `static/` folder, so likely no route change).
- **Rationale**: The page must contain the exact design `<x-dc>` template + helmet, load the local `dc-runtime.js`, and host the `<script type="text/x-dc" data-dc-script>` Component block. The giant bundled `@font-face` block (UUID asset URLs) is swapped for standard Google Fonts `<link>` tags for Archivo / JetBrains Mono / Newsreader / Space Grotesk so typography still resolves.
- **Action**: Undergo the verification/tests/validation process for this phase (page loads, dc-runtime boots, mock UI renders end-to-end in a browser/preview with no console errors). Once validated, commit to GitHub stating: Frontend Redesign (2/5) Complete: Assembled the dc-runtime index page with the exported design rendering.

### Step 3: Rewrite the Component Data Layer (Reads)
- **Locations**: `index.html` → `data-dc-script` `Component` class: `constructor`, new `componentDidMount` (fetch `/api/jobs`), new `loadJobs()`, new `mapDbJob()` / `deriveColumn()` / `deriveApplied()` / `daysAgoFrom()` helpers; rework `renderVals()` to consume mapped DB jobs; `decorate()`, timeline builder, and `buildJobs()` removal of mock data.
- **Rationale**: All read paths (New Jobs grid, Tracker columns, pipeline sidebar stats, detail panel + timeline, search filter) must reflect real database rows and the 9-status model before any mutation wiring is meaningful.
- **Action**: Undergo the verification/tests/validation process for this phase (with seeded DB rows, grid/tracker/detail render real jobs; empty DB shows empty states). Once validated, commit to GitHub stating: Frontend Redesign (3/5) Complete: Component reads live job data from the API with DB→view mapping.

### Step 4: Wire Mutations and the Find Jobs Modal (Writes)
- **Locations**: `index.html` → `Component`: `toggleIgnore` → `PATCH /api/jobs/<id>/ignore`; `markApplied` + `moveTo` (drag-drop) + `toggleStatus` → `PATCH /api/jobs/<id>/status`; `clearDatabase` → `POST /api/database/clear`; Find modal `startScrape` → `GET /api/config/load`, `POST /api/config/save`, `POST /api/scrape/start`, poll `GET /api/scrape/status/<id>`; config-mapping helpers (`sitesToConfig`, `ageToHours`, `groupsToKeywords`); progress/stat mapping (`found`/`saved`/`notHidden`/`percent`/`stage`). Find-modal init prefilled from loaded config.
- **Rationale**: This makes the app fully interactive and persistent: ignoring, applying, status timeline toggles, kanban drag, database clear, and the full scrape lifecycle all hit the backend and refresh from it.
- **Action**: Undergo the verification/tests/validation process for this phase (run a real scrape end-to-end or mock the endpoints; verify each mutation persists across reload and the progress ring/stats track `/api/scrape/status`). Once validated, commit to GitHub stating: Frontend Redesign (4/5) Complete: All mutations and the Find Jobs scrape lifecycle wired to the API.

### Step 5: Cleanup, Tests, Validation, and Merge
- **Locations**: delete obsolete frontend assets (`static/js/{data,helpers,renderers,handlers,app}.js`, `static/js/components/*`, `templates/parts/*`, `templates/primary/*`, `static/css/*` no longer referenced); prune dead routes in `app.py` (`/parts/<...>`, `/primary/<...>`); add `tests/test_frontend_wiring.py` (Flask test client asserting `/` serves the dc page and key `/api/*` contracts return expected shapes); update `docs/frontend_structure.md`.
- **Rationale**: Removing the superseded modular frontend prevents confusion and dead code; an automated test locks the page-serving + API contract; docs reflect the new single-component architecture. Then merge to `main`.
- **Action**: Undergo the verification/tests/validation process for this phase (`tests/test_frontend_wiring.py` passes; full manual smoke test; `git merge` into `main` with conflicts resolved). Once validated, commit to GitHub stating: Frontend Redesign (5/5) Complete: Removed legacy frontend, added wiring tests, updated docs, merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Vendored dc-runtime | Local copy of the design runtime that boots React | `utils/frontend/static/js/dc-runtime.js` |
| New index page | dc-runtime page hosting the exported design + rewritten `Component` | `utils/frontend/templates/index.html` |
| API-wired Component | `Component extends DCLogic` reading/writing the real Flask API | `index.html` (`data-dc-script` block) |
| Slimmed app routes | `app.py` with legacy `/parts` `/primary` routes removed | `app.py` |
| Wiring tests | Flask test-client tests for page serving + `/api/*` contracts | `tests/test_frontend_wiring.py` |
| Updated docs | Frontend structure doc rewritten for the single-component design | `docs/frontend_structure.md` |
| Implementation plan | This plan | `docs/plans/2026-06-30-frontend-redesign-wiring.md` |
