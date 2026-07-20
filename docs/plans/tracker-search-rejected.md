# Application Tracker — Search + Rejected Column

## Requirement

The Application Tracker (kanban board) needs:
1. **Search** — a keyword search box on the Tracker page that filters the cards across
   every column (mirrors the per-page search already on New Jobs and Saved).
2. **A "Rejected" column** — a distinct kanban column, split out from the current
   catch-all **Archived** column so a rejected application is visible on its own.

## Current behavior (before)

- `Component.COLS` = `applied · interviewing · offers · archived`.
- `deriveColumn` folds **Rejected**, **Post-Interview Rejection**, and **Ignored/Ghosted**
  all into `archived`.
- `statusesForColumn('archived')` sets the `Rejected` status when a card is dropped there.
- The Tracker header has no search box; the columns show every applied job.

## Design decisions

- **Rejected is its own column, distinct from Archived.**
  - `rejected` catches **Rejected** + **Post-Interview Rejection** (an application the
    company turned down).
  - `archived` now means only **Ignored/Ghosted** (no response / self-archived).
  - Column order: `applied · interviewing · offers · rejected · archived`.
- **New theme token `--c-reject`** (red) drives the Rejected column dot/accent, per theme
  (neon `#FF4D6A`, editorial `#B23B36`). Consistent with the rejection-red used in the
  timeline.
- **Search reuses `keywordMatch`** (the same matcher New Jobs/Saved use) against a new
  `searchTracker` state; each column filters its jobs by it. The `N ACTIVE` count stays the
  unfiltered pipeline total; per-column count badges reflect the filtered set.

## Phases

1. Plan doc + worktree. *(this file)*
2. `index.html`: `--c-reject` token (both themes); `COLS` adds `rejected`; `deriveColumn` +
   `statusesForColumn` split rejected/archived; `searchTracker` state + tracker search input +
   per-column `keywordMatch` filter + `onSearchTracker` binding.
3. Wiring test (`tests/test_frontend_wiring.py`) for the tracker search input + Rejected
   column tokens; run offline suite + `import app`.
4. Docs (`component-map.md`, `design-system.md`, this checklist entry) + live verification.
5. Merge to `main`, remove the worktree.
