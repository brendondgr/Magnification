# Project Checklist — Magnification

## Analyze Matches — LLM Fit Reasoning-Token Exhaustion — Definition of Done
Plan: `docs/plans/llm-fit-reasoning-exhaustion.md`. Delivered on branch
`fix-llm-fit-reasoning-exhaustion` (worktree), committed per phase, merged to `main`.

Reported: "Analyze Matches only fits ~2 jobs per run; ~165 still have no LLM fitting."
Root cause: the coverage/gap-fill logic was correct (`llm_fraction = 1.0` selects every
missing-verdict job), but the configured **reasoning** endpoint (`localhost:4000`, `skynet`)
spent its entire `max_tokens` (4092) on hidden reasoning and returned `finish_reason:
"length"` with `content: null` (or truncated JSON), which failed to parse and was dropped —
so only the occasional short-reasoning job landed. A live batch measured **3/10** verdicts in
52s.

- [x] (1/5) Root-cause plan doc + worktree.
- [x] (2/5) `utils/backend/llm/config.py` `disable_thinking` default True (auto-whitelisted);
  `utils/backend/llm/client.py` injects `chat_template_kwargs={"enable_thinking": false}` for
  every call when on (caller override wins; `None` opts out), drops-and-retries + caches on an
  HTTP 400 (strict endpoints keep working), and retries once on empty content; unit tests
  (`tests/llm/test_client.py`). Empirically: `reasoning_effort:low` and `json_object` did **not**
  fix it; disabling thinking did (3/10 → 9-10/10, ~20× faster).
- [x] (3/5) Options → LLM Endpoint "Disable model thinking" toggle + state/save/load wiring +
  embedded default; frontend wiring test. Verified live (worktree preview, DOM): renders ON,
  flips off; no console errors; not saved (shared config untouched).
- [x] Robustness follow-on found during verification: `service._coerce_verdict` tolerates a
  nested `{"score": {"score": N, ...}}` and numeric-string scores (rejects bools; clamps
  0–100) so a malformed-but-non-empty verdict is no longer dropped; `_llm_rerank` uses it;
  tests added.
- [x] (4/5) Docs (`workflow.md` reasoning-endpoint note, `api-contract.md` config key,
  `documentation.md` status, this checklist, plan doc) + **live end-to-end proof**: the real
  gap-fill drove the shared DB from **155/167 → 167/167** LLM fits (all missing filled), each
  pass ~2.4s (vs the original 68s for 2 fits).
- [x] (5/5) Merged to `main`.
- [x] Offline subsets green (`tests/llm`, `tests/recommend` — excluding the pre-existing
  model-cache `test_analyze_api_and_report`, which fails identically on `main`),
  `tests/test_frontend_wiring.py`; `import app` clean.

## Cover-Letter Skill: Structured Output — Definition of Done
Plan: `docs/plans/cover-letter-skill-structure.md`. Delivered on branch
`cover-letter-skill` (worktree), committed per phase, merged to `main`.

Requirement: convert an attached cover-letter Office Skill (the *Winning Formula* + writing rules)
into the generator's structured output, and ensure the skill is **always referenced** — on the
first generation and on every Application-Mode refresh/adjust — because the prior output was
"lackluster."

- [x] (1/5) Plan doc + worktree + resolved design forks (skill lives as a runtime code module, not
  a `docs/skills/` pointer-file skill; template reorder is alignment, prompt injection is enforcement).
- [x] (2/5) `utils/backend/agents/cover_letter_skill.py` — the Winning Formula (hook →
  two-paragraph quantified value proposition → why-this-company → strong close) + writing rules
  (quantify, strong openers, mistakes to avoid) as one runtime source of truth via
  `skill_guidance()`; unit tests (`tests/agents/test_cover_letter_skill.py`).
- [x] (3/5) `prompts.py` folds `skill_guidance()` into `STRATEGIZE_PROMPT`, `WRITE_LETTER_PROMPT`,
  and `CRITIQUE_PROMPT` (always-present system prompts → always referenced, first pass and refine);
  `seed_documents._CLASSIC` reordered to the formula for new installs; quality tests assert the
  formula reaches the writer on a first pass **and** a refine, and that existing anti-parrot /
  stated-interests rules are retained.
- [x] (4/5) Docs (`structure.md`, `data-flow.md`, this checklist) + full offline validation.
- [x] (5/5) Merged to `main`.
- [x] Offline agent/document subset green (`tests/agents`, `tests/documents`, `tests/database`,
  `tests/test_frontend_wiring.py`), `import app` clean.
- [ ] **Best-quality prose needs a real LLM endpoint** — the structure/wiring is covered by
  mocked-client + offline-fallback tests; the model-authored letter is best exercised with an
  enabled, responsive endpoint (Options → LLM Endpoint). The deterministic fallback stays valid
  offline but cannot fully realize the quantified value proposition.

