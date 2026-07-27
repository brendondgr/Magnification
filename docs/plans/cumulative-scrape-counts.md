# Plan — Cumulative "Jobs Found" / "Jobs Saved" across search iterations

Branch: `cumulative-scrape-counts` (Mode A — worktree at
`.claude/worktrees/cumulative-scrape-counts`, based on `4fd97d4`).

## Requirement (user)

> When doing the job searches, "Jobs Found" should be accurate if the user is going through
> multiple iterations — it should be cumulative. Same for "Jobs Saved": cumulative, and updated
> after every iteration **when the items are saved**.

## Current behavior (root cause)

The Find Jobs progress view renders three stats (`index.html`, `scrapeStats`):
**Jobs Found** (`s.found`) · **Jobs Saved** (`s.saved`) · **Not Hidden** (`s.notHidden`).

`execute_full_scraping_workflow` runs the scrape→process→db-dedup→LinkedIn→save block once per
iteration (`max_iterations`, 1–5). Four defects make the first two stats wrong:

1. **Live "Jobs Found" resets every iteration.** Each pass constructs a *fresh* `JobSpyScraper`,
   whose internal `total_jobs_found` restarts at 0. `scraper_progress_handler` forwards that raw
   per-pass count as `details.jobs_found`, and the poller assigns it directly
   (`patch.found = details.jobs_found`). With 3 iterations the counter climbs, snaps back to a
   small number, climbs again — never showing the run total.

2. **Final "Jobs Found" is last-pass only.** `results['steps']['scraping']` / `['processing']` /
   `['db_dedup']` / `['storage']` are **overwritten** on every pass, so the completion handler's
   `steps.processing.processed_count` describes only the final iteration.

3. **"Jobs Saved" stays 0 for the whole run.** Nothing emits a saved count during the scrape;
   `s.saved` is only assigned once, at completion, from the last-pass-only
   `steps.storage.stored_count`.

4. **The "no new jobs" early return zeroes the counter.** When every pass is fully deduped away,
   the workflow emits `jobs_found: 0`, wiping a legitimately non-zero found count.

## Decisions

- **"Jobs Found" = cumulative *raw* listings discovered across every iteration.** That is already
  what the live counter means mid-scrape; today it drops at completion to the post-dedup unique
  count, which reads as a regression. Making both ends of the run report the same cumulative raw
  total keeps the number monotonic. The unique/deduped total is not lost — it goes into the
  completion summary line and the results payload (`processing.processed_count`).
- **"Jobs Saved" = cumulative rows actually inserted**, emitted right after each iteration's
  step-5 storage block (so it ticks up per iteration, only when jobs really were saved).
- **"Not Hidden" is already correct** — filtering runs once over the accumulated `job_ids`.
- Per-iteration detail is preserved in `results['steps']['iterations']['passes']` so nothing that
  the cumulative rollup hides is thrown away.

## Steps

### 1. Plan doc + worktree — *this file*

### 2. Backend: cumulative counters in `execute_full_scraping_workflow`
`utils/backend/scrapers/scraping_service.py`

- Hoist `cum_raw` / `cum_processed` / `cum_stored` counters outside `_scrape_process_store`.
- `scraper_progress_handler` reports `jobs_found = cum_raw_at_pass_start + pass_count` (and says
  so in the message).
- After the step-5 save, emit `update_progress('saving', …, {'jobs_saved': cum_stored, …})`.
- Roll `steps.scraping.raw_jobs_count`, `steps.processing.processed_count`,
  `steps.db_dedup.removed`, and `steps.storage.stored_count` / `job_ids` up cumulatively;
  add `steps.iterations.passes[]` with the per-pass breakdown.
- Per-iteration "Iteration i/N done" message carries `jobs_found` + `jobs_saved`.
- Early return (no new jobs) reports the real cumulative `jobs_found` and `jobs_saved: 0`.
- Final `completed` details carry `jobs_found` (cumulative raw), `jobs_saved`, `jobs_kept`,
  and `jobs_unique`.

**Validate:** `uv run pytest tests/scrapers` — existing iteration/order/event tests stay green.

### 3. Backend tests
`tests/scrapers/test_cumulative_counts.py` (new, fully offline, fakes as in `test_iterations.py`):

- multi-iteration run → `steps.storage.stored_count` and `steps.scraping.raw_jobs_count` equal the
  sum over passes, not the last pass;
- `jobs_saved` in the progress stream is non-decreasing and reaches the total;
- `jobs_found` in the progress stream is non-decreasing across iteration boundaries;
- fully-deduped run → `jobs_found` in the terminal event is the real raw total, not 0;
- single-iteration run → counts unchanged from today.

**Validate:** `uv run pytest tests/scrapers`.

### 4. Frontend: consume the cumulative fields
`utils/frontend/templates/index.html`

- `pollScrape`: read `details.jobs_saved` into `patch.saved`; clamp `found`/`saved`/`notHidden`
  to be monotonic (`Math.max` against current state) so a late/stale poll can't walk them back.
- Completion: `found` = cumulative raw (`steps.scraping.raw_jobs_count`, falling back to the
  polled value), `saved` = cumulative `steps.storage.stored_count`, and a summary line that also
  surfaces the unique count.

**Validate:** wiring test + live check on the served page.

### 5. Frontend wiring test + docs
- `tests/test_frontend_wiring.py::test_index_scrape_stats_are_cumulative`.
- Docs: `docs/data-flow.md` (iteration/progress semantics), `docs/api-contract.md`
  (`/api/scrape/status` details fields), `docs/find_jobs.md` (what the three stats mean),
  `docs/checklist.md` (Definition of Done).

**Validate:** `uv run pytest tests/scrapers tests/test_frontend_wiring.py`; `import app` clean.

### 6. Merge + clean up
Commit per phase, merge `cumulative-scrape-counts` → `main`, remove the worktree.

## Out of scope

- Changing how iterations page through jobspy (`offset` advance) or the 1–5 clamp.
- The Analyze Matches stats trio (`aTotal`/`aLLM`/`aComp`) — that flow is single-pass.
