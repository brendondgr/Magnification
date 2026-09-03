# Plan — Bulk Filter popup (wipe out many jobs at once)

**Status:** proposed
**Branch:** `feature/bulk-filter-popup`

## 1. Introduction

Today the New Jobs **Filter** button is a single-shot action: it re-applies the saved rule sets
(`jobs_config.json` title/description keywords + the active profile's blocklists) to the visible
feed and hides whatever fails. There is no way to say "hide everything older than three weeks",
"hide everything under 40% match", or "hide every Retail job" without editing the profile first.
When a few hundred active jobs pile up, the user has no bulk instrument to cut the feed down.

This plan replaces the one-shot button with a **Filter popup**: a modal on the New Jobs header that
offers four ad-hoc criteria — title/description keywords, a cutoff date, a minimum match
percentage, and an industry multi-select — plus the existing "re-apply my saved rules" action. The
popup shows a live *dry-run* count ("will hide 143 of 312") before anything is committed, and the
commit is the same one-directional `ignore=1` pass the feed already uses, so every hidden job stays
recoverable via **Show Ignored**.

## 2. Gaps & Unanswered Questions

- **There is no board "posted" date.** `Job` stores `created_at` (surfaced as `date_found`); no
  scraper captures a posting date. *Assumption*: the date criterion filters on `date_found`
  (`created_at`). This is a close proxy because `scraper_config.DEFAULT_HOURS_OLD = 24` bounds each
  scrape to recently-posted listings. The popup will label it **"Found before"** with a one-line
  note, not "Posted before", so the semantics are honest.
- **Which industries to list.** *Assumption*: list only the industries actually present in the
  visible feed, each with its live count, sourced from a new facets endpoint — the user asked for
  "specific industry based on what is available". Jobs with no industry yet (`industry` null,
  classification not run) get an explicit **"Unclassified"** entry so they are selectable rather
  than invisible.
- **Jobs with no match score.** A job that has never been analyzed has `analysis = null`, so a
  "below X%" test is undefined for it. *Assumption*: unscored jobs are **kept** by default, with an
  opt-in checkbox "also hide jobs with no match score".
- **Multiple criteria together.** *Assumption*: criteria are OR'd — a job is hidden if it matches
  **any** enabled criterion. That is what "wipe out a lot of stuff at once" means; AND semantics
  would routinely hide nothing.
- **Keyword direction.** The saved `jobs_config` keywords are a *keep* list (a job must match to
  survive). The popup's keyword box is the opposite: a *kill* list ("hide anything containing
  these"), which is what "filter out manually based on Title/Description keywords" describes.
  *Assumption*: it is a kill list, labeled as such, with Title/Description scope toggles mirroring
  the profile keyword-group scope chips.
- **Should the popup be able to un-hide?** *Assumption*: no. Every existing hide path is
  one-directional and **Show Ignored** + the per-card un-hide is the reverse. Keeping the popup
  one-directional means it can never resurrect something the user deliberately buried.
- **Saved jobs.** *Assumption*: exempt, matching `docs/plans/saved-jobs-not-auto-hidden.md`.

## 3. Hierarchical Step-by-Step Instructions

### Step 1 (1/6): Bulk-rule predicate + dry-run engine

- **Locations**: `utils/backend/scrapers/job_filter.py` — new `BulkRules` normalizer
  (`normalize_bulk_rules`), a per-job predicate `job_matches_bulk_rules(job, analysis, rules)`, and
  the driver `apply_bulk_filters(rules, job_ids=None, dry_run=False)`. Reads analyses via
  `database.operations.get_analysis_for_jobs`.
- **Rationale**: the popup needs one function that both *previews* and *commits*, so the number the
  user is shown and the number that is hidden can never disagree. Putting it beside
  `apply_all_filters` keeps every hide rule in the module that already owns hiding, and keeps the
  route thin. The predicate returns *which* criteria matched so the UI can show a per-criterion
  breakdown ("keywords 41, date 78, match 92, industry 14").
- **Scope guarantees** (identical to `apply_all_filters`): saved jobs skipped, already-hidden jobs
  skipped, only `ignore=0` rows considered, hide-only.
- **Action**: Undergo the verification/tests/validation process for this phase — unit tests over an
  in-memory engine covering each criterion alone, criteria combined (OR), the saved-job exemption,
  the unscored-job default and its opt-in, "Unclassified" industry selection, and `dry_run=True`
  leaving `ignore` untouched. Once validated, commit to git stating: *Bulk Filter popup (1/6)
  Complete: added the bulk-rule predicate and dry-run/commit driver to job_filter.py.*

### Step 2 (2/6): Facets endpoint

- **Locations**: `utils/backend/routes/job_routes.py` — new `GET /api/jobs/filter/options`;
  supporting aggregate in `utils/backend/database/operations.py`
  (`get_feed_filter_facets()`).
- **Rationale**: the popup's industry list and its slider/date bounds must reflect the *actual*
  feed, not a hardcoded taxonomy. One cheap aggregate query (counts grouped by industry, count of
  scored vs unscored, oldest/newest `created_at`, total visible) avoids shipping every job row to
  the client just to build a checkbox list.
- **Response shape**: `{industries:[{label,count}], unclassified, scored, unscored, oldest, newest,
  total}`.
- **Action**: Undergo the verification/tests/validation process for this phase — a Flask
  test-client test asserting the shape and that counts exclude hidden and saved rows. Once
  validated, commit to git stating: *Bulk Filter popup (2/6) Complete: added the
  /api/jobs/filter/options facets endpoint.*

### Step 3 (3/6): Extend the filter route

- **Locations**: `utils/backend/routes/job_routes.py` — `filter_jobs()` gains an optional `rules`
  object and a `dry_run` flag, dispatching to `apply_bulk_filters` when `rules` is present and
  falling through to the existing `apply_all_filters` when it is not.
- **Rationale**: one endpoint, two modes, keeps the saved-rules button and the ad-hoc popup on the
  same contract and the same response envelope (`{success, checked, hidden, breakdown}`). Backwards
  compatible: an empty body behaves exactly as it does today, so nothing that already calls it
  breaks.
- **Validation of input** happens in `normalize_bulk_rules` (bad date → 400, threshold clamped to
  0–100, unknown industries ignored), so the route stays a thin adapter.
- **Action**: Undergo the verification/tests/validation process for this phase — test-client tests
  for: legacy empty body, `dry_run` returning counts with no DB mutation, a committing call
  flipping `ignore`, and a malformed date returning 400. Once validated, commit to git stating:
  *Bulk Filter popup (3/6) Complete: /api/jobs/filter now accepts ad-hoc rules and a dry-run flag.*

### Step 4 (4/6): The Filter popup UI

- **Locations**: `utils/frontend/templates/index.html` — a new
  `<sc-if value="{{ filterOpen }}">` overlay block (`data-overlay="filterfeed"`) placed with the
  other centered modals; the header **Filter** button rewired from `filterJobs` to `openFilter`;
  `Component` state (`filterOpen`, `fltKeywords`, `fltScopes`, `fltBefore`, `fltMinMatch`,
  `fltIndustries`, `fltUnscored`, `fltPreview`, `fltFacets`, `filterBusy`) and methods
  (`openFilter`, `closeFilter`, `loadFilterFacets`, `previewFilter` (debounced),
  `applyBulkFilter`, `applySavedRules`); `closeOverlay` / `_overlayOpen` extended for the new
  overlay; the exit-animation pair added alongside the other `closing` entries.
- **Rationale**: the modal is where all four criteria live, per the request. It follows the
  established overlay contract (scrim + `data-overlay` + Esc/Tab trap + animated exit) so focus
  management and reduced-motion handling come for free rather than being re-implemented. The
  debounced dry-run keeps the "will hide N" number live as the user drags the slider without
  hammering the endpoint.
- **Popup contents**: keyword tag input + Title/Description scope chips; "Found before" date input
  with 7/14/30-day quick presets; "Hide below X% match" slider with the unscored opt-in; industry
  checkbox list built from the facets (each with its count, plus Unclassified); a live
  "Will hide N of M" summary with the per-criterion breakdown; a destructive-styled **Hide N jobs**
  button; and a secondary **Re-apply saved rules** action preserving today's behavior.
- **Action**: Undergo the verification/tests/validation process for this phase — the browser pane
  does not composite in this environment, so verify via the served HTML (`GET /`), a wiring test
  asserting the overlay, its controls, the handlers and the fetch calls are present, and the
  accessibility checklist in `docs/skills/accessibility-mobile/SKILL.md` (44px targets, labels,
  `aria-modal`, focus trap). Once validated, commit to git stating: *Bulk Filter popup (4/6)
  Complete: the New Jobs Filter button now opens a multi-criteria bulk-hide popup with a live
  preview.*

### Step 5 (5/6): Tests

- **Locations**: `tests/scrapers/test_bulk_filter_rules.py` (predicate + dry-run over an in-memory
  engine), `tests/backend/test_bulk_filter_api.py` (route contract + facets endpoint),
  `tests/frontend/test_filter_popup_wiring.py` (served-page wiring + a11y attributes).
- **Rationale**: the repo's testing rule is offline, area-grouped tests that isolate the shared
  database. Splitting by layer matches the existing `tests/scrapers` / `tests/backend` /
  `tests/frontend` grouping and keeps each file well under the length cap.
- **Action**: Undergo the verification/tests/validation process for this phase — `uv run pytest`
  green, and `uv run python -c "import app"` still succeeds. Once validated, commit to git stating:
  *Bulk Filter popup (5/6) Complete: added predicate, API, and served-page wiring tests.*

### Step 6 (6/6): Documentation

- **Locations**: `docs/api-contract.md` (the extended `/api/jobs/filter` body + the new
  `/api/jobs/filter/options`), `docs/routes.md` (endpoint map), `docs/component-map.md` (the new
  overlay and its state/handlers), `docs/data-flow.md` (the bulk-hide path), `docs/structure.md`
  (new test files), `docs/checklist.md` (ledger entry pointing at this plan), and this plan's
  status → shipped.
- **Rationale**: the repository's documentation rule requires the matching doc to change in the
  same work as the code; a route whose contract is not in `api-contract.md` is a competing source
  of truth.
- **Action**: Undergo the verification/tests/validation process for this phase — `uv run pytest
  tests/docs` green (doc-link and skill-pointer checks). Once validated, commit to git stating:
  *Bulk Filter popup (6/6) Complete: documented the bulk filter rules, endpoints, and UI ownership.*

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Bulk rule predicate + driver | `normalize_bulk_rules`, `job_matches_bulk_rules`, `apply_bulk_filters(rules, job_ids, dry_run)` — keyword kill-list, found-before date, min-match, industry set; hide-only, saved-exempt. | `utils/backend/scrapers/job_filter.py` |
| Feed facets aggregate | `get_feed_filter_facets()` — industry counts, scored/unscored counts, date bounds over the visible feed. | `utils/backend/database/operations.py` |
| Facets endpoint | `GET /api/jobs/filter/options`. | `utils/backend/routes/job_routes.py` |
| Extended filter endpoint | `POST /api/jobs/filter` accepting `{rules, dry_run, job_ids}`; legacy empty body unchanged. | `utils/backend/routes/job_routes.py` |
| Filter popup overlay | `data-overlay="filterfeed"` modal: keywords + scopes, found-before date + presets, match slider + unscored opt-in, industry checkboxes, live "will hide N of M" preview, Hide button, Re-apply saved rules. | `utils/frontend/templates/index.html` |
| Predicate unit tests | Each criterion alone and combined, saved exemption, unscored default/opt-in, Unclassified industry, dry-run purity — in-memory engine. | `tests/scrapers/test_bulk_filter_rules.py` |
| API tests | Facets shape/exclusions; filter route legacy body, dry-run, commit, 400 on bad date. | `tests/backend/test_bulk_filter_api.py` |
| Frontend wiring tests | Served page contains the overlay, its controls, handlers, fetch calls, and the a11y attributes. | `tests/frontend/test_filter_popup_wiring.py` |
| Doc updates | Contract, route map, component ownership, data flow, structure, checklist ledger. | `docs/api-contract.md`, `docs/routes.md`, `docs/component-map.md`, `docs/data-flow.md`, `docs/structure.md`, `docs/checklist.md` |
