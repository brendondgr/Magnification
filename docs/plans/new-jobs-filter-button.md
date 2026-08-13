# Plan — "Filter" button on the New Jobs header

**Status:** shipped
**Branch:** `feature/new-jobs-filter-button`

## Problem

Block rules only ran at two moments: during a scrape (`filter_and_mark_jobs`, over the ids that
scrape just wrote) and on Profile Save / Block Company (`apply_profile_filters`, profile rules
only). There was no way to re-apply the rules on demand to the jobs already in the feed — in
particular, editing the Find Jobs **title / description keywords** in `jobs_config.json` had no
retroactive effect at all, and a user who tightened their filters had to re-scrape to see it.

## Goal

A **Filter** button immediately to the left of *Analyze matches* on the New Jobs header. It hides
every currently visible (non-hidden, non-saved) job that fails either rule set:

1. `jobs_config.json` — `job_titles` + `description_keywords` (the Find Jobs filter).
2. The active profile — `title_blocklist`, `blocked_companies`, and `keyword_groups`.

## Steps

1. **Backend predicate** — add `job_filter.apply_all_filters(job_ids=None)`: loads the jobs config
   and the active profile, walks the visible jobs, exempts `saved=1`, and sets `ignore=1` on any
   job failing `apply_filters(...)` or matched by `profile_filter.job_blocked_by_profile(...)`.
   One-directional, like the existing helpers — nothing is ever un-hidden.
   *Validate:* unit tests over an in-memory DB covering config-only, profile-only, saved-exempt,
   and already-hidden cases.
2. **Route** — `POST /api/jobs/filter` in `job_routes.py` → `{success, checked, hidden}`.
   *Validate:* a Flask test-client test asserting the response shape and that the matching job's
   `ignore` flag flipped.
3. **Frontend** — a secondary `Filter` button (funnel icon) left of *Analyze matches*, with a
   `filterBusy` state, a result toast, and a feed reload.
   *Validate:* wiring test asserting the button, its handler, and the fetch call are in the served
   page; browser pane does not composite here, so verification is via the served HTML + API.
4. **Docs** — `docs/routes.md`, `docs/api-contract.md`, `docs/component-map.md`,
   `docs/data-flow.md`, `docs/checklist.md` ledger.

## Notes

- Saved jobs stay exempt (`docs/plans/saved-jobs-not-auto-hidden.md`).
- The button acts on **all** currently visible jobs, not just the current page or the current
  search query — the header count updates after the reload.
