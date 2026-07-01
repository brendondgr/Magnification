# Profile Blocklists & Scoped Keyword Groups — Implementation Plan

## 1. Introduction

This plan adds three layers of precision to the job feed so that irrelevant listings
(e.g. a job that only mentions "intern" because the role *trains* interns) stop leaking in.
All three are driven by the active **Profile**, which becomes the single source of truth for
user-defined blocking:

1. **Company blocklist** — a per-card **Block** button (top-right of each job card, to the left
   of the existing ignore/"hidden" eye button) adds that company to `profile.blocked_companies`.
   Blocked companies are hidden immediately and stay blocked on future scrapes. The list is
   openly editable in the Profile panel.
2. **Keyword Title Blocklist** — a Profile tag-list; any job whose **title** contains a
   blocklisted term (e.g. "Senior") is blocked.
3. **Scoped Keyword Group Preferences** — each Keyword Group gains toggle-able **Title** /
   **Description** buttons (between the group label and the trash button). A group is *satisfied*
   when at least one of its terms appears in **any selected location**. Groups are AND-ed; an
   unsatisfied group **blocks** the job (hard filter). Example: "intern" scoped to Title-only must
   appear in the title; "machine learning" scoped to Title+Description may appear in either.

The approach: extend the `Profile` model (+ a lightweight SQLite migration), centralize the
profile-driven block rules in one pure module, apply them at scrape time **and** on demand
(so blocking is retroactive), expose them through the profile API, and surface all three in the
dc-runtime `index.html` frontend (card Block button + three Profile-panel controls).

Blocking is **one-directional**: applying rules hides matching jobs but never un-hides a job
(removing a rule takes effect on the next scrape). This keeps us from having to distinguish
filter-hidden jobs from manually-ignored ones.

## 2. Gaps & Unanswered Questions

- **Retroactivity** — *Answered by user*: blocking a company or adding a Title Blocklist term
  hides matching jobs **immediately** and applies to future scrapes.
- **Keyword-group behavior** — *Answered by user*: scoped groups are a **hard filter**. "intern"
  on Title-only must be in the title; Title+Description means either location satisfies it.
- **Default scope for existing / new groups** — *Assumption*: a group with no `scopes` key
  defaults to `["title","description"]` (both), which is the most permissive and backward-compatible
  reading. New groups created in the UI also default to both.
- **Un-hiding when a rule is removed** — *Assumption*: not supported (one-directional). Documented
  as a known limitation; a re-scrape re-evaluates from scratch.
- **Relationship to the existing `jobs_config.json` filter** — *Assumption*: the existing Find
  Jobs → `jobs_config` title/description keyword filter is retained unchanged; the new profile
  block rules are layered **in addition** at the same filter step. Profile rules never widen the
  feed, only narrow it, so layering is safe.
- **Keyword-group soft score** — *Assumption*: `ranker.keyword_group_score` is upgraded to be
  scope-aware (checks title and/or description per group) so the match % stays consistent with the
  new filter semantics. This is a refinement, not a behavior the user must approve.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Worktree + plan doc
- **Locations**: `.claude/worktrees/profile-blocklists` (branch `profile-blocklists`),
  `docs/plans/profile-blocklists.md`.
- **Rationale**: Non-trivial work happens on a feature branch per the git workflow; the plan doc
  is the durable record other agents/contributors read.
- **Action**: Undergo the verification/validation process for this phase (plan doc present, branch
  created, baseline `pytest` green). Once validated, commit stating: Profile Blocklists (1/6)
  Complete: Worktree + implementation plan.

### Step 2: Data model + migration
- **Locations**: `utils/backend/database/models.py` (`Profile`: add `blocked_companies` JSON,
  `title_blocklist` JSON); `utils/backend/database/operations.py` (`_PROFILE_FIELDS`,
  `_profile_to_dict`); `utils/backend/recommend/profile_builder.py`
  (`EMPTY_PROFILE`, `_normalize_keyword_groups` → preserve/normalize per-group `scopes`, add
  `normalize_string_list` reuse for the two new lists); a new migration
  `utils/backend/database/migrate_profile_blocklists.py` (ALTER TABLE ADD COLUMN, mirroring
  `migrate_site_field.py`), invoked from `utils/backend/database/init_db.py` startup.
- **Rationale**: Every downstream layer (filter, API, UI) reads/writes these fields, so the schema,
  serialization, and normalization must exist first. `keyword_groups` is already JSON, so `scopes`
  needs no column — only normalization support.
- **Action**: Undergo the verification/tests/validation process for this phase (new
  `tests/database/test_profile_blocklists.py` round-trips the new fields; `import app` clean;
  migration is idempotent on an existing DB). Once validated, commit stating: Profile Blocklists
  (2/6) Complete: Profile gains blocked_companies + title_blocklist + scoped keyword_groups with
  migration.

### Step 3: Profile-driven filtering logic
- **Locations**: new `utils/backend/scrapers/profile_filter.py` with pure predicates
  (`title_blocked`, `company_blocked`, `keyword_groups_satisfied(title, description, groups)`,
  `job_blocked_by_profile(job, profile)`); integrate into
  `utils/backend/scrapers/job_filter.py` (`filter_and_mark_jobs` / `apply_filters` consult the
  active profile) and a new `apply_profile_filters(job_ids=None)` in
  `utils/backend/database/operations.py` (or the service layer) that marks matching jobs
  `ignore=1` one-directionally; upgrade `utils/backend/recommend/ranker.py`
  (`keyword_group_score(title, description, groups)` scope-aware) and its callers in
  `ranker.rank_batch` + `utils/backend/recommend/service.py` (pass job `title`).