## Per-Page Search + Saved Sort — Definition of Done
Plan: `docs/plans/jobs-search-and-saved-sort.md`. Delivered on branch
`claude/jobs-search-sort-9da760` (worktree), committed per phase, merged to `main`.

Requirement: a search bar on **each** of the New Jobs and Saved pages (independent per page),
doing **keyword** search across the title and **everything else** on the card; and a
**Newest / Match** sort button on Saved (replacing the disliked alphabetical order).

- [x] (1/4) Plan doc + resolved design forks (independent per-page search; Saved defaults Newest).
- [x] (2/4) `utils/frontend/templates/index.html`: `keywordMatch(job, query)` matches across
  title/company/location/compensation/site/description/analyzed-skills (multi-token AND,
  case-insensitive substring); independent `searchNew`/`searchSaved` state + in-page search inputs
  on the New Jobs and Saved headers; Saved `savedSortByMatch` Newest(`createdAt` desc)↔Match(desc,
  no-score last) toggle. The shared sidebar Search box + `matchSearch` removed; Tracker no longer
  filtered by the retired global search. Verified live on the preview (22 saved / 4775 jobs): New
  Jobs search 18→16 (`python`) → 3 (`remote engineer`) → 0 + empty state (gibberish); Saved sort
  Newest→Match ordered 94,94,94,93,92; Saved search 22→13 matching on description/skills; no
  console errors.
- [x] (3/4) Wiring test `tests/test_frontend_wiring.py::test_index_has_per_page_search_and_saved_sort`
  (both inputs, Saved-sort tokens, sidebar-search removal) + docs (`component-map.md`, this checklist).
- [x] (4/4) Merged to `main`.
- [x] `tests/test_frontend_wiring.py` green (10 passed), `import app` clean.

## Analyze Matches: Model Load Failure — Definition of Done
Plan: `docs/plans/fix-embedder-model-load.md`. Delivered on branch
`claude/analyze-matches-model-load-1f2491` (worktree), merged to `main`.

Fixes the reported "Failed — Could not load model BAAI/bge-small-en-v1.5 from any source" on
clicking **Analyze Matches**. Root cause: `embedder.get_model()` let `huggingface_hub`
implicitly attach a **stale/invalid** cached HF token to the (public) model download, which the
Hub rejected and fastembed reported as an unrecoverable load failure; the default cache
(`$TMPDIR/fastembed_cache`) was also wiped on reboot, forcing a re-download every boot.
- [x] `utils/backend/recommend/embedder.py`: `_force_anonymous_hf()` (disable implicit token via
  env var **and** the already-bound `huggingface_hub.constants` flag) + `_resolve_cache_dir()`
  (persistent `~/.cache/fastembed`, overridable with `FASTEMBED_CACHE_PATH`); `get_model()` wires
  both. Public repo → no auth needed; a user's explicit `HF_TOKEN` is unaffected.
- [x] Offline unit tests (`tests/recommend/test_embedder.py`): cache-dir default/env + get_model
  forces anonymous access and the persistent cache without constructing the real model.
- [x] Docs (`docs/workflow.md` cache note corrected, this checklist, plan doc).
- [x] Live proof: with the invalid token still present and no env overrides, `embed_text()`
  downloads once to `~/.cache/fastembed` and succeeds; Analyze Matches completes end-to-end.
- [x] Offline `tests/recommend` + `tests/database` green (the pre-existing, unrelated
  `test_analyze_api_and_report` shared-DB failure is unchanged from `main`), `import app` clean.

## Analyze Matches: Coverage + Redundant Re-work — Definition of Done
Plan: `docs/plans/analyze-matches-coverage-and-rework.md`.
- [x] (1/3) Retire `top_n_llm` so the "Jobs through the LLM" slider is the single coverage
  control — a stale `top_n_llm` no longer silently caps 100% coverage below the verdict-less
  jobs. Cap removed from `_select_llm_indices`, `DEFAULT_RUNTIME_CONFIG`, and the Options UI;
  docs + LLM-features/gap-fill/options tests updated; regression test added.
- [x] (2/3) Reuse stored `extracted_skills` in `analyze_jobs`; only extract jobs missing them
  (force re-extracts). Reuse + force unit tests; recommendation/data-flow docs updated.
- [x] (3/3) `jobs.compensation_checked` column (idempotent migration) + `needs_compensation_recovery`
  so no-pay jobs are queried once, not every run; wired into Analyze Matches and the scrape
  pipeline; database/data-flow docs + predicate/no-pay/force tests.
