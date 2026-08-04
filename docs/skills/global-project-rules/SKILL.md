---
name: global-project-rules
description: Read this skill first before doing any work in the Magnification repository. It defines the source-of-truth docs, environment manager, documentation-maintenance rules, testing/verification expectations, and the git workflow every agent must follow.
---

# Global Project Rules — Magnification

Magnification is a local-first job-search application: a scraping backend and hybrid recommender
(`utils/backend`), a single served page (`utils/frontend`), SQLite storage, in-house document
generation agents, and a configurable OpenAI-compatible LLM integration. A React frontend rebuild is
planned but has not started.

Every agent and contributor reads this file before making changes.

## Source of Truth

Durable instructions live in `docs/`. The agent folders (`.claude/`, `.agents/`, `.cursor/`) contain
pointer files only — never canonical content.

Read before acting:

1. `docs/skills/global-project-rules/SKILL.md` (this file)
2. `docs/documentation.md` — purpose, stack, architecture, status
3. `docs/structure.md` — the repository tree and why each path exists
4. `docs/workflow.md` — install, run, test, environment, docs-maintenance, and git rules
5. `docs/checklist.md` — what is still open
6. The canonical skill for the task at hand, under `docs/skills/<skill>/`

For web, UI, route, or data-flow work, also read `docs/architecture.md`, `docs/routes.md`,
`docs/api-contract.md`, `docs/component-map.md`, `docs/data-flow.md`, and `docs/design-system.md`.
For subsystem work, read the matching reference: `docs/database.md`, `docs/job_scraping.md`,
`docs/find_jobs.md`, `docs/recommendation.md`, `docs/profile.md`.

## Installed Skills

Six canonical skills, each with a pointer file in all three agent folders:

- `global-project-rules` — this file; the mandatory entry point.
- `planner` — create and refine implementation plans before coding.
- `repository-structure` — layout standards and file-length limits.
- `website-architecture` — app mode, routes, data flow, design-quality gate.
- `accessibility-mobile` — responsive and accessibility checks (the accessibility authority here).
- `portfolio-readme` — write or audit the README and portfolio-facing material.

Adding or removing a skill means updating: `docs/skills/<name>/SKILL.md` (with `name:` frontmatter
matching the folder), all three pointer files, this list, and the `SKILLS` list in
`tests/docs/test_skill_pointers.py`.

## Environment

Python ≥ 3.12 managed with **`uv`**. Do not put pip or conda workflows into committed instructions.

- Install: `uv sync`
- Run: `uv run app.py`
- Add a dependency: `uv add <package>`
- Test: `uv run pytest`

The full command list, including the systemd units and the fastembed wheel workaround, is in
`docs/workflow.md`.

## Documentation Maintenance

Update the matching doc in the **same change** as the code:

| Change | Doc |
| --- | --- |
| Purpose, stack, or status | `docs/documentation.md` |
| Files or directories added, moved, removed | `docs/structure.md` |
| Commands, environment, dependencies | `docs/workflow.md` |
| Routes or endpoints | `docs/routes.md` + `docs/api-contract.md` |
| UI components or ownership | `docs/component-map.md` |
| Data sources or flow | `docs/data-flow.md` |
| Visual or design decisions | `docs/design-system.md` |
| Work left open | `docs/checklist.md` |

Implementation plans go in `docs/plans/` and stay there as a historical record — supersede a plan
with a banner, don't delete it. Keep `docs/checklist.md` a list of what is **open** plus a ledger
pointing at those plans; do not grow it back into a build log.

## Testing and Verification

- Tests live in top-level `tests/`, grouped by area (`tests/<area>/test_<behavior>.py`), and run
  offline — mock the LLM client, and skip when the embedding model isn't cached.
- Every worktree shares the real database. A test that touches it must isolate itself (patch
  `init_db.SessionLocal` onto an in-memory engine) or snapshot and restore what it changes.
- After backend changes, confirm `import app` still works.
- After UI changes, run the checklist in `docs/skills/accessibility-mobile/SKILL.md`. The browser
  pane does not composite in this environment — verify via the served HTML, the API, and wiring
  tests, and say that is what you did.
- Never POST configuration or options to a running app to "verify" a change; that overwrites the
  user's real shared config.
- Favor modular files: 800 lines hard cap, under 500 preferred.

## Git Workflow

- Do non-trivial work on a feature branch, not directly on `main`.
- Commit per logical phase. **Do not push unless the user explicitly asks.**
- End agent-authored commit messages with the `Co-Authored-By` trailer.
- Other agents may share this checkout and switch its branch mid-task; use a git worktree for
  long-running non-trivial work.

## Cleanup

Do not leave competing sources of truth. When content is migrated, the old file goes — a doc that
describes a system that no longer exists is worse than no doc.

## Definition of Done

Work is not complete while its checklist items in `docs/checklist.md` are unmet. Finish them, or
state plainly which ones are blocked and why.
