# Job Card Rows + Shared Description Enrichment

Branch: `job-card-and-enrichment` (Mode B — no worktree; feature branch off `main`).

## The report

1. Industry tagging "isn't being abided by" on the New Jobs page.
2. The card layout should be reorganized into five rows (see below).
3. Compensation renders as garbage when no salary exists —
   `USDnan - USDnan hourly`, `nannan - nannan nan` — instead of **"Not Specified"**.
4. Indeed listings in particular produce those values; compensation should **always** be
   extracted from the description during description extraction, and industry should be
   extracted at the same time.
5. **Both** "Find Jobs" and "Analyze Matches" must run the *same* extraction code — not two
   separate implementations.

## Diagnosis (measured on the real DB, 7,974 jobs)

| Symptom | Root cause |
| --- | --- |
| `USDnan - USDnan hourly` (348 rows) and `nannan - nannan nan` (926 rows) | `data_processor.clean_job_data` (and the parallel `jobspy_wrapper.normalize_job_data`) build the pay string from jobspy's `min_amount`/`max_amount`/`currency`/`interval`. Indeed rows carry **pandas `NaN`** in those fields; `float('nan')` is **truthy**, so `if min_amount or max_amount:` passes and `f"{nan:,.0f}"` formats as `"nan"`. `currency`/`interval` NaN stringify to `"nan"` too. |
| Those jobs never get pay recovered | `needs_compensation()` treats any non-empty string as "has pay", so a `nan` string permanently blocks LLM recovery. |
| Industry missing on most cards | `industry_checked` is set to `1` even when the LLM returned **no** label (call failed / unparseable), so the job is never retried. On the current feed: 17 non-ignored jobs, all 17 flagged `industry_checked`, only 7 carry a label. |
| Two extraction implementations | `scrapers/scraping_service.py` step 7a and `recommend/service._recover_enrichment` each re-implement the same gating + call + persistence around the shared `extract_enrichment_llm`. They can (and did) drift. |

## Target card layout (top → bottom)

| Row | Left | Right |
| --- | --- | --- |
| 1 | Source pill (where the job came from) | Industry tag |
| 2 | Title — **clamped to 2 lines** | — |
| 3 | Company + `(YYYY-MM-DD)` extraction date, back-to-back | Match % + `?` breakdown button |
| 4 | Location | Compensation (or "Not Specified") |
| 5 | Description — **clamped to 4 lines** | — |

Everything below row 5 (Generate/Applied buttons, the icon action row) is unchanged.

## Plan

### Phase 1 — Plan doc + branch
This document; branch `job-card-and-enrichment`.

### Phase 2 — Kill the `nan` compensation at the source
- `recommend/compensation.py`: add `clean_compensation(value)` — the single normalizer that
  rejects `nan`-poisoned / digit-less strings and returns `None`. `needs_compensation` and
  `_parse_comp` route through it.
- `scrapers/data_processor.clean_job_data` + `scrapers/jobspy_wrapper.normalize_job_data`:
  skip non-finite amounts, drop `nan` currency/interval, and emit no string at all when no
  finite amount survives.
- `database/migrations`: idempotent `migrate_clean_bad_compensation` — blank the malformed
  values already stored and clear their `compensation_checked` flag so they are re-extracted.
- Tests: `tests/scrapers/test_data_processor.py`, `tests/recommend/test_compensation.py`.

**Validate:** unit tests green; migration run against the real DB drops the 1,274 bad rows to 0.

### Phase 3 — One shared enrichment pipeline
- New `utils/backend/recommend/enrichment.py` — `enrich_jobs(jobs, runtime=None, force=False,
  progress=None)`: the **only** place that gates on the toggles + endpoint, selects candidates,
  calls `extract_enrichment_llm`, and persists. Returns
  `{candidates, compensation, industry, attempted}`.
- `recommend/service._recover_enrichment` and `scrapers/scraping_service` step 7a both become
  thin calls into it (no duplicated gating/persistence).
- Semantics changes, per the request:
  - **Compensation is always extracted from the description**: `needs_compensation_recovery`
    no longer requires the job to be missing pay — a description plus an unset
    `compensation_checked` is enough. A value found in the description wins over the board's
    value; when the description states none, whatever the board gave is kept.
  - `industry_checked` is only stamped when a label actually came back, so a failed/empty LLM
    response retries next run instead of poisoning the job forever.
- Tests: `tests/recommend/test_enrichment.py` (shared-path parity: the scrape workflow and
  `analyze_jobs` both route through `enrich_jobs`), plus updates to the existing
  compensation/industry/gap-fill/scrape-order tests.

**Validate:** `tests/recommend`, `tests/scrapers`, `tests/database` green; `import app` clean.

### Phase 4 — Card layout + "Not Specified"
- `utils/frontend/templates/index.html`: rebuild the New Jobs and Saved `<article>` rows to the
  table above; title `-webkit-line-clamp:2`, description `-webkit-line-clamp:4`;
  `mapDbJob` emits `Not Specified` (and sanitizes any residual `nan` string) plus a
  `companyDate` string.
- Wiring test in `tests/test_frontend_wiring.py`.

**Validate:** wiring test green; served page inspected (the Browser pane cannot composite in
this environment — verification is via served HTML + `/api/jobs`, as in prior UI work).

### Phase 5 — Docs, full validation, merge
`docs/data-flow.md`, `docs/database.md`, `docs/component-map.md`, `docs/design-system.md`,
`docs/structure.md`, `docs/documentation.md`, `docs/checklist.md`; offline suites; merge to
`main`.
