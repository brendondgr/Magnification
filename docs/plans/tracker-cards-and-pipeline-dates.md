# Tracker Card Slim-Down + Durable Pipeline Dates

Branch: `tracker-cards-pipeline-dates` (worktree). Delivered per-phase, merged to `main`.

## Requirements (user)

1. **Slim tracker cards** — on the Application Tracker kanban cards, remove the company
   logo/initials avatar, the location chip, and the compensation/salary chip. Keep only the
   **title** and **company**.
2. **Rename "Archived" → "Ghosted"** — the last kanban column (the `Ignored/Ghosted` lane).
3. **Scrollable columns** — the kanban lanes must not run past the edge of the screen; the
   lane row must stay within the viewport and scroll horizontally instead.
4. **Durable write-once pipeline dates** — every job records the **first** time each pipeline
   event occurred: found, applied, interviewing, offer, rejected, ghosted. These must be
   persisted and **never erased or overwritten** even when a card is dragged backward (the
   existing per-status `date_reached` is mutable — moving a card back clears it). Decision
   (user-confirmed): durable write-once history, not just surfacing the existing mutable dates.

## Findings (pre-work)

- `ApplicationStatus.date_reached` (`String(10)`, YYYY-MM-DD) already stores a per-status date,
  auto-stamped by `update_application_status(..., checked=1)` — but it is **cleared** when a
  status is un-checked (frontend `statusesForColumn` sets `date_reached=null`), so it is not a
  durable record.
- `Job.created_at` (`DateTime`) already durably records when a job was found.
- Kanban status changes funnel through **one** backend chokepoint:
  `PATCH /api/jobs/<id>/status` → `db_ops.update_application_status`. Stamping durable columns
  there captures every transition regardless of the frontend path.
- The 9 canonical statuses live in `utils/backend/database/config.py::APPLICATION_STATUSES`.

## Plan

### Phase 1 — Slim tracker cards (frontend)
`utils/frontend/templates/index.html`, tracker card markup: remove the initials-avatar `div`,
the `location` chip, and the `compensation` chip; keep title + company. Adjust the header
layout now that the avatar is gone.

### Phase 2 — Archived → Ghosted (frontend + test)
Change the `COLS` entry label `Archived` → `Ghosted` (keep the internal `key:'archived'` and
`--c-archive` token to avoid churn — single source drives the kanban and sidebar pipeline).
Update `tests/test_frontend_wiring.py` assertion accordingly.

### Phase 3 — Scrollable lane row (frontend)
The lane row already has `overflow-x:auto` but overflows because flex ancestors lack
`min-width:0`. Add `min-width:0` to the lane row (and the tracker section / main content column
as needed) so the row is capped at the viewport width and its own horizontal scroll engages.

### Phase 4 — Durable write-once pipeline dates (backend)
- `models.py::Job`: add `date_first_applied`, `date_first_interview`, `date_first_offer`,
  `date_first_rejected`, `date_first_ghosted` (`String(10)`, nullable). "Found" reuses the
  durable `created_at` (no redundant column).
- New idempotent migration `migrate_job_pipeline_dates.py` (add the 5 columns + **backfill**
  from existing checked `application_statuses.date_reached`, taking the earliest per event);
  registered in `init_db._run_migrations`.
- `operations.py`: a status→event map + write-once stamping inside `update_application_status`
  (set the mapped `Job` column only when currently `NULL`; never clear on un-check).
  `_job_to_dict` exposes the 5 columns + a derived `date_found` (from `created_at`).
- Tests (`tests/database/test_pipeline_dates.py`, isolated in-memory engine): write-once
  stamp, no-overwrite on re-reach, no-clear on un-check, dict exposure.

### Phase 5 — Surface the durable pipeline (frontend)
Add a compact, read-only **Pipeline history** readout to the job detail panel (Found / Applied
/ Interviewing / Offer / Rejected / Ghosted with their durable first-dates), and a **Found**
node so the full top-of-funnel is visible. Consume the new API fields.

### Phase 6 — Docs + validation + merge
Update `database.md`, `api-contract.md`, `data-flow.md`, `component-map.md`,
`design-system.md`, `structure.md`, `checklist.md`. Offline tests green + `import app` clean.
Live-verify in the preview. Merge to `main`, remove the worktree.
