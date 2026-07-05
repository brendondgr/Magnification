# Plan — LLM Re-analyze Missing (Analyze Matches gap-fill)

## 1. Introduction

"Analyze Matches" on the main page currently re-scores every non-ignored job and, when an
LLM endpoint is enabled, issues an LLM fit verdict for **all** of them on every click. In
practice many jobs still have no LLM fit percentage (the endpoint was off/unreachable at
scrape time), and many are missing a salary/hourly figure that is actually buried in the
description. Because the LLM verdict is the dominant weight in the match score, these gaps
leave the ranking mostly unusable.

This plan changes "Analyze Matches" to be a **gap-filler**: for every non-ignored job it (a)
runs the LLM fit verdict **only on jobs that do not yet have one** (preserving existing
verdicts and avoiding redundant LLM calls), and (b) re-extracts compensation from the
description for any job whose pay is still unspecified. Ignored jobs are always skipped;
saved jobs are included (per the user's decision: "only ignored jobs are excluded"). The
work lives almost entirely in `utils/backend/recommend/service.py`, with a small compensation
call, an endpoint passthrough flag, and a frontend toast update.

## 2. Gaps & Unanswered Questions

- **Saved-job scope** — *Resolved by the user:* only **ignored** jobs are excluded. Both LLM
  fit and compensation extraction run on every non-ignored job, saved included.
- **Force full re-analysis** — a profile change should be able to refresh *all* LLM verdicts,
  not just missing ones. *Assumption:* keep gap-fill as the default (empty body `{}` from the
  button) and add an optional `reanalyze_all` body flag that, when true, re-runs the LLM on
  every job. Low-risk, preserves current power-user behavior.
- **"Analysis on" definition** — *Assumption:* a job "has an LLM analysis" iff its stored
  `JobAnalysis.llm_score` is not `NULL`. `llm_rationale` may be null independently but
  `llm_score` is the fit percentage that drives the score, so it is the authoritative flag.
- **Compensation persistence** — *Assumption:* reuse the existing pattern from the scraping
  pipeline: `extract_compensation_llm(...)` mutates job dicts in place, then persist with
  `db_ops.update_job(id, {"compensation": ...})`. No schema change.
- **No endpoint configured** — *Assumption:* both steps no-op silently (as today) when the LLM
  endpoint is disabled/unreachable; scoring still runs on the non-LLM signals.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Worktree + plan doc
- **Locations**: `docs/plans/llm-reanalyze-missing.md` (this file); worktree
  `llm-reanalyze-missing`.
- **Rationale**: Isolate the change and record the design before touching code, per the repo's
  git + planner rules.
- **Action**: Undergo the verification/validation process for this phase (plan reviewed). Once
  validated, commit stating: LLM Re-analyze Missing (1/5) Complete: Worktree + plan doc.

### Step 2: Gap-fill the LLM fit verdict in the recommendation service
- **Locations**: `utils/backend/recommend/service.py` — `analyze_jobs()` and `_llm_rerank()`.
- **Details**:
  - `analyze_jobs()` already loads existing analyses inside `_ensure_embeddings()`; load the
    same `get_analysis_for_jobs(...)` map once at the top (or thread it through) so we know each
    job's stored `llm_score`/`llm_rationale`.
  - Seed each freshly computed `analysis` dict with the stored `llm_score`/`llm_rationale` for
    jobs that already have a verdict, so the existing verdict is preserved and folded into
    `rag_score` without a new LLM call.
  - Add an `llm_only_missing: bool = True` parameter. `_llm_rerank()` restricts `order` to jobs
    whose (seeded) `llm_score is None` when `llm_only_missing` is true; the existing `top_n_llm`
    cap still applies on top of that subset. When false, behavior is today's full re-rank.
  - Return additional counts in the summary: `llm_analyzed` (number of new verdicts issued).
- **Rationale**: This is the core requirement — every non-ignored job ends up with an LLM fit
  percentage, filled incrementally, without paying for verdicts that already exist.
- **Action**: Undergo the verification/tests/validation process for this phase (unit test on the
  gap-fill selection + `import app`). Once validated, commit stating: LLM Re-analyze Missing
  (2/5) Complete: Analyze fills only missing LLM fit verdicts and preserves existing ones.

### Step 3: Re-extract missing compensation during analyze
- **Locations**: `utils/backend/recommend/service.py` — `analyze_jobs()` (new internal helper,
  e.g. `_recover_compensation(jobs, runtime)`); reuse
  `utils/backend/recommend/compensation.py` (`extract_compensation_llm`, `needs_compensation`)
  and `db_ops.update_job`.
- **Details**:
  - Gated by `runtime["enable_llm_compensation"]` and the endpoint being enabled (mirror the
    scraping-pipeline guard). Targets = non-ignored jobs (already the only jobs in scope) with
    `needs_compensation(j)` true.
  - Extract, then persist each recovered value via `update_job(id, {"compensation": ...})`, and
    update the in-memory job dict so the same run is consistent.
  - Return `compensation_extracted` count in the summary.
- **Rationale**: Recovers pay hidden in descriptions so the UI stops showing "Not specified"
  for jobs that actually state a figure — the second half of the requirement.
- **Action**: Undergo the verification/tests/validation process for this phase (unit test with a
  mocked client + `import app`). Once validated, commit stating: LLM Re-analyze Missing (3/5)
  Complete: Analyze recovers missing compensation from descriptions.

### Step 4: Endpoint passthrough + frontend feedback
- **Locations**: `utils/backend/routes/recommend_routes.py` — `analyze()` (read optional
  `reanalyze_all` from the body, pass `llm_only_missing=not reanalyze_all`);
  `utils/frontend/templates/index.html` — `analyzeJobs()` toast to surface the new counts
  (e.g. "Analyzed N jobs · M new LLM fits · K pay recovered").
- **Rationale**: Wire the new capability end-to-end and give the user visible confirmation of
  how many gaps were filled.
- **Action**: Undergo the verification/tests/validation process for this phase (frontend-wiring
  test + `import app`; in-browser smoke if preview available). Once validated, commit stating:
  LLM Re-analyze Missing (4/5) Complete: Endpoint flag + toast surface gap-fill counts.

### Step 5: Docs + tests + merge
- **Locations**: `tests/recommend/` (new area) or `tests/` — gap-fill selection + compensation
  recovery tests (mocked client, in-memory DB); `docs/data-flow.md`, `docs/api-contract.md`,
  `docs/recommendation.md`, `docs/checklist.md`.
- **Rationale**: Lock behavior with tests and keep the canonical docs in sync per the
  documentation-maintenance rule; then merge to `main`.
- **Action**: Undergo the full verification process (offline test subset green, `import app`
  clean). Once validated, commit stating: LLM Re-analyze Missing (5/5) Complete: Tests + docs +
  merge. Then merge the worktree branch into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Gap-fill LLM rerank | `analyze_jobs` seeds existing verdicts; `_llm_rerank` only scores jobs missing `llm_score` (via `llm_only_missing`) | `utils/backend/recommend/service.py` |
| Compensation recovery in analyze | New `_recover_compensation` step calling `extract_compensation_llm` + `update_job` for non-ignored jobs missing pay | `utils/backend/recommend/service.py` |
| Endpoint flag | `analyze()` reads optional `reanalyze_all` and passes `llm_only_missing` | `utils/backend/routes/recommend_routes.py` |
| Toast counts | `analyzeJobs()` surfaces new LLM-fit + compensation counts | `utils/frontend/templates/index.html` |
| Gap-fill unit test | Only jobs without a stored `llm_score` are sent to the LLM; existing verdicts preserved & folded | `tests/recommend/test_analyze_gapfill.py` |
| Compensation recovery test | Mocked client fills compensation for jobs missing pay, persists via `update_job` | `tests/recommend/test_analyze_compensation.py` |
| Docs update | Data flow, API contract, recommendation, checklist reflect gap-fill analyze | `docs/data-flow.md`, `docs/api-contract.md`, `docs/recommendation.md`, `docs/checklist.md` |
