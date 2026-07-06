# Auto-Update Match Percentages — Implementation Plan

## 1. Introduction

The New Jobs / Saved cards and the Job Detail panel display a **match percent** derived
from each job's stored `JobAnalysis.rag_score` (a weighted combination of the semantic,
BM25, keyword, skill, and LLM-fit sub-scores). Today those percentages only refresh when
the user clicks **Analyze Matches**, which re-runs the *entire* recommendation pipeline
(job embedding, LLM verdicts, compensation recovery) — an expensive, network/LLM-bound
operation. Two cheaper events currently leave the displayed percentages **stale**:

1. **Changing the score-weight sliders** (Options → Runtime): only the weighting changes,
   yet the stored `rag_score` is not recomputed until a full re-analyze.
2. **Adding/changing profile skills** (the "missing skill" quick-add chips, and the Profile
   panel Save/Rebuild): this changes the `skill` sub-score (and the profile query that feeds
   `semantic`/`bm25`), yet the stored scores are not recomputed.

The approach: add a **lightweight server-side rescore** that recomputes the sub-scores and
`rag_score` **from already-stored analysis artifacts** — reusing the stored per-job
embeddings and extracted skills, and preserving the stored LLM verdicts — with **no job
re-embedding, no LLM calls, and no compensation recovery**. Expose it at
`POST /api/recommend/rescore`, then call it automatically from the frontend after the three
triggering events and refresh the job list so the percentages update on the page. The
existing **Analyze Matches** path already calls `loadJobs()` and needs no change beyond
verification.

## 2. Gaps & Unanswered Questions

- **Embedder availability for a pure weight change.** `semantic` needs the profile query
  embedded. *Assumption*: the model is cached (the user has analyzed before). To stay robust
  offline, `rescore_jobs` will **fall back to a reweight-only pass** (recompute `rag_score`
  from the *stored* sub-scores) if the profile embedding is unavailable, so weight changes
  still take effect without the model. Skill-driven sub-score changes require the embedder,
  which is the normal case.
- **Which profile edits should trigger a rescore?** *Assumption*: skill quick-add
  (`addSkillToProfile`), Profile panel **Save** (`saveProfile`), and runtime-weight **Save**
  (`saveRuntimeOptions`). Rebuild flows into Save, so it is covered on save. Blocklist-only
  edits already refresh via `loadJobs()`; a rescore on save is harmless (scores unchanged).
- **No profile / no analyses yet.** `rescore_jobs` returns `success:true, rescored:0` when
  there are no analyzed jobs, and `success:false` when there is no active profile. The
  frontend treats a non-success rescore as a silent no-op (no error toast) — a user with no
  profile has no match percentages to update.
- **Should rescore only run when weights actually changed on runtime save?** *Assumption*:
  always rescore on runtime save. It is cheap (no LLM/embedding of jobs) and other runtime
  toggles leave scores unchanged, so an unconditional rescore is simplest and correct.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Worktree + plan doc
- **Locations**: git worktree `auto-update-match-percent`; this file
  `docs/plans/auto-update-match-percent.md`.
- **Rationale**: Non-trivial work is done on a feature branch/worktree per the repo git
  workflow, sharing the real `data/` DB via the git-common-dir resolver.
- **Action**: Undergo the verification/validation process for this phase (plan committed,
  `import app` still clean). Once validated, commit stating: `Auto-Update Match % (1/5)
  Complete: Worktree + plan doc`.

### Step 2: Backend `rescore_jobs` service function
- **Locations**: `utils/backend/recommend/service.py` — new `rescore_jobs(profile=None,
  runtime=None)`; reuses `ranker.rank_batch`, `ranker.combined_score`,
  `ranker.build_profile_query`, `embedder.embed_text`, `embedder.from_bytes`,
  `db_ops.get_all_jobs`, `db_ops.get_analysis_for_jobs(..., include_embedding=True)`,
  `db_ops.save_job_analysis`.