- [x] Offline recommend/database/llm suites green + `import app` clean; merged to `main`
  (pre-existing offline-only failure `test_analyze_api_and_report` — needs the embedding model
  cached — deselected).

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
  on. Note: full coverage issues one LLM call **per analyzed job** — lower the "Jobs through the
  LLM" (`llm_fraction`) slider to cap cost.

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

## Analyze Matches Progress Popup — Definition of Done

Plan: `docs/plans/analyze-progress-popup.md`. Delivered on branch `analyze-progress-popup`
(worktree), committed per phase, merged to `main`.

Requirement: clicking "Analyze Matches" should bring up a popup showing how many jobs it is
going through and the percent done.

- [x] (1/4) Worktree + plan doc
- [x] (2/4) Backend: `analyze_tasks` in-memory store + `_run_analyze_background` thread +
  `POST /api/recommend/analyze/start` + `GET /api/recommend/analyze/status/<job_id>` (mirrors
  `scrape_routes`); `service.analyze_jobs` progress messages carry job counts (compensation
  candidates, jobs sent to the LLM of the total, summary line). Synchronous `/analyze` retained.
- [x] (3/4) Frontend: `analyzeJobs` → `/analyze/start`, `pollAnalyze` polls `/status` @1s; a
  dedicated popup (percent ring, stage + count message, live activity feed, and an
  Analyzed/New-LLM-Fits/Pay-Recovered stats grid + Done on completion). Verified in-browser
  (DOM inspection): running + completed states render, Done closes, real `/start`+`/status`
  stream live counts ("Embedding 12 jobs…", "Recovering compensation for 3 job(s)…").
- [x] (4/4) Tests (`tests/recommend/test_analyze_progress.py`: start→stream→complete, reanalyze_all
  forwarded, profile-required 400, unknown-job 404, background failure → failed) + docs
  (`routes.md`, `api-contract.md`, `data-flow.md`, `component-map.md`, this checklist) + merge
- [x] Offline subset green (`tests/recommend`, `tests/database`, `tests/test_frontend_wiring.py`),
  `import app` clean
- [ ] **Live full pipeline with an LLM endpoint** — the popup + endpoints are verified end-to-end
  against the real background runner; issuing real LLM verdicts/compensation still needs an enabled
  endpoint (Options → LLM Endpoint).

## LLM Re-analyze Missing (Analyze Matches gap-fill) — Definition of Done

Plan: `docs/plans/llm-reanalyze-missing.md`. Delivered on branch `llm-reanalyze-missing`
(worktree), committed per phase, merged to `main`.

Requirement: "Analyze Matches" should **gap-fill** — re-run the LLM fit verdict across
non-ignored jobs that don't yet have one (the LLM fit is the dominant match weight), and
re-extract hourly/salary pay from the description when it's still unspecified. Only ignored
jobs are excluded (saved jobs are included).

- [x] (1/5) Worktree + plan doc
- [x] (2/5) `analyze_jobs` seeds existing stored LLM verdicts onto fresh analyses (preserved +
  folded into `rag_score`); `_llm_rerank` gains `llm_only_missing` (default True) → issues
  verdicts only for jobs lacking one, honoring `top_n_llm` on the remainder, and returns the
  new-verdict count
- [x] (3/5) `_recover_compensation` extracts pay from the description for non-ignored jobs still
  missing it (gated by `enable_llm_compensation` + endpoint) and persists via `update_job`;
  summary returns `llm_analyzed` + `compensation_extracted`
- [x] (4/5) `/api/recommend/analyze` accepts optional `reanalyze_all` (→ `llm_only_missing`);
  `analyzeJobs` toast surfaces new LLM-fit + compensation counts
- [x] (5/5) Tests (`tests/recommend/test_analyze_gapfill.py`: gap-fill selection, reanalyze-all,
  compensation recovery/persistence, disabled-toggle no-ops) + docs (`api-contract.md`,
  `data-flow.md`, `recommendation.md`, this checklist) + merge
- [x] Offline test subset green (`tests/recommend`, `tests/database`, `tests/test_frontend_wiring.py`),
  `import app` clean
- [ ] **Live gap-fill with a real LLM endpoint** — the gap-fill selection, verdict preservation,
  and compensation recovery are covered by mocked-client tests; filling real verdicts/pay needs an
  enabled endpoint (Options → LLM Endpoint) with "LLM re-rank" + "LLM compensation extraction" on.

## Save Jobs (Saved lane) — Definition of Done

Plan: `docs/plans/save-jobs.md`. Delivered on branch `save-jobs` (worktree), committed per
phase, merged to `main`.

Requirement: a **Save** button next to the Hide button on each job card moves the job out of
New Jobs into a **Saved** tab; saved jobs always appear there, even once Applied.

