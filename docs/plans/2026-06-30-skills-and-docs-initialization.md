# Plan: Skills & Docs Initialization (docs/ Source-of-Truth Overhaul)

## 1. Introduction

This plan overhauls the **Magnification** repository to match the design scheme defined in `bdgrSkills/initialize.md`. The goal is to make `docs/` the single source of truth for project documentation and agent-facing skills, install a curated set of skills as canonical definitions, and add minimal pointer files for the supported agent tools (Claude Code, OpenAI Codex, Cursor).

The approach is additive and non-destructive to working application code. Magnification is a working Flask/Jinja monolith (job-scraping backend in `utils/backend`, server-rendered frontend in `utils/frontend`, SQLite storage, a LocalLLM integration). Per the user's decision, the current code layout is **retained as-is**; the `web/` migration and the planned React frontend overhaul are recorded as future checklist items, not executed now. This pass installs the **planner**, **repository-structure**, **website-architecture**, and **accessibility-mobile** skills (plus the mandatory **global-project-rules**), writes the canonical and web-architecture docs, wires up agent pointers, and removes the `bdgrSkills/` starter kit after migration.

## 2. Gaps & Unanswered Questions

- **Physical code migration to `web/`** — *Resolved by user:* docs/skills scaffolding only for now; do not move working code. Record `web/` migration as a future task.
- **Supported agent tools** — *Resolved by user:* Claude Code, OpenAI Codex, Cursor. (Gemini CLI / Antigravity excluded.)
- **`ui-frontend` / `ada-compliance` skills** — *Assumption:* Out of scope. The user explicitly named only planner, repository-structure, website-architecture, accessibility-mobile. The web-architecture docs will reference `ada-compliance`/`ui-frontend` as recommended for the future React work, but they are not installed now.
- **Git workflow** — *Resolved by user:* commit per phase, **do not push**. Work happens on branch `init-skills-scaffold`, merged to `main` at the end.
- **Environment variables / `.env.example`** — *Assumption:* The app configures via gitignored JSON files (`jobs_config.json`, `llm_config.json`), not env vars. No `.env.example` is required; this is documented in `docs/checklist.md` as intentionally deferred.
- **Existing domain docs** (`database.md`, `find_jobs.md`, `job_scraping.md`, `ui.md`) — *Assumption:* Keep as canonical deep-dive references, linked from `documentation.md`. The structural docs (`project_structure.md`, `frontend_structure.md`) are superseded by `structure.md`/`component-map.md` and removed to avoid competing sources of truth.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Write this plan (Phase 1)
- **Locations**: `docs/plans/2026-06-30-skills-and-docs-initialization.md`.
- **Rationale**: The planner skill requires an explicit, validated plan before implementation, and `docs/plans/` must exist per the initializer.
- **Action**: Verify the plan renders and `docs/plans/` exists. Once validated, commit: `Skills Init (1/5) Complete: Added docs/plans/ and initialization plan.`

### Step 2: Migrate selected skills into `docs/skills/` (Phase 2)
- **Locations**: `docs/skills/global-project-rules/SKILL.md`; `docs/skills/planner/{SKILL.md,planner.md,SETUP.md}`; `docs/skills/repository-structure/{SKILL.md,SETUP.md,structures/}`; `docs/skills/website-architecture/{SKILL.md,SETUP.md}`; `docs/skills/accessibility-mobile/SKILL.md`. Sources under `bdgrSkills/`.
- **Rationale**: `docs/skills/` is the canonical home for skills. `global-project-rules` is mandatory and must be authored fresh. Skill folder names follow the initializer's canonical names (`planner`, `repository-structure`). Frontmatter `name:` is updated to match each folder.
- **Action**: Verify every skill folder has a valid `SKILL.md` and supporting files. Once validated, commit: `Skills Init (2/5) Complete: Migrated selected skills + global-project-rules into docs/skills/.`

### Step 3: Write canonical & web-architecture docs (Phase 3)
- **Locations**: `docs/documentation.md`, `docs/structure.md`, `docs/workflow.md`, `docs/checklist.md`, `docs/architecture.md`, `docs/routes.md`, `docs/component-map.md`, `docs/data-flow.md`, `docs/deployment.md`, `docs/design-system.md`, `docs/api-contract.md`. Route data sourced from `utils/backend/routes/*.py`; structure from `utils/`, `app.py`.
- **Rationale**: These are the source-of-truth documents. The web docs are required because Magnification is an API-backed Flask web app; `api-contract.md` is required because Flask blueprints expose endpoints.
- **Action**: Verify each doc exists and is concrete (no placeholders). Once validated, commit: `Skills Init (3/5) Complete: Authored canonical docs and web-architecture docs.`

### Step 4: Generate agent pointer files (Phase 4)
- **Locations**: `.claude/skills/<skill>/SKILL.md`, `.agents/skills/<skill>/SKILL.md` (for global-project-rules, planner, repository-structure, website-architecture, accessibility-mobile); `.cursor/rules/<skill>.mdc`.
- **Rationale**: Agent folders must contain only pointers to `docs/skills/global-project-rules/SKILL.md` and the relevant canonical skill — no duplicated instructions.
- **Action**: Verify each pointer has valid tool-specific frontmatter and references real `docs/` targets. Once validated, commit: `Skills Init (4/5) Complete: Added Claude Code, Codex, and Cursor pointer files.`

### Step 5: Cleanup, README, verification, merge (Phase 5)
- **Locations**: Delete `bdgrSkills/`, `docs/project_structure.md`, `docs/frontend_structure.md`, `docs/readme.md`→consolidate into `README.md`. Verify with `git grep`/`ls` and a Flask import smoke test.
- **Rationale**: The starter kit and superseded docs must not remain as competing sources of truth. README must point to canonical docs. The Definition of Done requires explicit verification.
- **Action**: Run the verification checklist (pointer targets exist, app imports, tree inspected). Once validated, commit: `Skills Init (5/5) Complete: Cleanup, consolidated README, verified DoD.` Then merge `init-skills-scaffold` into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Initialization plan | This phased plan | `docs/plans/2026-06-30-skills-and-docs-initialization.md` |
| Global project rules skill | Mandatory rules every agent reads first | `docs/skills/global-project-rules/SKILL.md` |
| Canonical skills | planner, repository-structure, website-architecture, accessibility-mobile | `docs/skills/<skill>/` |
| Canonical docs | documentation, structure, workflow, checklist | `docs/{documentation,structure,workflow,checklist}.md` |
| Web architecture docs | architecture, routes, component-map, data-flow, deployment, design-system, api-contract | `docs/{architecture,routes,component-map,data-flow,deployment,design-system,api-contract}.md` |
| Agent pointers | Claude Code, Codex, Cursor pointer files | `.claude/skills/`, `.agents/skills/`, `.cursor/rules/` |
| Verification test | Lightweight pointer-target + skill-doc verification script | `tests/docs/test_skill_pointers.py` |
| README | Points readers to canonical `docs/` | `README.md` |