- **Rationale**: A single cheap path that recomputes sub-scores + `rag_score` from stored
  embeddings + stored `extracted_skills` against the current profile & weights, preserving
  stored `llm_score`/`llm_rationale`. Only rescores jobs that already have an analysis.
  Falls back to reweight-only (recompute `rag_score` from stored sub-scores) when the profile
  embedding is unavailable. Persists only score fields (never re-writes embeddings/LLM).
- **Action**: Undergo the verification/validation process for this phase (unit-level import,
  `import app` clean). Once validated, commit stating: `Auto-Update Match % (2/5) Complete:
  rescore_jobs service (reuses stored embeddings + LLM verdicts, no re-embed/LLM)`.

### Step 3: Backend `POST /api/recommend/rescore` endpoint
- **Locations**: `utils/backend/routes/recommend_routes.py` — new `rescore()` route calling
  `service.rescore_jobs()`; returns `{success, rescored, profile_id, top}` mirroring
  `analyze`. Guards on an active profile (400 when absent).
- **Rationale**: Gives the frontend a fast endpoint to refresh scores after weight/skill/
  profile edits without the full analyze cost.
- **Action**: Undergo the verification/validation process for this phase (`import app`
  clean; route registered). Once validated, commit stating: `Auto-Update Match % (3/5)
  Complete: /api/recommend/rescore endpoint`.

### Step 4: Frontend auto-refresh wiring
- **Locations**: `utils/frontend/templates/index.html` — add `rescoreJobs()` helper (POST
  `/api/recommend/rescore`, then `loadJobs()` on success, silent no-op otherwise); call it
  from `saveRuntimeOptions` (after save success), `addSkillToProfile` (after the add-skill
  save resolves), and `saveProfile` (after save success). Verify `analyzeJobs` already
  refreshes via `loadJobs()` (no change).
- **Rationale**: Turns the three triggering events into automatic on-page percentage
  updates. The skill quick-add keeps its optimistic single-job update; the follow-up rescore
  + `loadJobs()` replaces it with authoritative recomputed scores across all affected jobs.
- **Action**: Undergo the verification/validation process for this phase (preview tools:
  change weights → percentages shift; add a skill → skill bar + match % shift). Once
  validated, commit stating: `Auto-Update Match % (4/5) Complete: auto-rescore on weight /
  skill / profile save`.

### Step 5: Tests + docs + merge
- **Locations**: `tests/recommend/test_rescore.py` (new — reweight changes `rag_score` from
  stored sub-scores; skill add changes `skill_score`; stored LLM verdict preserved; embeddings
  not rewritten; no-profile / no-analyses guards); docs: `docs/api-contract.md`,
  `docs/data-flow.md`, `docs/recommendation.md`, `docs/checklist.md`. Merge worktree → `main`.
- **Rationale**: Locks in behavior with an isolated in-memory test (per the shared-DB test
  rule) and records the new endpoint/flow in the canonical docs.
- **Action**: Undergo the verification/validation process for this phase (offline test subset
  green, `import app` clean). Once validated, commit stating: `Auto-Update Match % (5/5)
  Complete: tests + docs + merge` and merge to `main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| `rescore_jobs` service | Recompute sub-scores + `rag_score` from stored artifacts; reweight-only fallback; preserve LLM verdicts | `utils/backend/recommend/service.py` |
| Rescore endpoint | `POST /api/recommend/rescore` → `rescore_jobs` | `utils/backend/routes/recommend_routes.py` |
| Frontend auto-refresh | `rescoreJobs()` + calls in `saveRuntimeOptions`, `addSkillToProfile`, `saveProfile` | `utils/frontend/templates/index.html` |
| Rescore tests | Isolated in-memory: reweight, skill-change, LLM preserved, embedding untouched, guards | `tests/recommend/test_rescore.py` |
| Docs | Endpoint contract + data-flow + recommendation notes + checklist entry | `docs/api-contract.md`, `docs/data-flow.md`, `docs/recommendation.md`, `docs/checklist.md` |
</content>
</invoke>