- [x] (1/3) `Job.saved` column (+ `idx_jobs_saved`) + idempotent `migrate_job_saved` (wired into
  `_run_migrations`) + `set_job_saved()` + `saved` in `_job_to_dict` + `PATCH /api/jobs/<id>/save`;
  isolated in-memory round-trip test (`tests/database/test_job_saved.py`)
- [x] (2/3) Save button (right of Hide) on New Jobs cards + detail panel; `toggleSave` (optimistic
  PATCH); new **Saved** tab (desktop + mobile nav) + grid; saved jobs excluded from New Jobs
  (verified in-browser: Save pulls a card out of New Jobs and into Saved, persists, and a saved
  job stays in Saved **and** appears on the Tracker after being marked Applied)
- [x] (3/3) Docs updated (`api-contract.md`, `database.md`, `component-map.md`, `structure.md`,
  this checklist, plan) + merged to `main`
- [x] All tests green (offline subset: `tests/database` + `tests/test_frontend_wiring.py`),
  `import app` clean; UI verified via preview tools (DOM/eval — screenshot tooling timed out in
  this environment, as noted for prior UI work)

## Auto-Update Match Percentages — Definition of Done

Plan: `docs/plans/auto-update-match-percent.md`. Delivered on branch `auto-update-match-percent`
(worktree), committed per phase, merged to `main`.

Requirement: when the score-weight sliders change (Options → Runtime), when "Analyze Matches"
returns new percent matches, **or when profile skills change** (skill quick-add / Profile save),
the displayed match percentages update on the page automatically.

- [x] (1/5) Worktree + plan doc
- [x] (2/5) `service.rescore_jobs` — recompute sub-scores + `rag_score` from the **stored**
  embedding/`extracted_skills` against the current profile + weights, preserving the stored LLM
  verdict; no job re-embedding, no LLM calls, no compensation recovery; reweight-only fallback
  when the embedder is unavailable
- [x] (3/5) `POST /api/recommend/rescore` endpoint (400 without an active profile) →
  `{success, rescored, profile_id, top}`
- [x] (4/5) Frontend `rescoreJobs()` (POST rescore → `loadJobs()`) wired into
  `saveRuntimeOptions`, `addSkillToProfile`, and `saveProfile`; "Analyze Matches" already reloads
  (verified live: rescore recomputed 12 real jobs, preserved LLM verdicts, reused embeddings; no
  console errors; helper + 3 call-sites present in the served page)
- [x] (5/5) Tests (`tests/recommend/test_rescore.py`: reweight-only rag recompute, stored-LLM fold,
  full-rescore threads stored artifacts + persists sub-scores + doesn't rewrite the embedding,
  guards) + docs (`api-contract.md`, `data-flow.md`, `recommendation.md`, this checklist) + merge
- [x] Offline test subset green (`tests/recommend`, `tests/database`, `tests/test_frontend_wiring.py`),
  `import app` clean; rescore verified live against the real DB via the preview server

## LLM Fit on All Searches (adjustable coverage) — Definition of Done

Plan: `docs/plans/llm-fit-coverage.md`. Delivered on branch `llm-fit-coverage`
(worktree), committed per phase, merged to `main`.

Requirement: every job search — whether a **manual search from the Web UI** or the
**automatic daily bot** — must run **all** of its final jobs through the LLM for a
personalized fit, and this must be **adjustable** (default **1.0** = all) in the Options menu.

- [x] (1/5) Worktree + plan doc
- [x] (2/5) `llm_fraction` runtime knob (default `1.0` = every final job → LLM) in
  `DEFAULT_RUNTIME_CONFIG`; `service._llm_rerank` keeps the top `ceil(fraction × N)` candidates
  by semantic+bm25 and composes with the existing `top_n_llm` absolute cap. Both manual
  (`/api/scrape/start`) and bot (`utils/backend/scheduler`) searches reach it via the shared
  `execute_full_scraping_workflow → analyze_jobs`. 4 coverage tests added.
- [x] (3/5) Options → Runtime "LLM coverage" slider (0–100%, default 100%) with a live percent
  readout; `rtLlmFraction`/`onRtLlmFraction` wiring + `llm_fraction:1.0` embedded default +
  updated "LLM re-rank" helper copy (verified: served template + API round-trip default 1.0 /
  save 0.5 / restore 1.0)
- [x] (4/5) Docs updated (`recommendation.md`, `data-flow.md`, `api-contract.md`, this checklist)
- [x] (5/5) Offline suite green + `import app` clean; merged to `main`
- [ ] **LLM fit live on all searches** — the coverage selection is covered by mocked-client
  tests; issuing real verdicts for every job needs an enabled endpoint (Options → LLM Endpoint)
  + "LLM re-rank" on. Note: `llm_fraction = 1.0` issues one LLM call **per final job** — lower it
  to cap cost.

