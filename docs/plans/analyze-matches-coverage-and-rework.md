# Plan — Fix "Analyze Matches" Coverage & Redundant Re-work

## 1. Introduction

The "Analyze Matches" action has three related defects. First, it reports that every
job "already has an LLM fit" and issues no new verdicts, even though many non-ignored
jobs genuinely lack one (the live DB has 56 non-ignored jobs with an analysis row but a
`NULL` `llm_score`, versus 27 with a verdict). The cause is that the saved runtime config
has the **"Jobs through the LLM" slider at 100%** yet also carries a stale **`top_n_llm`
cap of 10**; `_select_llm_indices` applies that absolute cap *after* the fraction, so
coverage is silently limited to the 10 most-relevant jobs — all of which already have a
verdict — and the gap-fill filter then finds nothing. Second and third, every run
re-extracts **skills** for all jobs and re-queries the LLM for **compensation** on every
no-pay job, because neither reuses prior work.

The approach: (1) make the coverage slider authoritative by retiring the redundant
`top_n_llm` knob so 100% means every job; (2) reuse stored `extracted_skills` and only
extract for jobs missing them; and (3) add a durable `compensation_checked` flag so a job
whose description states no pay is queried once, not on every run. Each phase is
independently testable and committed on its own.

## 2. Gaps & Unanswered Questions

- **Slider vs. top-N interaction** — Resolved by the user: the coverage slider is
  authoritative; the redundant "LLM top-N" field is retired.
- **Compensation "already checked" memory** — Resolved by the user: add a durable
  `compensation_checked` column (idempotent migration), not an in-run-only skip.
- **Re-extract skills on `reanalyze_all`?** *Assumption*: skills are derived from the job
  description only, so gap-fill (extract only when missing) is always safe; a
  `reanalyze_all` (force) run still re-extracts every job so a changed extraction method
  or gazetteer can refresh them.
- **Force path for compensation** — *Assumption*: a `reanalyze_all` run re-attempts
  compensation even for already-checked jobs (treat "force" as "ignore the checked flag").
- **Profile-scoped `llm_score` gap-fill** — The gap-fill keys off `llm_score is not None`
  without comparing `profile_id`. With a single active profile (the live state) this is
  moot; noted as a latent follow-up, out of scope here.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Retire `top_n_llm` — make the coverage slider authoritative (Bug 1)
- **Locations**:
  - `utils/backend/recommend/service.py` — `_select_llm_indices()`: remove the `top_n_llm`
    cap block and its docstring paragraph; coverage is decided solely by `llm_fraction`
    (top `ceil(f × N)` by semantic+bm25) then the gap-fill `llm_score is None` filter.
    Update `_llm_rerank()` / `analyze_jobs()` docstrings that mention `top_n_llm`.
  - `utils/backend/recommend/runtime_config.py` — drop `top_n_llm` from
    `DEFAULT_RUNTIME_CONFIG` (and therefore `_ALLOWED_KEYS`); a stale key in the saved
    JSON becomes an ignored no-op.
  - `utils/frontend/templates/index.html` — remove the "LLM top-N (0 = all)" number field,
    the `rtTopN`/`onRtTopN` view bindings, and `top_n_llm` from the inline `runtime`
    default object.
  - Docs: `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md`,
    `docs/checklist.md` — remove/replace `top_n_llm` references; note the slider is the
    single coverage control.
- **Rationale**: The absolute cap silently overrode the prominent 100% slider, so the
  gap-fill never reached the 56 verdict-less jobs. Removing it makes 100% mean "every
  non-ignored job eventually gets a verdict," matching the UI's promise.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit to GitHub stating: Analyze Matches Coverage (1/3) Complete: retired the
  redundant top_n_llm cap so the coverage slider fully controls LLM fit coverage.

### Step 2: Reuse stored skills — stop re-extracting every run (Bug 2b)
- **Locations**:
  - `utils/backend/recommend/service.py` — `analyze_jobs()` and
    `_extract_skills_for_jobs()`: pass the already-fetched `stored` analyses in; reuse
    `stored[id]["extracted_skills"]` when present and only extract for jobs missing them.
    When `llm_only_missing` is False (force/`reanalyze_all`), extract for all jobs.