- **Rationale**: One pure module keeps the block rules unit-testable and reused by both the
  scrape-time filter and the retroactive on-demand apply. Ranker consistency keeps the visible
  match % aligned with what is filtered.
- **Action**: Undergo the verification/tests/validation process for this phase (new
  `tests/scrapers/test_profile_filter.py`: company block, title blocklist, title-only vs both
  scope, AND-across-groups; ranker scope test). Once validated, commit stating: Profile Blocklists
  (3/6) Complete: Centralized profile block rules (company/title/scoped-groups) + scope-aware ranker.

### Step 4: Profile API endpoints
- **Locations**: `utils/backend/routes/profile_routes.py` — extend `save_profile` allowed fields
  (`blocked_companies`, `title_blocklist`, scoped `keyword_groups`) and re-apply profile filters on
  save; new `POST /api/profile/block-company` (add company → hide matching jobs → return count);
  update `docs/routes.md`, `docs/api-contract.md`.
- **Rationale**: The card Block button and the Profile-panel editors need endpoints; saving the
  profile must retroactively hide newly-matching jobs so edits take effect on the current feed.
- **Action**: Undergo the verification/tests/validation process for this phase (extend
  `tests/profile/test_profile_api.py`: save persists new fields; block-company hides matching jobs
  and is idempotent). Once validated, commit stating: Profile Blocklists (4/6) Complete: Profile API
  accepts blocklists + block-company endpoint with retroactive hide.

### Step 5: Frontend — card Block button + detail panel
- **Locations**: `utils/frontend/templates/index.html` — add a Block button in the card action
  column (line ~203, left of the ignore button) and in the detail panel header (line ~284); add
  `blockCompany(company)` method (optimistic hide of all matching jobs in state + POST
  `/api/profile/block-company`); decorate job with `onBlock` + `blockBtn` style in `decorate()`.
- **Rationale**: This is the primary retroactive entry point the user described ("if that company
  pops up, it will be blocked").
- **Action**: Undergo the verification/tests/validation process for this phase (preview tools:
  clicking Block hides that company's cards and persists; `test_frontend_wiring.py` still passes).
  Once validated, commit stating: Profile Blocklists (5/6) Complete: Per-card + detail Block-company
  button with instant hide.

### Step 6: Frontend — Profile panel controls + docs + merge
- **Locations**: `utils/frontend/templates/index.html` — Profile panel: **Blocked Companies**
  tag-list, **Keyword Title Blocklist** tag-list, and **Title/Description scope toggles** on each
  Keyword Group (between label and trash, line ~466); wire `loadProfile`/`saveProfile` and
  `renderVals` (`pfBlockedCompanies`, `pfTitleBlocklist`, per-group `scopes` toggles); update
  `docs/profile.md`, `docs/recommendation.md`, `docs/component-map.md`, `docs/design-system.md`
  (if a new control pattern), `docs/checklist.md`; merge `profile-blocklists` → `main`.
- **Rationale**: Completes the openly-editable Profile surface and documents the feature; merge
  delivers it.
- **Action**: Undergo the verification/tests/validation process for this phase (full `pytest`
  green, `import app` clean, preview verification of all three Profile controls + save round-trip).
  Once validated, commit stating: Profile Blocklists (6/6) Complete: Profile-panel blocklists +
  scoped keyword groups, docs, and merge to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Profile schema + migration | `blocked_companies`, `title_blocklist` columns; scoped `keyword_groups` | `utils/backend/database/models.py`, `utils/backend/database/migrate_profile_blocklists.py`, `init_db.py` |
| Profile serialization | New fields in dict + allowed-write sets + empty skeleton + normalization | `operations.py`, `recommend/profile_builder.py` |
| Profile filter module | Pure block predicates (company/title/scoped-groups) | `utils/backend/scrapers/profile_filter.py` |
| Filter integration + retroactive apply | Scrape-time + on-demand `apply_profile_filters` | `utils/backend/scrapers/job_filter.py`, `operations.py` |
| Scope-aware ranker | `keyword_group_score(title, description, groups)` + callers | `utils/backend/recommend/ranker.py`, `service.py` |
| Profile API | Extended save + `POST /api/profile/block-company` | `utils/backend/routes/profile_routes.py` |
| Frontend Block button | Per-card + detail-panel Block-company, optimistic hide | `utils/frontend/templates/index.html` |
| Frontend Profile controls | Blocked Companies + Title Blocklist tag-lists + scope toggles | `utils/frontend/templates/index.html` |
| Profile CRUD tests | Round-trip of new fields + migration idempotency | `tests/database/test_profile_blocklists.py` |
| Filter unit tests | Company/title/scoped-group block matrix + ranker scope | `tests/scrapers/test_profile_filter.py` |
| API tests | Save persistence + block-company retroactive hide | `tests/profile/test_profile_api.py` |
| Docs | Feature docs + contracts + checklist | `docs/profile.md`, `docs/recommendation.md`, `docs/routes.md`, `docs/api-contract.md`, `docs/component-map.md`, `docs/checklist.md` |
