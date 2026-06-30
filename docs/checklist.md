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

## Deferred / Follow-up Work

- [ ] **Migrate web code to `web/`** per `docs/skills/repository-structure/structures/web-interfaces.md` (Mode F). Deferred because the app is working and a frontend rebuild is planned.
- [ ] **React frontend overhaul** — rebuild `utils/frontend` as a React app; re-run `website-architecture` to choose the React stack, and add `ui-frontend` + `ada-compliance` skills at that time.
- [ ] **Add `ruff`** for lint + format; record commands in `docs/workflow.md`.
- [ ] **Add `ada-compliance` skill** when the accessibility audit work begins.
- [ ] **`.env.example`** — add only if/when environment variables are introduced (currently config is JSON-file based).

## Intentionally Retained / Removed

- **Removed:** `bdgrSkills/` (starter kit — selected skills migrated to `docs/skills/`; `ui-frontend` and `ada-compliance` not selected for this pass), `docs/project_structure.md`, `docs/frontend_structure.md`, `docs/readme.md`.
- **Retained:** `docs/database.md`, `docs/job_scraping.md`, `docs/find_jobs.md`, `docs/ui.md` as subsystem deep-dives linked from `docs/documentation.md`; `requirements.txt` as a legacy mirror of `pyproject.toml`; `main.py` (uv default stub).