## Find Jobs: Max Results 100 + Max Iterations — Definition of Done

Plan: `docs/plans/find-jobs-iterations.md`. Delivered on branch `find-jobs-iterations`
(worktree), committed per phase, merged to `main`.

Requirement: raise the Find Jobs **Max Results** ceiling to **100**, and add a **Max Iterations**
(1–5) control below it that loops/re-searches to surface unique/various results.

- [x] (1/5) Worktree + plan doc
- [x] (2/5) Page `offset` threaded through `JobSpyScraper` → `JobScrapeTask` → jobspy
  `scrape_jobs`; steps 2–5 of `execute_full_scraping_workflow` extracted into an inner helper and
  run up to `max_iterations` times (config-driven, clamped 1–5, forced 1 in non-DB mode),
  advancing `offset` by `results_wanted` per pass and accumulating new-job ids; steps 6–7 run once.
  `max_iterations:1` added to the default config. Offline tests (`tests/scrapers/test_iterations.py`:
  advancing offset, cross-pass dedup, single-pass default, clamp-to-5).
- [x] (3/5) Frontend: Max Results slider `max=100`; Max Iterations slider (1–5, default 1) below
  it + helper copy; `maxIterations`/`onMaxIter` state, `configToSave`/`applyConfig` wiring
  (verified: served template `max=100` + control present, config save/load round-trip persists
  `max_iterations`)
- [x] (4/5) Docs (`find_jobs.md`, `job_scraping.md`, `data-flow.md`, this checklist)
- [x] (5/5) Offline suite green + `import app` clean; merged to `main`
- [ ] **Live multi-iteration scrape** — the offset/loop/dedup paths are covered by an offline
  mocked-scraper test; a real multi-pass run hits live job boards (and, for new jobs, the LLM fit).

## Agentic Documents — Foundation — Definition of Done

Design: `docs/plans/agentic-documents-system.md`. Plan: `docs/plans/agentic-documents-foundation.md`.
Delivered on branch `agentic-documents-foundation` (worktree), committed per phase.

Scope: the **data + ingestion foundation** (design build-order §8.1 data layer + §8.2 ingestion
agent & Profile/Documents sidebar). Orchestration is **in-house plain Python (no LangGraph)** — the
node structure and checkpoint semantics are preserved via DB columns + the async-task pattern, with
zero new dependencies. **Application Mode is out of scope**, and the cover-letter/résumé generation
graphs (§8.3/§8.4) are the **next phase** (checked in with the user before building them).

- [x] (1/6) Worktree + design/implementation plan docs
- [x] (2/6) 6 supporting-document models (`uploaded_documents`, `behavioral_profiles`,
  `writing_style_profiles`, `document_templates`, `job_evaluations`, `generated_documents`) —
  created by `create_all` (no migration for new tables); `documents_ops.py` CRUD (single-active
  invariant for the two profile-like tables, default-per-kind templates, `job_evaluations` upsert);
  idempotent `seed_documents_if_empty()` wired into `init_database()`; `clear_jobs_database()` also
  purges the new job-linked rows; 8 in-memory round-trip/invariant/seed tests
- [x] (3/6) In-house ingestion/summarization agent (`utils/backend/agents/ingestion`) —
  extract→classify→summarize/normalize, reuses `extract_resume_text` + `OpenAIClient`, returns a
  draft (never persists), degrades to an empty editable draft with no LLM, never 500s on a malformed
  upload; 7 mocked-LLM tests
- [x] (4/6) `documents_bp` blueprint (ingest, ingest/save, uploaded list, behavioral/writing/templates
  CRUD, job-evaluation, generated-docs list) registered in `app.py`; 8 test-client tests on an
  isolated in-memory DB
- [x] (5/6) Profile slide-over → tabbed **Profile & Documents** sidebar (Candidate | Behavioral |
  Writing | Templates) with upload→draft→edit→save for behavioral/writing, a template manager, and a
  Recent-uploads trace; verified live in-browser (DOM): tabs render+switch, seeds load, template
  selection loads its body, Save Profile is Candidate-only, no console errors; +2 served-page wiring tests
- [x] (6/6) Docs (`database.md`, `structure.md`, `routes.md`, `api-contract.md`, `component-map.md`,
  `data-flow.md`, `documentation.md`, this checklist) + validation
- [x] Offline test subset green (`tests/database`, `tests/agents`, `tests/documents`,
  `tests/test_frontend_wiring.py`, + the prior suites), `import app` clean; UI verified via preview
  tools (screenshot tooling timed out as in prior UI work — DOM inspection used instead)
- [ ] **Ingestion live with a real LLM endpoint** — the agent is covered by mocked-client tests; real
  summarization needs an enabled endpoint (Options → LLM Endpoint). Without one it degrades to an
  empty editable draft.
