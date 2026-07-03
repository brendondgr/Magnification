# Project Checklist — Magnification

## Initialization (this overhaul) — Definition of Done

### Canonical docs
- [x] `docs/` exists and is the source of truth
- [x] `docs/documentation.md`
- [x] `docs/structure.md`
- [x] `docs/workflow.md`
- [x] `docs/checklist.md`
- [x] `docs/plans/`
- [x] `docs/skills/global-project-rules/SKILL.md`
- [x] Web docs: `architecture.md`, `routes.md`, `component-map.md`, `data-flow.md`, `deployment.md`, `design-system.md`, `api-contract.md`

### Skills
- [x] `planner` migrated to `docs/skills/planner/`
- [x] `repository-structure` migrated (with `SETUP.md` + `structures/`)
- [x] `website-architecture` migrated (with `SETUP.md`)
- [x] `accessibility-mobile` migrated
- [x] Skill frontmatter `name:` matches folder name

### Agent pointers
- [x] Claude Code pointers (`.claude/skills/`)
- [x] OpenAI Codex pointers (`.agents/skills/`)
- [x] Cursor pointers (`.cursor/rules/`)
- [x] Each pointer references `docs/skills/global-project-rules/SKILL.md` + its canonical skill

### Cleanup
- [x] `bdgrSkills/` starter kit removed after migration
- [x] Superseded `docs/project_structure.md` and `docs/frontend_structure.md` removed (folded into `structure.md` / `component-map.md`)
- [x] `readme.md` consolidated into `README.md`
- [x] No competing sources of truth remain

### Verification
- [x] Final tree inspected
- [x] All pointer targets verified to exist (stdlib verification of `tests/docs/test_skill_pointers.py` assertions — all pass)
- [x] App code untouched by this overhaul; `app.py`, routes, and DB modules pass `py_compile`
- [ ] Full Flask import/run smoke test — **deferred:** the local `.venv` has no deps installed and `uv sync` can't build `regex` offline (missing `Python.h`). Run `uv sync --dev && uv run pytest && uv run python -c "import app"` in a provisioned environment.

## RAG + LLM Recommendation Overhaul — Definition of Done

Plan: `docs/plans/rag-llm-recommendation.md`. Delivered on branch `rag-llm-recommendation`
(worktree), committed per phase, merged to `main`.

- [x] (1/7) Dependencies (fastembed, rank-bm25, pypdf, requests) + plan doc
- [x] (2/7) `Profile` + `JobAnalysis` tables + CRUD + tests
- [x] (3/7) OpenAI-compatible LLM client + endpoint/runtime config + Options API + tests
- [x] (4/7) Résumé→profile builder + Profile API + Profile & Options panels + tests (verified in-browser)
- [x] (5/7) Gazetteer skill extraction + parallel LinkedIn description fetch + tests
- [x] (6/7) Hybrid RAG ranker + embed-on-retrieve pipeline + match-score UI + tests (real bge model verified)
- [x] (7/7) LLM verdict/rationale (top-N) + LLM keyword generation + multi-country/job-type Find Jobs + merge
- [x] All tests green (`pytest`), `import app` clean; UI panels verified via preview tools
- [ ] **Live end-to-end with a real LLM endpoint** — not exercised (no endpoint configured in this env);
  all LLM paths are covered by mocked tests. Configure an endpoint in Options to use the LLM features.

## UI/UX Refinements — Definition of Done

Plan: `docs/plans/ui-recommendation-refinements.md`. Delivered on branch `ui-reco-refinements`
(worktree), committed per phase, merged to `main`.

- [x] (1/7) Worktree + plan doc
- [x] (2/7) New Jobs cards: removed company icon, relocated match % with breakdown popover +
  color tiers, YYYY-MM-DD dates (verified in-browser)
- [x] (3/7) Résumé drag-and-drop zone + "Build Profile (LLM)" action (verified in-browser)
- [x] (4/7) Unified searchable country selector + optional City/Remote (verified in-browser)
- [x] (5/7) Find Jobs prefills Title/Description keywords from the active profile, refreshes on open
  (verified in-browser)
- [x] (6/7) Live step-by-step scraping activity feed (server event log + UI feed) + tests
  (verified end-to-end against the real pipeline)
- [x] (7/7) LLM compensation extraction (recovers pay from descriptions) + runtime toggle + tests + merge
- [x] All tests green (`pytest`), `import app` clean; UI verified via preview tools
- [ ] **LLM compensation live** — the extractor is covered by mocked-client tests; recovering real
  pay requires an enabled LLM endpoint (toggle: Options → Runtime → "LLM compensation extraction").

