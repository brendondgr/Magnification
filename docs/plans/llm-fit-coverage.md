# Plan — LLM Fit on All Searches (adjustable coverage, default 1.0)

## 1. Introduction

Every job search — whether a **manual search from the Web UI** (`/api/scrape/start`) or the
**automatic daily bot** (`utils/backend/scheduler/daily_runner.py`) — must run **all** of its
final (kept, non-ignored) jobs through the LLM so each one gets a personalized fit verdict.
Both entry points already funnel through the single `execute_full_scraping_workflow`, whose
post-scrape analysis step calls `analyze_jobs → _llm_rerank`, so the two paths share one code
path and both already honor the recommendation runtime config. The remaining requirement is to
make LLM coverage an **adjustable knob with a default of 1.0** (i.e. 100% of final jobs → LLM),
surfaced in the Options menu.

The approach adds one runtime knob, `llm_fraction` (float in `[0.0, 1.0]`, default `1.0`), to
`DEFAULT_RUNTIME_CONFIG`. `_llm_rerank` selects `ceil(llm_fraction × N)` of its LLM candidates
(ranked by `semantic + bm25`) and composes this with the existing optional `top_n_llm` absolute
cap. At the default `llm_fraction = 1.0` + `top_n_llm = 0`, every analyzed job is sent to the
LLM — unchanged, correct default behavior — while lower fractions let a cost-sensitive user dial
coverage down. The change ripples into the Options Runtime UI, four `docs/` files, and the
recommendation tests. Because both manual and bot searches read the same runtime config, no
per-path wiring is needed beyond the shared `_llm_rerank`.

## 2. Gaps & Unanswered Questions

- **Fraction vs. count knob.** The user asked for an adjustable value "with a default of 1.0",
  which is naturally a *fraction* (1.0 = all). *Assumption*: add `llm_fraction ∈ [0,1]` (default
  1.0) as the primary coverage dial and **keep** the existing `top_n_llm` as a secondary absolute
  cap (non-destructive, backward-compatible with saved configs). They compose: fraction selects
  the top share, then `top_n_llm` (when > 0) further caps the count.
- **Which set the fraction applies to.** *Assumption*: the fraction applies to the LLM
  *candidate* set inside `_llm_rerank` — for a fresh scrape that is every new job (none has a
  prior verdict), so default 1.0 = all new jobs; for the "Analyze Matches" gap-fill it is the
  jobs still lacking a verdict. This matches "run all final jobs through the LLM" on a scrape.
- **Rounding.** *Assumption*: `ceil(fraction × N)` so any non-zero fraction always covers at
  least one job, and `1.0` always covers all. Clamp the value to `[0.0, 1.0]`; treat missing as
  `1.0`.
- **Forcing analysis on regardless of toggles.** *Assumption*: leave the existing master
  toggles (`enable_analysis`, `enable_llm_rerank`) as the on/off switches and let `llm_fraction`
  be the coverage dial. The out-of-the-box defaults (both toggles on, fraction 1.0, endpoint
  enabled) already deliver "all final jobs → LLM"; we do not remove the ability to turn LLM
  re-rank off entirely.

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Worktree + plan doc
- **Locations**: git worktree `.claude/worktrees/llm-fit-coverage` on branch
  `llm-fit-coverage`; this file `docs/plans/llm-fit-coverage.md`.
- **Rationale**: Per `docs/workflow.md`, non-trivial work happens on a feature branch/worktree so
  `main` stays clean and the change merges as one reviewable unit.
- **Action**: Undergo the verification/validation process for this phase (branch/worktree exists,
  plan committed, `import app` still clean). Once validated, commit to GitHub (do **not** push)
  stating: LLM Fit Coverage (1/5) Complete: worktree + plan doc.

#### Step 2: Backend — `llm_fraction` knob + `_llm_rerank` wiring
- **Locations**:
  - `utils/backend/recommend/runtime_config.py` → add `"llm_fraction": 1.0` to
    `DEFAULT_RUNTIME_CONFIG` (with an inline comment: `1.0 = all final jobs → LLM`). Being a new
    default key auto-whitelists it via `_ALLOWED_KEYS`.
  - `utils/backend/recommend/service.py` → `_llm_rerank`: read and clamp `llm_fraction` from
    `runtime` (default 1.0, clamp to `[0,1]`); after building `candidates`, when `fraction < 1.0`
    keep the top `ceil(fraction × len(candidates))` by `semantic + bm25`; then apply the existing
    `top_n_llm` cap. Update the docstring to describe the fraction and its composition with
    `top_n_llm`, and the `"llm"` progress message wording where relevant.