- [x] **Next phase — DELIVERED:** cover-letter graph (§2) + résumé fine-tuner with recommender
  match-lift (§3) — see the section below. Application Mode (§4) remains the deferred large effort.

## Agentic Documents — Graphs — Definition of Done

Design: `docs/plans/agentic-documents-system.md` (§2/§3). Plan: `docs/plans/agentic-documents-graphs.md`.
Delivered on branch `agentic-documents-foundation` (worktree), committed per phase.

Scope: the two **per-job generation graphs** (design build-order §8.3 Cover Letter + §8.4 Résumé
fine-tuner). Orchestration is **in-house plain Python (no LangGraph)** — an explicit node pipeline,
an in-memory task store mirroring `recommend_routes`, `threading.Event` checkpoint pause/resume, and
a persisted `generated_documents.checkpoint_state` snapshot; zero new dependencies. **Application Mode
(§4) and the browser-automation adapter (§4.3) remain out of scope.**

- [x] (1/6) Part-2 plan doc (`docs/plans/agentic-documents-graphs.md`)
- [x] (2/6) In-house orchestrator (`agents/orchestrator.py`: progress + semi-auto checkpoints),
  context loader (`agents/context.py`: Ingestion = a DB read), recommender-reuse match-lift
  (`agents/scoring.py`), prompts + normalizers + slot helpers (`agents/prompts.py`); 8 tests
- [x] (3/6) Cover-letter graph — `nodes_shared.py` (research_company, evaluate_fit persisting
  `job_evaluations`, truthfulness_check) + `nodes_cover_letter.py` (strategize/write/style/critique) +
  `cover_letter.py` (pipeline + revision loop + angle checkpoint); every node degrades with no LLM;
  3 tests (offline fallback + persisted evaluation, full LLM path, interactive checkpoint)
- [x] (4/6) Résumé fine-tuner graph — `nodes_resume.py` (evaluate_gap/plan_edits/rewrite/ats_format,
  strictly truth-preserving fallbacks) + `resume.py` whose `score` node reuses `recommend/ranker`
  on a throwaway profile for an objective `match_before → match_after` lift; 3 tests (offline
  truth-preserving lift, non-fabrication of an un-owned JD skill, LLM path, plan checkpoint)
- [x] (5/6) Generation service (`agents/service.py`: daemon-thread runner + async task+poll +
  persistence) and `generation_bp` routes (`routes/document_generation_routes.py`:
  cover-letter/résumé start, status, resume, GET/PATCH generated doc) registered in `app.py`;
  5 test-client tests (start→poll→completed both kinds, résumé match-lift, PATCH approve,
  interactive pause→resume, 400/404 guards)
- [x] (6/6) Job-detail **Documents** surface in `index.html` (Cover Letter / Tailor Résumé buttons,
  inline node-stage progress, generated-docs list with the match-lift badge using the recommendation
  color grading, View / Approve, a document-viewer modal with Download) + docs (`routes.md`,
  `api-contract.md`, `data-flow.md`, `component-map.md`, `structure.md`, this checklist) + validation
- [x] Offline suite green (`tests/agents`, `tests/documents`, `tests/test_frontend_wiring.py`, + prior
  suites), `import app` clean, all six `/api/documents/*` generation routes registered without
  collision; UI verified live on the preview (page renders, Documents section + buttons present, no
  console errors; a full live generation produced + persisted a real cover letter, then the test rows
  were removed so the shared DB was left untouched — DOM inspection used; screenshot tooling flaky)
- [ ] **Full-quality output needs a real LLM endpoint** — the graphs are covered by mocked-client +
  offline-fallback tests; a live generation on this env's (hanging) endpoint completed with mixed
  real-LLM + fallback content and `needs_review=true`. Prose quality + the angle/plan checkpoints are
  best exercised with an enabled, responsive endpoint (Options → LLM Endpoint).
- [ ] **Application Mode (§4)** — the Apply-button intent/status split, `application_sessions`, the
  intake wizard, and the manual/browser submission adapters remain the deferred large effort.

## Agentic Documents — Application Mode — Definition of Done

Design: `docs/plans/agentic-documents-system.md` (§4). Plan: `docs/plans/agentic-documents-application-mode.md`.
Delivered on branch `agentic-documents-foundation` (worktree), committed per phase.

Scope: the interactive **Apply** flow — generation moved **out of the Profile side-panel** into a
dedicated modal, with an iterate/refine loop. **Out of scope (still deferred):** the
browser-automation submission adapter (§4.3) and a persisted `application_sessions` table (the
session is ephemeral frontend state; the documents persist in `generated_documents`).