## Pipeline Reorder + LLM-Weighted Scoring — Definition of Done

Plan: `docs/plans/reco-pipeline-scoring.md`. Delivered on branch `reco-pipeline-scoring`
(worktree), committed per phase, merged to `main`.

- [x] (1/5) Worktree + plan doc
- [x] (2/5) LinkedIn description fetch forced **serial** (1 at a time) to stop rate-limiting + test
- [x] (3/5) Analysis reorder: keyword-filtered remainder → embed → semantic+bm25 top-30 → LLM
  verdict folded into `rag_score` (`llm` weight 0.40, renormalized when absent); 2-3 sentence
  company-aware rationale; `top_n_llm=30`, `enable_llm_rerank` default on + tests
- [x] (4/5) Score-weight sliders (5, incl. LLM) with a live total that must equal exactly 1.00;
  Save blocked otherwise; LLM-fit bar in the breakdown (verified in-browser)
- [x] (5/5) Docs + merge
- [x] All tests green (`pytest`, offline subset), `import app` clean; weights UI verified via preview
- [ ] **LLM verdict live** — the fold + rationale are covered by mocked-client tests; real verdicts
  need an enabled endpoint (Options → LLM Endpoint) + "LLM re-rank" on.

## Clear Database — Scoped Options — Definition of Done

Plan: `docs/plans/clear-db-options.md`. Delivered on branch `clear-db-options`
(worktree), committed per phase, merged to `main`.

- [x] (1/3) `clear_jobs_database()` op (deletes analyses+statuses+jobs, keeps
  profiles) + `scope`-aware `/api/database/clear` (`full` default, `jobs`) +
  isolated in-memory test (`tests/database/test_clear_jobs.py`)
- [x] (2/3) Sidebar "Clear Database" slides down to two scoped buttons —
  "Full Database (Jobs + Profile)" and "Jobs Database" — with scope-specific
  confirm + toast (verified in-browser: options slide down, `jobs` keeps the
  profile, `full` wipes it, bad scope → 400)
- [x] (3/3) Docs (`api-contract.md`, this checklist, plan doc) + merge
- [x] All tests green (offline subset), `import app` clean; UI verified via preview

## UI Hover & Movement Animations — Definition of Done

Plan: `docs/plans/ui-hover-animations.md`. Delivered on branch `ui-hover-animations`
(worktree), committed per phase, merged to `main`.

- [x] (1/7) Worktree + plan doc
- [x] (2/7) Header, sidebar, and mobile nav hover/focus animations
- [x] (3/7) New Jobs grid, card lift, and action-button hover animations
- [x] (4/7) Tracker kanban polish + Job Detail panel/timeline hover animations
- [x] (5/7) Find Jobs modal + Match Breakdown popup hover animations
- [x] (6/7) Profile panel + Options panel hover animations
- [x] (7/7) Motion section of `docs/design-system.md` documented + merge
- [x] All tests green (`pytest`), `import app` clean; every panel/modal verified in-browser via
  computed styles/classes on the generated `style-hover`/`style-active`/`style-focus` rules
  (screenshot tooling was unavailable in this environment, so verification used DOM/stylesheet
  inspection instead of visual screenshots)

## Profile Blocklists & Scoped Keyword Groups — Definition of Done

Plan: `docs/plans/profile-blocklists.md`. Delivered on branch `profile-blocklists`
(worktree), committed per phase, merged to `main`.

- [x] (1/6) Worktree + plan doc
- [x] (2/6) `Profile.blocked_companies` + `title_blocklist` columns + scoped `keyword_groups`
  (`scopes` ⊆ title/description) + idempotent migration + CRUD/normalizer tests
- [x] (3/6) `profile_filter.py` pure block predicates + `job_filter.apply_profile_filters`
  (retroactive, one-directional) + scope-aware `ranker.keyword_group_score` + tests
- [x] (4/6) `POST /api/profile` accepts blocklists + re-applies filters on save;
  `POST /api/profile/block-company` (retroactive hide); isolated in-memory API tests + docs
- [x] (5/6) Per-card + detail-panel **Block** button (left of ignore) with instant hide
  (verified in-browser: blocking a company hid its cards + persisted + set ignore=1)
