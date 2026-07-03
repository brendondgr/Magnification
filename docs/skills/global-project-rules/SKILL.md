---
name: global-project-rules
description: Read this skill first before doing any work in the Magnification repository. It defines the source-of-truth docs, environment manager, documentation-maintenance rules, testing/verification expectations, and the git workflow every agent must follow.
---

# Global Project Rules — Magnification

Magnification is a Flask/Jinja job-search application: a job-scraping backend (`utils/backend`), a server-rendered frontend (`utils/frontend`), SQLite storage, and a local-LLM integration (`utils/LocalLLM`). A React frontend overhaul is planned but not yet started.

Every AI agent and contributor must read this file before making changes.

## Source of Truth

The repository's durable instructions live in `docs/`. Agent-specific folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointer files — never the canonical instructions.

Read before acting:

1. `docs/skills/global-project-rules/SKILL.md` (this file)
2. `docs/documentation.md` — project purpose, stack, architecture, status
3. `docs/structure.md` — repository tree and the reason each path exists
4. `docs/workflow.md` — install, run, test, lint, env, docs-maintenance, and git rules
5. `docs/checklist.md` — active checklist and known follow-up work
6. The relevant canonical skill under `docs/skills/<skill>/` for the task at hand

For any web/UI/route/data-flow work, also read `docs/architecture.md`, `docs/routes.md`, `docs/component-map.md`, `docs/data-flow.md`, `docs/design-system.md`, and `docs/api-contract.md`.

## Installed Skills

- `docs/skills/planner/` — create and refine implementation plans before coding.
- `docs/skills/repository-structure/` — repository layout standards.
- `docs/skills/website-architecture/` — web app structure, routes, data flow, design-quality gate.
- `docs/skills/accessibility-mobile/` — mobile-responsive and touch accessibility checks.
- `docs/skills/portfolio-readme/` — write/audit GitHub profile and project READMEs, and repo pinning/curation advice.

## Environment Manager

This is a Python project managed with **`uv`**. Do not introduce pip/conda workflows into committed instructions.

- Install: `uv sync`
- Run app: `uv run app.py`
- Add a dependency: `uv add <package>`
- Run tests: `uv run pytest`

The full command list lives in `docs/workflow.md`.

## Documentation Maintenance

When a change affects any of the following, update the matching doc in the same change:

- Project purpose, stack, or status → `docs/documentation.md`
- Files or directories added/moved/removed → `docs/structure.md`
- Commands, environment, or dependencies → `docs/workflow.md`
- New or changed routes/endpoints → `docs/routes.md` and `docs/api-contract.md`
- New UI components or ownership → `docs/component-map.md`
- Data sources or flow → `docs/data-flow.md`
- Visual/design decisions → `docs/design-system.md`
- Outstanding work → `docs/checklist.md`

Implementation plans go in `docs/plans/`.

## Testing and Verification

- Keep lightweight tests under the top-level `tests/` directory, grouped by area (`tests/<area>/test_<behavior>.py`).
- Verify the Flask app still imports and starts after backend changes.
- For UI changes, validate the responsive/accessibility checklist in `docs/skills/accessibility-mobile/SKILL.md`.
- Favor modular files: max 800 lines, ideally under 500.

## Git Workflow

- Do non-trivial work on a feature branch, not directly on `main`.
- Commit per logical phase. **Do not push unless the user explicitly asks.**
- End commit messages with the `Co-Authored-By` trailer when applicable.

## Cleanup

Do not leave competing sources of truth. Starter/scaffold inputs and superseded docs must be removed once their content has been migrated into `docs/`.

## Definition of Done

Setup or a feature is not complete until the applicable checklist items in `docs/checklist.md` are verified. Do not claim completion while checklist items remain unmet — finish the work or list the blocking items.