- [x] (1/5) Plan doc (`docs/plans/agentic-documents-application-mode.md`)
- [x] (2/5) Steerable refine backend — `prompts.guidance_block()`; `instructions`/`prior_content`
  through `context.load_context` + the cover-letter (strategize/write) and résumé (plan/rewrite)
  nodes; `service.start_generation(instructions, prior_content, revise_from)` with `_persist`
  updating the `revise_from` row in place (revision bump, no accumulation); routes accept
  `{instructions?, revise_from?}` (revise_from loads the prior draft's content). Tests: guidance
  threads through both graphs; API refine updates in place.
- [x] (3/5) Apply flow UI — cards (New Jobs + Saved) + job-detail footer show **Apply** (opens the
  flow) + **Applied** (quick markApplied); the side-panel Documents section + viewer are removed.
  Application Mode modal (mirrors the Find Jobs shell): Intake (résumé/cover toggles + guidance +
  Start / Just-mark-Applied) → Generating (parallel per-doc node-stage progress) → Review (content,
  résumé match-lift badge, Edit / Download / Approve, quick-refine chips + a Regenerate feedback box
  that re-runs in place via `revise_from`). Mark-as-Applied finishes. Wiring test swapped to
  Application-Mode tokens.
- [x] Verified live in-app on the preview: Apply → intake → **parallel** generation of both docs
  with live stages → review with the 54%→56% match-lift badge → chip-prefilled **Regenerate**
  (re-ran the cover letter in place) → Edit editor → Approve chip → Close (pollers torn down); no
  console errors. Node `--check` on the component JS passes; `import app` clean; 46 targeted offline
  tests green. Verification rows were removed and the job status left untouched.
- [x] (4/5) Docs (`component-map.md`, `routes.md`, `api-contract.md`, `data-flow.md`, this checklist).
- [x] (5/5) Adversarial multi-agent review of the diff (4 dimensions → verify): 5 findings confirmed
  and **all fixed** — (a) review-existing / de-selected kinds no longer render a phantom card or a
  false "couldn't generate" error (card visibility keys off `want`, reconciled on the review-existing
  path); (b) Edit/Download/Approve are hidden while a card is actively regenerating, so a refine can't
  silently revert a concurrent Approve/Save; (c) the refine's revision read-modify-write is serialized
  with a lock; (d) the Apply pollers/`_fetchAppDoc`/`_finishGen` carry a job-id guard so a late
  completion can't cross jobs. Fixes 1 & 3 re-verified live in-app; full offline suite green.
- [ ] **Browser-automation submission (§4.3)** and **`application_sessions`** persistence remain the
  deferred follow-ups; a full LLM endpoint is still needed for best-quality prose (the graphs
  degrade gracefully offline).

## Agentic Documents — LaTeX Output + PDF Preview Workspace — Definition of Done

Design: `docs/plans/agentic-documents-system.md` (§4). Plan: `docs/plans/agentic-documents-application-mode.md`
(LaTeX + PDF iteration). Delivered on branch `agentic-documents-foundation` (worktree), committed per phase.

Scope: on top of the Apply flow, the generation graphs now emit **LaTeX** (not Markdown), a compile
subsystem renders that source to a **PDF**, and the Apply **Review** screen becomes a **two-column
workspace** — left a live step-by-step agent process feed + refine controls, right the rendered PDF
preview — with per-document tabs. **Out of scope (still deferred):** the browser-automation submission
adapter (§4.3) and a persisted `application_sessions` table.

- [x] (1/5) Deterministic offline LaTeX assembly (`utils/backend/agents/latex.py`: `escape_latex`,
  `md_to_latex`, `build_cover_letter_tex`, `build_resume_tex`) — the graphs' final node now emits a full
  `\documentclass{article}` document; `generated_documents.content` is a complete `.tex` document and the
  row persists `format="latex"`; the résumé **match-lift** is still computed on the plain tailored text
  (not the LaTeX), so the recommender reuse is unchanged; tests (`tests/agents/test_latex.py`)
- [x] (2/5) PDF compile subsystem (`utils/backend/pdf_compile.py`: `compile_pdf` shells out to `pdflatex`
  and caches the result under `data/generated_pdfs/` keyed by content — an unchanged document isn't
  recompiled — with `LatexCompileError` on a missing toolchain / bad source)
- [x] (3/5) Serve routes — `GET /api/documents/<id>/pdf` (compile-or-reuse-cache → stream the PDF inline,
  or as an attachment with `?download=1`; 404 unknown doc / 415 non-LaTeX / 422 compile failure, all
  logged) + `GET /api/documents/<id>/tex` (raw LaTeX source); tests (`tests/documents/test_pdf_route.py`)
- [x] (4/5) Apply Review two-column `data-appws` workspace — left **Process** column (the live agent step
  feed from the task `events`, including the revision loops, + the refine chips/box → **Regenerate** and
  **Edit LaTeX** / **Download PDF** / **Approve**); right **Preview** column (the compiled PDF in an
  `<iframe>` whose `src` is set through a React `ref`, so the raw template never fetches a literal `{{…}}`
  URL); document tabs (Tailored Résumé ∣ Cover Letter); a Process ∣ Preview toggle on narrow screens; the
  PDF recompiles on each refine/edit; wiring test
  (`tests/test_frontend_wiring.py::test_index_has_two_column_latex_workspace`)
- [x] (5/5) Docs (this checklist + the plan doc's LaTeX/PDF iteration section) + validation
- [x] Full suite **251 passed** (2 pre-existing, unrelated env failures), `import app` clean; the six
  `/api/documents/*` generation routes plus the new `/pdf` + `/tex` routes register without collision
- [ ] **PDF preview needs `pdflatex` on the host** — the compile subsystem shells out to `pdflatex`; where
  it isn't installed (or the source fails to typeset) `compile_pdf` raises `LatexCompileError` and the
  `/pdf` route returns 422 (logged). Install a TeX toolchain to render/download the PDF; the raw `.tex`
  source is always available via `/tex`.
- [ ] **Best-quality LaTeX prose still needs a real LLM endpoint** — the deterministic assembly guarantees
  a valid compilable document offline, but the model-authored body is best exercised with an enabled,
  responsive endpoint (Options → LLM Endpoint).

## Saved Jobs Not Auto-Hidden — Definition of Done

Plan: `docs/plans/saved-jobs-not-auto-hidden.md`. Delivered on branch
`fix-saved-jobs-auto-hidden` (worktree), committed per phase.

Fixes the reported bug where jobs in the **Saved** lane were being hidden (`ignore=1`) without the
user clicking hide, and got re-hidden after the user un-hid them (on a server restart / job search).
Root cause: the two auto-hide filters (`filter_and_mark_jobs` during a search, `apply_profile_filters`
on Profile Save / Block Company over all jobs) set `ignore=1` on matching jobs **without exempting
saved jobs**, and blocking is one-directional (only ever hides). These are the only two non-user
writers of `ignore=1`.

- [x] (1/3) `saved`-guard added to `filter_and_mark_jobs()` and `apply_profile_filters()` in
  `utils/backend/scrapers/job_filter.py` — both skip any job with `saved=1` (never auto-hide it);
  docstrings updated. Save/Ignore stay independent; the manual hide button still works on a saved job.
- [x] (2/3) Isolated in-memory regression tests (`tests/scrapers/test_saved_job_filter_exempt.py`):
  a saved job matching a block rule (company / title / keyword-group) or failing the `jobs_config`
  keyword filter is left visible, while an identical non-saved job is still hidden.
- [x] (3/3) Docs updated (`database.md`, `data-flow.md`, `save-jobs.md`, this checklist).
- [x] Offline test subset green (`tests/scrapers`, `tests/database`), `import app` clean; fix verified
  by reproducing the bug against an isolated DB before/after the guard.

## Analyze Matches — LLM Coverage Fix — Definition of Done

Plan: `docs/plans/analyze-matches-llm-coverage.md`. Delivered on branch
`analyze-matches-llm-coverage` (worktree), committed per phase, merged to `main`.

Requirement: "Analyze Matches" must honor the Options → Runtime **"Jobs through the LLM"**
(`llm_fraction`) slider — **100% = every job through the LLM (if available); 50% = the top 50%
by embedding/rerank**. It was only doing "~20%" because the fraction was applied to the
missing-verdict gap, not the full analyzed set.

- [x] (1/3) Worktree + plan doc
- [x] (2/3) `service._select_llm_indices` selects the coverage set over **all** analyzed jobs
  (top `ceil(llm_fraction × N)` by semantic+bm25, then the `top_n_llm` cap), and only then
  applies the gap-fill (`llm_only_missing`) filter; `_llm_rerank` + `analyze_jobs`' progress
  count both use it. Two tests added (fraction over the full set; 100% covers all but gap-fills
  only the missing) + a scripted proof that fraction is a share of the whole set
- [x] (3/3) Docs (`recommendation.md`, `data-flow.md`, `api-contract.md`, this checklist) + merge
- [x] Offline `tests/recommend` subset green (the one pre-existing model-dependent failure,
  `test_analyze_api_and_report`, also fails unmodified on `main` — needs the bge model cached),
  `import app` clean
- [ ] **Live coverage with a real LLM endpoint** — the selection/gap-fill is covered by
  mocked-client tests; issuing real verdicts for the covered jobs needs an enabled endpoint
  (Options → LLM Endpoint) + "LLM re-rank" on.

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