- [x] (6/6) Profile panel: **Blocked Companies** + **Keyword Title Blocklist** tag-lists +
  per-group **Title/Description** scope toggles; docs + merge (verified in-browser: scope
  toggle persists `scopes:["title"]`, saving a title-block hid the matching job, hard-filter
  hides jobs missing a title-scoped group's term)
- [x] All tests green (`pytest`), `import app` clean; UI verified via preview tools

## Profile Model Instructions — Definition of Done

Plan: `docs/plans/profile-llm-instructions.md`. Delivered on branch `profile-llm-instructions`
(worktree), committed per phase, merged to `main`.

- [x] (1/2) `Profile.llm_instructions` Text column + idempotent migration; build-prompt
  injection (`build_profile_from_text(..., instructions)`); `/api/profile/build` accepts
  `instructions` (falls back to the saved value); save whitelist + serialization + tests
- [x] (2/2) Profile panel **Model Instructions** textarea above the résumé section; state /
  load / save / rebuild wiring; docs + merge (verified in-browser: renders above the résumé
  section, round-trips through save/load, and is sent to the build endpoint)
- [x] All tests green (`pytest`), `import app` clean; UI verified via preview tools

## Skills Quick-Add — Definition of Done

Plan: `docs/plans/skills-quick-add.md`. Delivered on branch `skills-quick-add` (worktree),
committed per phase, merged to `main`.

- [x] (1/3) `POST /api/profile/add-skill` endpoint (case-insensitive de-dupe, creates a default
  profile if none exists) + isolated in-memory API tests + docs
- [x] (2/3) Job detail panel's "Skills the job wants you lack" chips are clickable —
  `addSkillToProfile(skill, jobId)` optimistically adds to `profile.skills` and moves the skill
  from that job's `skill_match.missing` to `.matched`, reverting both on a failed save (verified
  in-browser: click moves the chip and the skill appears in `GET /api/profile` and the Profile
  panel)
- [x] (3/3) `rebuildProfile()` unions `skills` (like the existing `blocked_companies` union) so a
  résumé rebuild never drops a click-added skill; Profile panel Skills list caps at 20 with a
  "Show all (N)" / "Show less" toggle (verified in-browser: 25 seeded skills render 20 + the
  toggle expands/collapses); docs + merge
- [x] All tests green (`pytest`), `import app` clean; UI verified via preview tools
- [ ] **Skills union on a real LLM rebuild** — not exercised live (no LLM endpoint configured in
  this environment); the union logic mirrors the already-shipped `blocked_companies` union
  verbatim and is exercised for `add-skill` + save/load via tests and in-browser checks.

## Shared Data Root — Definition of Done

Plan: `docs/plans/shared-data-root.md`. Delivered on branch `shared-data-root` (worktree),
committed per phase, merged to `main`.

Fixes the reported "profile constantly gets deleted" bug: `data/magnificiation.db` and every
gitignored `config/*.json` were resolved via `Path(__file__).resolve().parents[N]`, which points at
whichever checkout is running — git worktrees don't share gitignored files, so every worktree got
its own empty, disconnected database/config (proven on-disk: main checkout's DB was 5.3 MB vs. 53 KB
in nine sibling worktrees).

- [x] (1/3) `utils/backend/paths.get_project_root()` — resolves the project root via
  `git rev-parse --git-common-dir` (shared by the main checkout and every worktree), with a
  `__file__`-relative fallback when git is unavailable; memoized; unit tests
  (`tests/backend/test_paths.py`)
- [x] (2/3) `utils/backend/database/config.py`, `utils/backend/scrapers/job_filter.py`,
  `utils/backend/scrapers/task_generator.py`, `utils/backend/routes/config_routes.py`,
  `utils/backend/llm/config.py`, `utils/backend/recommend/runtime_config.py` all wired to the
  shared resolver; cross-module consistency test added. **Also fixed in this step:**
  `tests/database/test_profile_analysis.py` was mutating the real active profile's `is_active` flag
  when run against a non-empty DB (harmless per-worktree before this fix, destructive after, since
  all worktrees now share the real DB) — isolated against an in-memory engine like
  `tests/database/test_clear_jobs.py`; the real profile's `is_active` flag was restored after the
  incident (content was never lost)
- [x] (3/3) Verified `DATABASE_PATH` resolves identically from the main checkout and a worktree;
  launching the app from a worktree serves the real, persisted profile (`GET /api/profile` →
  `exists: true`); docs (`docs/workflow.md`) updated with the shared-root + test-isolation rules;
  merged to `main`
- [x] All tests green (`pytest`, excluding the pre-existing live-network hang noted in
  `docs/workflow.md`), `import app` clean; real `data/`/`config/` content verified unchanged
  before/after the full suite run

## All Jobs LLM Fitting — Definition of Done

Plan: `docs/plans/all-jobs-llm-fitting.md`. Delivered on branch `all-jobs-llm-fitting`
(worktree), committed per phase, merged to `main`.

Requirement: **every** analyzed job goes through LLM Fitting, not just a select few (was: only
the top `top_n_llm` = 30 by `semantic+bm25`).

