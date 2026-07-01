# Plan — All Jobs Through LLM Fitting

## 1. Introduction

Today the recommendation pipeline only sends a **select few** jobs to the LLM for a fit
verdict: `service._llm_rerank` sorts the keyword-filtered remainder by `semantic + bm25` and
keeps just the top `top_n_llm` (default **30**). Every other job is scored without an `llm`
signal, so its `rag_score` is renormalized over the non-LLM weights. The requirement is that
**all** analyzed jobs receive an LLM fit verdict, not just the top-N.

The approach is a small, contained change centered on `_llm_rerank`: process **every**
analyzed (keyword-filtered, non-ignored) job by default. The `top_n_llm` knob is retained but
repurposed as an **optional cost cap** — `0` (or missing/negative) means "no cap → all jobs",
and any positive value keeps the legacy top-N behavior. The default becomes `0`, so out of the
box all jobs go through LLM fitting. Ripple effects touch the runtime config default, the
Options UI slider, the ranker/service docstrings, four `docs/` files, and the recommendation
tests.

## 2. Gaps & Unanswered Questions

- **Keep or remove the `top_n_llm` knob?** *Assumption*: keep it as an optional cap defaulting
  to `0` = all jobs. This satisfies "all jobs by default" while preserving a safety valve for
  API cost/rate control, and avoids destructive removal of a config key + UI control + saved
  configs already on disk. Non-destructive and reversible.
- **Cost / rate-limit blow-up.** Sending every job (potentially hundreds) to the LLM multiplies
  API calls. *Assumption*: acceptable — it is exactly what was requested; `chat_many` already
  parallelizes over `llm_workers`, and the optional cap remains for users who want to limit it.
- **Which jobs count as "all jobs"?** *Assumption*: the same set already analyzed — the
  keyword-filtered, non-ignored remainder (`analyze_jobs` already restricts to these). We do not
  widen the analyzed set; we only remove the top-N gate on the LLM verdict within it.
- **Selection order when a cap is set.** *Assumption*: unchanged (top by `semantic + bm25`),
  used only when `top_n_llm > 0`.

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Worktree + plan doc
- **Locations**: git worktree `../Magnification-all-jobs-llm-fitting` on branch
  `all-jobs-llm-fitting`; this file `docs/plans/all-jobs-llm-fitting.md`.
- **Rationale**: Per `docs/workflow.md`, non-trivial work happens on a feature branch/worktree
  so `main` stays clean and the change merges as one reviewable unit.
- **Action**: Undergo the verification/validation process for this phase (branch exists, plan
  committed, `import app` still clean). Once validated, commit to GitHub (do **not** push)
  stating: All Jobs LLM Fitting (1/5) Complete: worktree + plan doc.

#### Step 2: Backend — LLM fit on all jobs
- **Locations**:
  - `utils/backend/recommend/service.py` → `_llm_rerank`: read `top_n_llm`; when it is `0`,
    missing, or negative, build `order` as **all** analysis indices; when positive, keep the
    existing `sorted(...semantic+bm25...)[:top_n]` cap. Update the function docstring and the
    `"llm"` progress message ("LLM fit verdict on all matches…").
  - `utils/backend/recommend/runtime_config.py` → `DEFAULT_RUNTIME_CONFIG["top_n_llm"]` becomes
    `0`; update its inline comment to document `0 = all jobs`.
  - `utils/backend/recommend/ranker.py` → module docstring wording that says the LLM runs on
    "the top-N / top candidates" updated to reflect all-jobs-by-default (renormalization note
    stays valid for offline jobs).
- **Rationale**: `_llm_rerank` is the single gate that limits the verdict to a select few;
  removing the gate by default is the core of the requirement. The config default drives
  first-run behavior; the docstrings must not keep describing the removed top-N default.
- **Action**: Undergo the verification/tests/validation process for this phase — run
  `uv run pytest tests/recommend -q` and `uv run python -c "import app"`; add a test asserting
  that with `top_n_llm` = `0`/absent **every** job gets an `llm_score`, and keep the existing
  cap test (`top_n_llm: 1` still caps). Once validated, commit to GitHub (do **not** push)
  stating: All Jobs LLM Fitting (2/5) Complete: LLM fit runs on all analyzed jobs by default,
  top_n_llm repurposed as an optional cap.

#### Step 3: UI — Options runtime defaults + labels
- **Locations**: `utils/frontend/templates/index.html`
  - the embedded default `runtime:{…, top_n_llm:30, …}` → `top_n_llm:0`.
  - the "LLM re-rank" toggle helper text (line ~616) and the "LLM top-N" number input label +
    help copy (line ~632) updated to explain `0 = all jobs` and that the verdict now covers all
    matches by default.
- **Rationale**: The frontend carries its own copy of the runtime defaults and the Options
  Runtime tab; these must agree with the backend default and describe the new behavior so the
  UI does not silently re-cap the pipeline to 30 on save.
- **Action**: Undergo the verification/validation process for this phase — `uv run python -c
  "import app"`, and verify the Options Runtime tab renders the new label/default (preview tools
  if available, else DOM/string inspection). Once validated, commit to GitHub (do **not** push)
  stating: All Jobs LLM Fitting (3/5) Complete: Options Runtime default top_n_llm=0 + "0 = all
  jobs" copy.

#### Step 4: Documentation
- **Locations**: `docs/recommendation.md` (Signals table `llm` row + Flow block), `docs/data-flow.md`
  (analysis line ~40), `docs/api-contract.md` (`/api/options/runtime` `top_n_llm` description),
  `docs/checklist.md` (new "All Jobs LLM Fitting — Definition of Done" section).
- **Rationale**: `docs/` is the single source of truth; the "top-N (default 30)" wording is now
  wrong and must describe all-jobs-by-default with the optional cap.
- **Action**: Undergo the verification/validation process for this phase — `uv run pytest
  tests/docs -q` (skill-pointer/doc integrity) stays green. Once validated, commit to GitHub (do
  **not** push) stating: All Jobs LLM Fitting (4/5) Complete: docs updated for all-jobs LLM fit.

#### Step 5: Full verification + merge
- **Locations**: repo root; merge `all-jobs-llm-fitting` → `main`; remove the worktree.
- **Rationale**: Definition of Done requires the full suite green and `import app` clean, then a
  clean merge to `main` per the git workflow.
- **Action**: Undergo the verification/tests/validation process for this phase — full
  `uv run pytest` (offline subset per `docs/workflow.md`) + `uv run python -c "import app"`;
  check the checklist boxes. Once validated, commit to GitHub (do **not** push) stating: All Jobs
  LLM Fitting (5/5) Complete: verified + merged to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan doc | This plan | `docs/plans/all-jobs-llm-fitting.md` |
| All-jobs LLM fit | `_llm_rerank` verdicts every job by default; `top_n_llm` optional cap | `utils/backend/recommend/service.py` |
| Runtime default | `top_n_llm` default `0` (= all jobs) | `utils/backend/recommend/runtime_config.py` |
| Docstring fixes | Ranker/service wording for all-jobs behavior | `utils/backend/recommend/ranker.py`, `service.py` |
| UI defaults + copy | Options Runtime default `top_n_llm=0` + "0 = all jobs" labels | `utils/frontend/templates/index.html` |
| All-jobs test | Assert every job gets `llm_score` when uncapped; cap still works | `tests/recommend/test_llm_features.py` |
| Docs update | recommendation/data-flow/api-contract/checklist | `docs/recommendation.md`, `docs/data-flow.md`, `docs/api-contract.md`, `docs/checklist.md` |
