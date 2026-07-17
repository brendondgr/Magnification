# Plan — Per-Page Search + Saved Sort (New Jobs & Saved)

## 1. Introduction

The New Jobs and Saved tabs currently share a single global sidebar search box whose
`matchSearch(j)` matches only a job's **title + company**. The Saved tab has no sort control and
renders jobs in the API's natural order (which reads as alphabetical to the user), while New Jobs
already has a Newest/Match toggle. This plan gives **each** of the New Jobs and Saved pages its own
independent, in-page search bar; broadens search to keyword-match across **all** visible job
information (title, company, location, compensation, site, description, and analyzed skills); and
adds a **Newest / Match** sort toggle to the Saved page (defaulting to Newest).

The work is confined to the single dc-runtime frontend file `utils/frontend/templates/index.html`
(template markup + the inline `Component` class), plus served-page wiring tests and docs. Because it
is one cohesive file, it is implemented directly (not via parallel agent workflows, which would
conflict on the same file). Per the user's instruction, each phase is **committed** locally — **not
pushed** — and the branch is finally merged to `main`.

## 2. Gaps & Unanswered Questions

- **Search independence** — *Resolved by user:* independent per-page search. New Jobs and Saved
  each get their own search term; the shared sidebar Search box is retired. The Tracker keeps
  working but loses its (previously global) search filter, which is acceptable.
- **Saved default sort** — *Resolved by user:* **Newest first**, with a button toggling to Match.
  Jobs without a match % sort last under Match.
- **"Newest" definition** — *Assumption:* newest = most recent `createdAt` (the stored
  `created_at` ISO timestamp already mapped in `mapDbJob`), descending. Ties keep stable order.
- **What "everything" covers for keyword search** — *Assumption:* concatenate `title`, `company`,
  `location`, `compensation`, `site`, `description`, and the analysis skill lists
  (`skill_match.matched` / `.missing`). Multi-word queries match when **every** whitespace-separated
  token appears somewhere in that text (case-insensitive substring). Empty query = match all.
- **New Jobs sort** — already has Newest/Match; left as-is except its filter switches to the new
  keyword matcher and its own search state.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Plan doc committed
- **Locations**: `docs/plans/jobs-search-and-saved-sort.md` (this file).
- **Rationale**: Record the approach, resolved forks, and assumptions before editing code.
- **Action**: Undergo the verification/validation process for this phase (doc reads cleanly). Once
  validated, **commit** stating: `Jobs Search + Saved Sort (1/4) Complete: plan doc + resolved design forks`.

### Step 2: Search + sort logic (Component class)
- **Locations**: `utils/frontend/templates/index.html` — the inline `Component` class:
  - `constructor` initial state (near line 1486–1494): add `searchNew:''`, `searchSaved:''`,
    `savedSortByMatch:false`; keep the existing `sortByMatch`/`page`.
  - New helper `keywordMatch(job, query)` (beside `matchSearch`, ~line 1609): tokenizes the query,
    builds the concatenated searchable text (title/company/location/compensation/site/description +
    analysis skills), returns true when every token is a substring. Empty query → true.
  - `render()` list computation (~lines 2416–2430):
    - New Jobs `all` filter: replace `this.matchSearch(j)` with `this.keywordMatch(j, s.searchNew)`.
    - Saved `savedList`: filter with `this.keywordMatch(j, s.searchSaved)`, then sort — Newest
      (`createdAt` desc) by default, Match (`match` desc, nulls last) when `savedSortByMatch`.
    - Tracker `columns` (~line 2403): drop the `this.matchSearch(j)` filter (global search retired).
  - `render()` returned props map (~lines 2577–2594): add `searchNew`/`onSearchNew`,
    `searchSaved`/`onSearchSaved`, and Saved sort props (`savedSortLabel`, `savedSortStyle`,
    `toggleSavedSort`, `savedAnyMatches`); leave New Jobs sort props intact.
  - Remove the now-unused `matchSearch` + `state.search`/`onSearch` wiring once no caller remains.
- **Rationale**: Centralizes the keyword matcher and per-page state so the markup only binds props;
  makes Saved "Newest" a real timestamp sort instead of insertion order.
- **Action**: Undergo the verification/validation process for this phase (`import app` clean; served
  page renders without console errors via the preview). Committed together with Step 3 (same file).

### Step 3: Template markup (search bars, Saved sort, retire sidebar search)
- **Locations**: `utils/frontend/templates/index.html`:
  - New Jobs header (~lines 182–199): add a search `<input>` bound to `{{ searchNew }}` /
    `{{ onSearchNew }}` with the magnifier icon, styled like the existing sidebar box.
  - Saved header (~lines 283–288): add the same search `<input>` bound to `{{ searchSaved }}` /
    `{{ onSearchSaved }}`, plus a Newest/Match sort `<button>` (mirrors the New Jobs `toggleSort`
    button) gated on `{{ savedAnyMatches }}`.
  - Sidebar Search block (~lines 89–95): remove it (search now lives on each page).
- **Rationale**: Puts search where the user asked (on each page) and gives Saved the requested sort
  control, reusing the established card/header styling.
- **Action**: Undergo verification for this phase — launch the preview, confirm both search inputs
  filter their own page across all fields, Saved sort toggles Newest↔Match, Tracker still renders,
  no console errors. Once validated, **commit** stating:
  `Jobs Search + Saved Sort (2/4) Complete: per-page keyword search + Saved Newest/Match sort; retire global sidebar search`.

### Step 4: Tests + docs
- **Locations**:
  - `tests/test_frontend_wiring.py`: add assertions that the served page exposes the New Jobs and
    Saved search inputs (`onSearchNew` / `onSearchSaved`), the Saved sort control
    (`toggleSavedSort`), and that the retired sidebar search token (`onSearch`) is gone.
  - Docs: `docs/component-map.md` (per-page search + Saved sort ownership), `docs/ui.md` (behavior
    note), `docs/checklist.md` (new Definition-of-Done section).
- **Rationale**: Locks the wiring against regressions and keeps `docs/` the source of truth.
- **Action**: Undergo verification — `uv run pytest tests/test_frontend_wiring.py` (and the offline
  subset) green, `import app` clean. Once validated, **commit** stating:
  `Jobs Search + Saved Sort (3/4) Complete: wiring tests + docs`.

### Step 5: Merge to main
- **Locations**: git (worktree branch `claude/jobs-search-sort-9da760` → `main`).
- **Rationale**: Deliver the feature onto the main line per the repo git workflow.
- **Action**: Merge the branch into `main`, resolving any conflicts; re-run the offline test subset +
  `import app` after merge. **Commit** the merge stating:
  `Jobs Search + Saved Sort (4/4) Complete: merged to main`. **Do not push.**

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan doc | This plan | `docs/plans/jobs-search-and-saved-sort.md` |
| `keywordMatch` helper + per-page state | All-fields keyword matcher; `searchNew`/`searchSaved`/`savedSortByMatch` state; Saved Newest/Match sort; Tracker search retired | `utils/frontend/templates/index.html` (Component class) |
| Per-page search + Saved sort UI | Search inputs on New Jobs and Saved headers; Saved Newest/Match button; sidebar Search block removed | `utils/frontend/templates/index.html` (template markup) |
| Wiring tests | Served-page assertions for the two search inputs, Saved sort control, and removal of the global search | `tests/test_frontend_wiring.py` |
| Docs | Component-map, UI notes, checklist Definition-of-Done | `docs/component-map.md`, `docs/ui.md`, `docs/checklist.md` |