- [x] (1/5) Worktree + plan doc
- [x] (2/5) `service._llm_rerank` verdicts **all** analyzed jobs by default; `top_n_llm`
  repurposed as an optional cost cap (`0`/absent/negative = all jobs, `N>0` = top-N); runtime
  default `top_n_llm=0`; ranker/service docstrings updated; all-jobs test added, cap test kept
- [x] (3/5) Options Runtime UI: default `top_n_llm=0`, "LLM top-N (0 = all)" input (`min=0`),
  "LLM re-rank" copy notes it now covers every analyzed job
- [x] (4/5) Docs updated (`recommendation.md`, `data-flow.md`, `api-contract.md`, this checklist)
- [x] (5/5) Full offline suite green + `import app` clean; merged to `main`
- [ ] **LLM fit live on all jobs** — the all-jobs path is covered by mocked-client tests; running
  real verdicts for every job needs an enabled endpoint (Options → LLM Endpoint) + "LLM re-rank"
  on. Note: uncapped fitting issues one LLM call **per analyzed job** — set `top_n_llm` > 0 to cap.

## Systemd Daily Search (LLM-gated) — Definition of Done

Plan: `docs/plans/systemd-daily-search.md`. Delivered on branch
`systemd-daily-search` (worktree), committed per phase, merged to `main`.

Requirement: on computer start-up (and daily), begin the daily search **only if
the LLM is running**; if not, retry every 10 minutes up to 6 times (~1 h), else
skip the day.

- [x] (1/5) Worktree + plan doc
- [x] (2/5) `utils/backend/scheduler` — `check_llm_ready()` (`GET {base_url}/models`),
  `run_daily_search()` (once-per-day stamp guard; LLM re-check every 10 min ×6 then
  give up; runs `execute_full_scraping_workflow` once on first success) + `python -m
  utils.backend.scheduler` CLI (`--check-llm`, `--force`) + 14 offline tests
- [x] (3/5) `deploy/systemd/` oneshot `.service` + boot/daily `.timer` templates +
  `install.sh`/`uninstall.sh`/README; validated with `systemd-analyze --user verify`
- [x] (4/5) Docs updated (`structure.md`, `workflow.md`, `documentation.md`, this
  checklist, plan doc)
- [x] (5/5) Merged to `main`; installed + enabled the user timer from the main
  checkout (`~/.config/systemd/user/`, symlinked into `timers.target.wants`);
  verified `is-enabled=enabled` and next daily elapse `2026-07-04 09:00 EDT`
  (`systemd-analyze calendar`); no live scrape triggered. Not started this session
  — it activates at the next boot (`OnBootSec` + `OnCalendar`).
- [x] Scheduler tests green (`pytest tests/scheduler`), `import app` clean; `--check-llm`
  correctly reports LLM up (exit 0) / down (exit 1) live
- [ ] **Live daily scrape** — not exercised end-to-end (would hit real job boards +
  the LLM). The gate, retry, guard, and scrape-invocation paths are covered by
  mocked tests + a live `--check-llm`; the real scrape runs at the next boot/daily
  trigger when the LLM is up.

## Deferred / Follow-up Work

- [ ] **Migrate web code to `web/`** per `docs/skills/repository-structure/structures/web-interfaces.md` (Mode F). Deferred because the app is working and a frontend rebuild is planned.
- [ ] **React frontend overhaul** — rebuild `utils/frontend` as a React app; re-run `website-architecture` to choose the React stack, and add `ui-frontend` + `ada-compliance` skills at that time.
- [ ] **Add `ruff`** for lint + format; record commands in `docs/workflow.md`.
- [ ] **Add `ada-compliance` skill** when the accessibility audit work begins.
- [ ] **`.env.example`** — add only if/when environment variables are introduced (currently config is JSON-file based).
- [ ] **Reconcile `docs/design-system.md`** — the Color Tokens/Typography/Iconography sections
  still describe an earlier design export; the live tokens are the per-theme `Component.THEMES`
  vars in `index.html` (see the note added to the Motion section in this change).

## Intentionally Retained / Removed

- **Removed:** `bdgrSkills/` (starter kit — selected skills migrated to `docs/skills/`; `ui-frontend` and `ada-compliance` not selected for this pass), `docs/project_structure.md`, `docs/frontend_structure.md`, `docs/readme.md`.
- **Retained:** `docs/database.md`, `docs/job_scraping.md`, `docs/find_jobs.md`, `docs/ui.md` as subsystem deep-dives linked from `docs/documentation.md`; `requirements.txt` as a legacy mirror of `pyproject.toml`; `main.py` (uv default stub).
