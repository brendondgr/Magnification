# Shared Data Root — Fix Profile/Config Loss Across Worktrees

## 1. Introduction

The user reported that the recommendation **profile** (and, by the same mechanism, job/LLM/runtime
config) "constantly gets deleted on app resetting." Investigation (code read + on-disk evidence)
found the true trigger: it isn't deleted at all — a fresh, disconnected SQLite database is created
every time the app runs from a different **git worktree**.

`utils/backend/database/config.py` resolves the project root as `Path(__file__).resolve().parents[3]`
and derives `DATABASE_PATH` from it. `data/` is (correctly) gitignored, but **git worktrees do not
share gitignored/untracked files** — each worktree is a separate directory on disk with its own
empty `data/`. Since `__file__` lives inside whichever checkout is running, every worktree computes
its *own* project root and therefore its own brand-new `data/magnificiation.db`. This repo's own
workflow (`docs/workflow.md`, and this task's own instructions) recommends a worktree for every
non-trivial change, so this triggers routinely — not just for the user but for every future feature
branch.

On-disk proof (sizes of `data/magnificiation.db` before this fix):

```
main checkout                                        5,308,416 bytes (real data + profile)
.claude/worktrees/pipeline-reorder-dedup-filter/...     53,248 bytes (empty schema only)
.claude/worktrees/profile-blocklists/...                 53,248 bytes
.claude/worktrees/profile-build-generation/...           53,248 bytes
.claude/worktrees/profile-llm-instructions/...            53,248 bytes
.claude/worktrees/rag-llm-recommendation/...              53,248 bytes
.claude/worktrees/reco-pipeline-scoring/...                53,248 bytes
.claude/worktrees/skills-quick-add/...                    53,248 bytes
.claude/worktrees/ui-hover-animations/...                 53,248 bytes
.claude/worktrees/ui-reco-refinements/...                184,320 bytes (had its own test data)
```

The exact same `__file__`-relative root computation appears in five more modules that load the
gitignored runtime JSON configs (`jobs_config.json`, `llm_endpoint_config.json`,
`runtime_config.json`), so job filters, the LLM endpoint, and runtime toggles reset the same way.
It is one root cause in six places, not six separate bugs.

The fix: resolve the project root once, using `git`'s notion of the **common `.git` directory**
(shared by the main checkout and every worktree), with a safe fallback to today's behavior when
`git` is unavailable (e.g. a packaged install with no `.git`). Every module that currently computes
its own `__file__`-relative root switches to this single shared resolver, so the DB and all runtime
config always live in one place — the main checkout's `data/` and `config/` — regardless of which
worktree the app is launched from.

---

## 2. Gaps & Unanswered Questions

- **Stray per-worktree `data/`/`config/` directories left behind by past worktrees.** These are
  gitignored, harmless, and unrelated to git history. *Assumption*: leave them in place (out of
  scope to clean up someone else's worktree filesystem state); the fix only changes where *new*
  reads/writes go.
- **Git binary unavailable / non-git deployment (e.g. a future packaged install).** *Assumption*:
  fall back to the current `parents[N]`-from-`__file__` behavior, so behavior for a plain,
  non-worktree checkout is unchanged and nothing regresses.
- **`utils/LocalLLM/utils/config_initializer.py`'s `llm_config.json`** (the bundled llama-server
  manager's own config) uses a different, self-contained resolution scheme and is explicitly
  documented as intentionally separate from the app's `config/llm_endpoint_config.json`
  (`utils/backend/llm/config.py` docstring). *Assumption*: out of scope — `LocalLLM` is a
  self-contained library by design (`docs/structure.md`), not part of this shared-root fix.
- **The "Clear Database → Full" feature intentionally deletes the profile.** This is a documented,
  tested, opt-in UI action (`docs/plans/clear-db-options.md`), unrelated to the worktree bug.
  *Assumption*: no change needed there; noted so it isn't confused with this fix during review.

**Addendum — discovered during Step 2 validation:** running the fixed test suite from this
worktree flipped the real profile's `is_active` flag to `0` in the shared main `data/magnificiation.db`
(`GET /api/profile` would have reported `exists: false`). Root cause:
`tests/database/test_profile_analysis.py::test_profile_crud_and_single_active_invariant` exercised
the single-active-profile invariant directly against whatever engine `database/config.py` points
to, with no isolation and no snapshot/restore of a pre-existing active profile — unlike every other
DB-touching test in the suite. Before this fix, that was silently harmless because each worktree had
its own disposable empty DB; after this fix, all worktrees share the real DB, so the same test
became destructive. The real profile's data was recovered (`set_active_profile(1)`, content
unaffected, only `is_active` needed restoring) and the test itself is now fixed in the same step —
isolated against an in-memory SQLite engine via the `temp_db` fixture pattern already used by
`tests/database/test_clear_jobs.py`, so it can no longer touch real data regardless of where it runs.

---

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Worktree + shared path-resolution utility
- **Locations**: new `utils/backend/paths.py` (`get_project_root()` function); new
  `tests/backend/test_paths.py`.
- **Rationale**: Every affected module needs the *same* answer to "where is the project root,"
  computed once and shared, instead of six independent `__file__`-relative computations that
  silently diverge per worktree. `get_project_root()`:
  - Runs `git rev-parse --git-common-dir` with `cwd` set to the calling file's directory, joins the
    (possibly relative) result against that `cwd`, and resolves it — the common dir is shared by
    the main checkout and every worktree, so its parent is the one true project root.
  - Falls back to today's `parents[N]`-from-`__file__` computation if `git` is missing, times out,
    or the repo has no `.git` (`OSError`/`subprocess.SubprocessError`/non-zero exit).
  - Is memoized (`functools.lru_cache`) so each process resolves it once.
  - Create the work on branch/worktree `shared-data-root` per repo convention.
- **Action**: Undergo the verification/tests/validation process for this phase — new unit tests
  cover: (a) the git-based path resolves to a directory containing `pyproject.toml` and `.git`;
  (b) the fallback path is exercised (monkeypatch `subprocess.run` to raise) and matches the
  previous hardcoded computation. Run `uv run pytest tests/backend/test_paths.py`. Once validated,
  commit stating: `Shared Data Root (1/3) Complete: add get_project_root() git-common-dir resolver + tests.`

#### Step 2: Point the database + all runtime config loaders at the shared root
- **Locations**:
  - `utils/backend/database/config.py` — `PROJECT_ROOT` (replace the `parents[3]` line with
    `get_project_root()`); this is the fix for the reported profile-loss bug.
  - `utils/backend/scrapers/job_filter.py` and `utils/backend/scrapers/task_generator.py` —
    `CONFIG_DIR`/`JOBS_CONFIG_PATH` (both currently duplicate the identical `parents[3]`
    computation; both switch to `get_project_root() / "config"`).
  - `utils/backend/routes/config_routes.py` — `CONFIG_PATH`.
  - `utils/backend/llm/config.py` — `CONFIG_PATH` for `llm_endpoint_config.json`.
  - `utils/backend/recommend/runtime_config.py` — `CONFIG_PATH` for `runtime_config.json`.
  - `tests/database/test_profile_analysis.py` — isolate against an in-memory SQLite engine (the
    `temp_db` fixture pattern from `tests/database/test_clear_jobs.py`) instead of the real engine;
    required per the addendum above.
- **Rationale**: These five modules have the identical defect as the database config — resolving
  gitignored file locations relative to whichever checkout's `__file__` happens to be running.
  Fixing only the database would still leave job filters, LLM endpoint settings, and runtime
  toggles resetting per worktree, which is the same user-visible symptom ("my settings keep
  disappearing") under a different name.
- **Action**: Undergo the verification/tests/validation process for this phase — existing tests in
  `tests/database/`, `tests/scrapers/`, `tests/llm/`, `tests/recommend/`, and
  `tests/test_config_loading.py` must still pass unchanged (path *values* are unaffected when run
  from the main checkout, only worktree behavior changes). Add an assertion-style check (extend
  `tests/backend/test_paths.py`) that every one of these five `CONFIG_PATH`/`DATABASE_PATH`
  constants resolves under the same `get_project_root()` — i.e., they can never diverge again. Run
  the full suite (`uv run pytest`, deselecting the pre-existing
  `tests/test_config_loading.py::test_workflow_config_loading` live-network hang noted in project
  memory) **and confirm the real `data/magnificiation.db` and `config/*.json` mtimes/content are
  unchanged before vs. after** — this is now load-bearing since every worktree shares the real DB.
  Then `uv run python -c "import app; print('ok')"` to confirm the Flask app still imports and
  initializes cleanly. Once validated, commit stating:
  `Shared Data Root (2/3) Complete: wire database + job/LLM/runtime config loaders to the shared project root; isolate test_profile_analysis.py from the real DB.`

#### Step 3: Manual worktree verification + docs
- **Locations**: manual verification only (no new source files); doc updates in
  `docs/workflow.md` (note the shared-root behavior under Environment/Config files),
  `docs/checklist.md` (new "Shared Data Root" Definition-of-Done section), and this plan doc.
- **Rationale**: The bug was only proven with a live worktree, so the fix must be proven the same
  way — start the app from an existing worktree (e.g. `.claude/worktrees/ui-hover-animations`) and
  confirm it now reads/writes the **main checkout's** `data/magnificiation.db` (profile present) and
  `config/*.json`, not a fresh empty one. Docs must record this behavior so future contributors
  don't reintroduce a `__file__`-relative path.
- **Action**: Undergo the verification/tests/validation process for this phase —
  1. `uv run python -c "from utils.backend.database.config import DATABASE_PATH; print(DATABASE_PATH)"`
     from the main checkout and from `.claude/worktrees/ui-hover-animations` must print the **same**
     absolute path.
  2. Launch the app from the worktree checkout, `GET /api/profile`, and confirm the existing
     profile (not `{"exists": false}`) is returned.
  3. Full `uv run pytest` green; `import app` clean.
  Once validated, commit stating: `Shared Data Root (3/3) Complete: verify cross-worktree persistence + update docs/checklist.`
  Then merge the `shared-data-root` worktree branch into `main`, resolving any conflicts, per
  `docs/workflow.md`'s git workflow (commit only — do not push unless asked).

---

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Shared root resolver | `get_project_root()` — git-common-dir based, memoized, with `__file__`-relative fallback | `utils/backend/paths.py` |
| Path resolver tests | Unit tests for the git-based path, the fallback path, and cross-module consistency | `tests/backend/test_paths.py` |
| Database path fix | `DATABASE_PATH`/`PROJECT_ROOT` sourced from the shared resolver | `utils/backend/database/config.py` |
| Job config path fix | `JOBS_CONFIG_PATH`/`CONFIG_DIR` sourced from the shared resolver (de-duplicated) | `utils/backend/scrapers/job_filter.py`, `utils/backend/scrapers/task_generator.py` |
| Jobs-config route path fix | `CONFIG_PATH` sourced from the shared resolver | `utils/backend/routes/config_routes.py` |
| LLM endpoint config path fix | `CONFIG_PATH` sourced from the shared resolver | `utils/backend/llm/config.py` |
| Runtime config path fix | `CONFIG_PATH` sourced from the shared resolver | `utils/backend/recommend/runtime_config.py` |
| Test isolation fix | Isolate the single-active-profile CRUD test against an in-memory engine so it can never mutate the real DB | `tests/database/test_profile_analysis.py` |
| Docs | Shared-root behavior documented; checklist Definition-of-Done section | `docs/workflow.md`, `docs/checklist.md` |
