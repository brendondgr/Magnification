# Analyze Matches — Honor "Jobs through the LLM" Coverage

## 1. Introduction

The **New Jobs → Analyze Matches** action is meant to run the analyzed jobs through the LLM for a
personalized fit, governed by the Options → Runtime **"Jobs through the LLM"** slider
(`llm_fraction`, labeled *LLM coverage*). The intended contract is: **100% = every job goes through
the LLM (if an endpoint is available); 50% = only the top 50% by embedding/rerank score.** In
practice the button only sends "~20%" of jobs to the LLM regardless of the slider.

**Root cause:** `analyzeJobs()` calls `/api/recommend/analyze/start` in gap-fill mode
(`llm_only_missing=True`). Inside `service._llm_rerank`, the `llm_fraction` is applied to
**`candidates` = only the jobs still missing a verdict**, not to the full analyzed set. So once most
jobs already have a verdict, the fraction is a share of the small remaining gap — e.g. 100% of the
20% that are missing, which reads as "20%". At 50% it would keep 50% *of the gap*, not the top 50%
of all jobs.

**Approach:** apply `llm_fraction` (and the optional `top_n_llm` cap) over the **full** analyzed set
to pick the coverage set (top `ceil(fraction × N)` by semantic+bm25), and *then* gap-fill within that
coverage set. Per the user's decision, the button stays **gap-fill within coverage**: 100% guarantees
every job ends up with an LLM fit while repeat clicks stay cheap; jobs that already have a verdict are
not re-queried. This is a localized change in `utils/backend/recommend/service.py`; the frontend
slider, config, and endpoints already exist and are correct.

## 2. Gaps & Unanswered Questions

- **Re-run policy at 100%** — *Resolved by the user:* **gap-fill within coverage** (select the top
  `fraction × N`, only spend an LLM call on those lacking a verdict). Not "always fresh".
- **Where the fraction denominator should live** — *Assumption:* the coverage set is computed over
  **all** analyzed (non-ignored) jobs, before the gap-fill/missing filter. This is the whole fix.
- **`top_n_llm` ordering** — *Assumption:* `top_n_llm` remains an absolute cost cap applied to the
  coverage set **before** the missing filter (unchanged semantics; it only ever lowers the count).
- **Scheduler / scrape path** — *Assumption:* the daily bot and manual scrape reach the same
  `analyze_jobs → _llm_rerank`, so they inherit the corrected coverage automatically; no separate
  change needed.
- **Frontend / config / docs** — *Assumption:* no UI change is required; the slider already writes
  `llm_fraction` and defaults to 1.0. Only doc prose that describes the coverage math needs a touch-up.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Worktree + plan doc
- **Locations**: git worktree `.claude/worktrees/analyze-matches-llm-coverage` (branch
  `analyze-matches-llm-coverage`); `docs/plans/analyze-matches-llm-coverage.md` (this file).
- **Rationale**: non-trivial work happens on a feature branch per the repo git workflow; the plan is
  the source of truth for the phases and their validation.
- **Action**: Undergo the verification/validation process for this phase (worktree exists, baseline
  `tests/recommend` subset green). Once validated, commit stating: *Analyze Matches LLM coverage (1/3)
  Complete: Worktree + plan doc.*

### Step 2: Backend coverage fix + tests
- **Locations**: `utils/backend/recommend/service.py` —
  - Add a `_select_llm_indices(analyses, runtime, llm_only_missing)` helper that computes the coverage
    set over **all** analyses (top `ceil(llm_fraction × N)` by semantic+bm25), applies the `top_n_llm`
    absolute cap, then drops jobs that already have a verdict when `llm_only_missing` is set.
  - Rewrite the candidate/fraction/cap block in `_llm_rerank` to call `_select_llm_indices` (removing
    the current "fraction over `candidates`" logic) and update its docstring.
  - Update the `n_for_llm` progress-count computation in `analyze_jobs` to reuse
    `_select_llm_indices` so the popup's "LLM fit verdict on N of M job(s)…" message is accurate.
  - Tests: `tests/recommend/test_analyze_gapfill.py` — add (a) *fraction applies to the full set*:
    top-relevance jobs missing verdicts, low-relevance jobs having verdicts, `llm_fraction=0.5`
    selects the top 50% of **all** jobs then gap-fills; (b) *100% guarantees full coverage cheaply*:
    some jobs pre-verdicted, `llm_fraction=1.0` only fills the missing ones and preserves the rest.
    Confirm the existing `tests/recommend/test_llm_features.py` fraction/cap tests still pass unchanged.
- **Rationale**: this is the actual defect — the fraction must be a share of the whole job set, not of
  the missing gap, so the slider means what the Options copy says.
- **Action**: Undergo the verification/tests/validation process for this phase (`pytest
  tests/recommend`, `python -c "import app"`, and a scripted end-to-end call of `_select_llm_indices`
  / `_llm_rerank` proving the ~20%→100% behavior with a fake client). Once validated, commit stating:
  *Analyze Matches LLM coverage (2/3) Complete: llm_fraction now covers the full analyzed set, then
  gap-fills.*

### Step 3: Docs + merge
- **Locations**: `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md` (coverage/
  gap-fill prose), and `docs/checklist.md` (a new "Definition of Done" section for this change); then
  merge `analyze-matches-llm-coverage` into `main` and remove the worktree.
- **Rationale**: docs are the single source of truth and must describe the corrected coverage math;
  merging delivers the fix on `main`.
- **Action**: Undergo the verification/validation process for this phase (full offline test subset
  green post-merge, `import app` clean, docs updated). Once validated, commit stating: *Analyze
  Matches LLM coverage (3/3) Complete: docs updated + merged to main.*

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan doc | This phased plan | `docs/plans/analyze-matches-llm-coverage.md` |
| Coverage selector | `_select_llm_indices` helper computing coverage over the full set, then gap-fill | `utils/backend/recommend/service.py` |
| `_llm_rerank` fix | Fraction/cap applied over all analyses via the new helper | `utils/backend/recommend/service.py` |
| Accurate progress count | `analyze_jobs` reuses the selector for the "N of M" popup message | `utils/backend/recommend/service.py` |
| Coverage+gap-fill tests | Fraction-over-full-set + 100%-full-coverage gap-fill cases | `tests/recommend/test_analyze_gapfill.py` |
| Doc updates | Corrected coverage/gap-fill prose + checklist DoD | `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/checklist.md` |