- **Rationale**: `_llm_rerank` is the single gate that decides which jobs receive a verdict; both
  manual and bot searches reach it through `analyze_jobs`, so wiring the knob here covers both
  paths at once. The config default drives first-run behavior (all jobs at 1.0).
- **Action**: Undergo the verification/tests/validation process for this phase — run
  `uv run pytest tests/recommend -q` and `uv run python -c "import app"`; add tests to
  `tests/recommend/test_llm_features.py` asserting (a) `llm_fraction = 1.0`/absent → all
  candidates scored, (b) `llm_fraction = 0.5` of 4 candidates → top 2 by `semantic+bm25`, and
  (c) `llm_fraction` composes with `top_n_llm`. Once validated, commit to GitHub (do **not** push)
  stating: LLM Fit Coverage (2/5) Complete: llm_fraction knob (default 1.0) wired into _llm_rerank.

#### Step 3: UI — Options Runtime coverage control + default
- **Locations**: `utils/frontend/templates/index.html`
  - Add an "LLM coverage" control to the Runtime tab's Parallelism grid (near line ~715, beside
    "LLM top-N"): a `0–100%` slider or number input bound to `rtLlmFraction` /
    `onRtLlmFraction`, labeled to explain `1.0 = every job gets an LLM fit`.
  - Register the getter/setter in the component props block (near line ~1971–1976, beside
    `rtTopN`/`onRtTopN`): `rtLlmFraction: rt.llm_fraction`, `onRtLlmFraction: (e)=>this.rtSet({llm_fraction:+e.target.value})`.
  - Add `llm_fraction:1.0` to the embedded default `runtime:{…}` object (line ~1126) so the
    frontend default agrees with the backend and Save does not drop the key.
  - Update the "LLM re-rank" helper copy (line ~699) to mention the coverage dial.
- **Rationale**: The frontend carries its own copy of the runtime defaults + the Options Runtime
  tab; these must agree with the backend default and expose the new dial, or Save would silently
  omit `llm_fraction` and the UI would never show it.
- **Action**: Undergo the verification/validation process for this phase — `uv run python -c
  "import app"`, and verify the Options Runtime tab renders the new control/default (preview tools
  if available, else DOM/string inspection). Once validated, commit to GitHub (do **not** push)
  stating: LLM Fit Coverage (3/5) Complete: Options Runtime LLM-coverage control + default 1.0.

#### Step 4: Documentation
- **Locations**: `docs/recommendation.md` (LLM verdict / coverage description), `docs/data-flow.md`
  (post-scrape analysis line — both manual + bot honor the fraction), `docs/api-contract.md`
  (`/api/options/runtime` — document `llm_fraction`), `docs/checklist.md` (new "LLM Fit on All
  Searches — Definition of Done" section). Cross-check `docs/find_jobs.md` for any coverage
  wording that needs a pointer.
- **Rationale**: `docs/` is the single source of truth; the new knob and the "all searches →
  LLM" guarantee must be documented alongside `top_n_llm`.
- **Action**: Undergo the verification/validation process for this phase — `uv run pytest
  tests/docs -q` (skill-pointer/doc integrity) stays green. Once validated, commit to GitHub (do
  **not** push) stating: LLM Fit Coverage (4/5) Complete: docs updated for adjustable LLM coverage.

#### Step 5: Full verification + merge
- **Locations**: repo root; merge `llm-fit-coverage` → `main`; remove the worktree.
- **Rationale**: Definition of Done requires the offline suite green and `import app` clean, then
  a clean merge to `main` per the git workflow.
- **Action**: Undergo the verification/tests/validation process for this phase — offline
  `uv run pytest` subset (`tests/recommend`, `tests/database`, `tests/llm`,
  `tests/test_frontend_wiring.py`, `tests/docs`) + `uv run python -c "import app"`; check the
  checklist boxes. Once validated, commit to GitHub (do **not** push) stating: LLM Fit Coverage
  (5/5) Complete: verified + merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan doc | This plan | `docs/plans/llm-fit-coverage.md` |
| `llm_fraction` default | New runtime knob, default `1.0` (= all final jobs → LLM) | `utils/backend/recommend/runtime_config.py` |
| Coverage wiring | `_llm_rerank` applies `llm_fraction` (composes with `top_n_llm`) | `utils/backend/recommend/service.py` |
| Coverage tests | `llm_fraction` 1.0/0.5/compose-with-cap behavior | `tests/recommend/test_llm_features.py` |
| Options UI control | Runtime "LLM coverage" slider/input + default `1.0` + wiring | `utils/frontend/templates/index.html` |
| Docs update | recommendation / data-flow / api-contract / checklist | `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/checklist.md` |
</content>
</invoke>