- **Rationale**: Skills depend only on the description, so recomputing them for every job
  on every run (and, with `enable_llm_skills`, re-hitting the LLM) is wasted work. Reusing
  stored skills mirrors how embeddings are already reused by `_ensure_embeddings`.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit to GitHub stating: Analyze Matches Coverage (2/3) Complete: reuse stored
  extracted_skills and only extract skills for jobs that lack them.

### Step 3: Add `compensation_checked` flag — query pay once (Bug 2a)
- **Locations**:
  - `utils/backend/database/models.py` — add `compensation_checked` (Boolean, default
    False) to `Job`; document it in the class docstring.
  - `utils/backend/database/migrate_job_compensation_checked.py` (new) — idempotent
    `ALTER TABLE jobs ADD COLUMN compensation_checked INTEGER DEFAULT 0`, mirroring
    `migrate_job_saved.py`.
  - `utils/backend/database/init_db.py` — register the new migration in `_run_migrations`.
  - `utils/backend/database/operations.py` — include `compensation_checked` in
    `_job_to_dict`.
  - `utils/backend/recommend/compensation.py` — add `needs_compensation_recovery(job,
    force=False)` = `needs_compensation(job) and (force or not
    job.get("compensation_checked"))`.
  - `utils/backend/recommend/service.py` — `_recover_compensation(jobs, runtime, force)`:
    select via `needs_compensation_recovery`; after extraction, persist
    `compensation_checked=True` (plus any recovered `compensation`) for every attempted
    job. `analyze_jobs` passes `force=not llm_only_missing`.
  - `utils/backend/scrapers/scraping_service.py` — the Step 7a compensation block: select
    via `needs_compensation_recovery` and persist `compensation_checked=True` for attempted
    jobs so the scrape path and the button agree.
  - Docs: `docs/database.md`, `docs/data-flow.md` — document the new column and the
    "checked once" behavior.
- **Rationale**: Jobs whose descriptions truly state no pay never gain a `compensation`
  value, so the current `needs_compensation`-only gate re-queries them on every run. A
  durable flag records "we already asked the LLM," eliminating the repeated cost while a
  force run can still re-attempt.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit to GitHub stating: Analyze Matches Coverage (3/3) Complete: added a
  durable compensation_checked flag so pay is extracted once, not on every run.

### Step 4: Merge to `main`
- **Locations**: git — merge `claude/analyze-results-matching-issue-20e8a8` into `main`,
  resolving any conflicts; re-run the recommend test suite post-merge.
- **Rationale**: The work is done in a worktree/branch; it must land on `main` per the git
  workflow, with the full suite green after integration.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, the branch is merged into main (not pushed unless asked).

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Slider-authoritative coverage | Remove `top_n_llm` cap; slider is the only LLM-coverage control | `utils/backend/recommend/service.py`, `utils/backend/recommend/runtime_config.py`, `utils/frontend/templates/index.html` |
| Skills reuse | Gap-fill `extracted_skills`; only extract for jobs missing them | `utils/backend/recommend/service.py` |
| Compensation flag + migration | `compensation_checked` column, idempotent migration, one-time extraction | `utils/backend/database/models.py`, `utils/backend/database/migrate_job_compensation_checked.py`, `utils/backend/database/init_db.py`, `utils/backend/database/operations.py`, `utils/backend/recommend/compensation.py`, `utils/backend/recommend/service.py`, `utils/backend/scrapers/scraping_service.py` |
| Coverage test | 100% fraction selects verdict-less jobs even when many already have a verdict; no top-N cap | `tests/recommend/test_analyze_gapfill.py` |
| Skills-reuse test | Second analyze run does not re-extract skills for jobs that already have them | `tests/recommend/test_recommend_service.py` |
| Compensation-flag test | A checked no-pay job is not re-queried on the next run | `tests/recommend/test_compensation.py` |
| Docs updates | Coverage control, skills reuse, and the new column reflected in docs | `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/database.md`, `docs/checklist.md` |
