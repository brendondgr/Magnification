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
- [x] All pointer targets verified to exist (`tests/docs/test_skill_pointers.py`)
- [x] Flask app import smoke test passes

## Deferred / Follow-up Work

- [ ] **Migrate web code to `web/`** per `docs/skills/repository-structure/structures/web-interfaces.md` (Mode F). Deferred because the app is working and a frontend rebuild is planned.
- [ ] **React frontend overhaul** — rebuild `utils/frontend` as a React app; re-run `website-architecture` to choose the React stack, and add `ui-frontend` + `ada-compliance` skills at that time.
- [ ] **Add `ruff`** for lint + format; record commands in `docs/workflow.md`.
- [ ] **Add `ada-compliance` skill** when the accessibility audit work begins.
- [ ] **`.env.example`** — add only if/when environment variables are introduced (currently config is JSON-file based).

## Intentionally Retained / Removed

- **Removed:** `bdgrSkills/` (starter kit — selected skills migrated to `docs/skills/`; `ui-frontend` and `ada-compliance` not selected for this pass), `docs/project_structure.md`, `docs/frontend_structure.md`, `docs/readme.md`.
- **Retained:** `docs/database.md`, `docs/job_scraping.md`, `docs/find_jobs.md`, `docs/ui.md` as subsystem deep-dives linked from `docs/documentation.md`; `requirements.txt` as a legacy mirror of `pyproject.toml`; `main.py` (uv default stub).
