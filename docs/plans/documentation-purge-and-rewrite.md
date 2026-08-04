# Documentation Purge & Rewrite — Implementation Plan

**Branch:** `docs-overhaul` (Mode B — no worktree)
**Goal:** audit every doc and skill in the repository, delete what is stale or belongs to a
different project, and replace the rest with compact, verified-accurate versions.

## Why

The docs grew by accretion: several files are pre-implementation plans that were never rewritten
after the code shipped, one file describes an entirely different application, the root carries a
superseded design doc, and the checklist is a 1,047-line append-only build log. A full audit
(four parallel read-only passes over `docs/`, `utils/`, `app.py`, `tests/`, `deploy/`) produced the
findings below; every item is a verified mismatch, not a style preference.

## Audit findings (verified)

| File | Finding |
| --- | --- |
| `cover-letter-agent-design.md` (root) | LangGraph design, self-labelled "Design only — no implementation". No `langgraph` dependency exists; the shipped system is the in-house orchestrator in `utils/backend/agents/`. Orphaned — nothing links to it. |
| `docs/ui.md` | Belongs to a different app — references "ShortSpork", recipes, `variables.css`, glassmorphism, coral/indigo tokens, icon SVGs that do not exist. |
| `docs/frontend_structure.md` | `checklist.md` claims it was removed in the 2026-06-30 overhaul; it still exists, lists 4 tracker columns (there are 5) and 7 consumed endpoints (there are ~30). Superseded by `component-map.md`. |
| `docs/job_scraping.md` (704 lines) | A "Phase 1–9" pre-implementation plan. Cites `utils/libs/logger/`, `utils/backend/services/job_service.py`, `utils/libs/llm/`, `get_job_by_criteria()` — none exist. |
| `docs/find_jobs.md` (607 lines) | Only the 16-line preamble is current; the rest cites `handlers.js`, `renderers.js`, `header.html`, `modal.js` (single-file frontend) and a `cancel_scraping` route that was never built. |
| `docs/database.md` (402 lines) | §1–4 are plan prose for a `utils/backend/services/` package that was never built; the schema listing omits `jobs.site`, `profiles.blocked_companies/title_blocklist/llm_instructions` and three migrations; cites `get_job_by_criteria()` and `utils/backend/tests/`. |
| `docs/architecture.md` | Claims client-side HTML-partial stitching, `/parts/<file>` + `/primary/<file>` routes, 4 blueprints (10 are registered), Tailwind CDN, 5 external CSS files, FontAwesome/Lucide, DM Sans — none present. |
| `docs/routes.md` | Same fictitious partial routes; missing `PATCH /api/jobs/<id>/save` and `GET /api/jobs/counts`. |
| `docs/api-contract.md` | Missing `GET /api/jobs/counts`. |
| `docs/design-system.md` | Iconography (FontAwesome/Lucide), body font (DM Sans vs live `Archivo`), `parts/mobile-nav.html`. Theme-token table is accurate. |
| `docs/component-map.md` | Accurate except the `index.html` line count (says ~1,240; actual 2,815). |
| `docs/documentation.md` | Blueprint list omits `documents_bp`, `generation_bp`, `guidance_bp`. Status section is a changelog. |
| `docs/structure.md` | `tests/` tree omits 6 real subpackages (`backend`, `frontend`, `llm`, `profile`, `recommend`, `scrapers`). |
| `docs/checklist.md` | 1,047 lines, 38 shipped Definition-of-Done blocks. Line 434's deferred smoke test is factually stale (deps are installed, `import app` works). |
| `docs/workflow.md` | Accurate **except** its headline command: `uv run pytest` fails with 53 collection errors — no `pythonpath` config, so `from utils...` imports fail from the repo root. |
| `docs/skills/*/SETUP.md` (3 files) | One-time bootstrap questionnaires; answers already captured in `docs/`. Unreachable — nothing references them. |
| `docs/skills/repository-structure/structures/{lab-reports,langgraph}.md` | LaTeX lab reports and LangGraph layouts — neither applies to this repo (the agents are explicitly non-LangGraph). |
| `docs/skills/website-architecture/`, `accessibility-mobile/` | Reference `ui-frontend` and `ada-compliance` skills that do not exist; mandate a `web/` root that this repo deliberately does not have. |
| `docs/skills/repository-structure/SKILL.md` | Generic starter-kit tree (`libs/`, `[workflow]/`) contradicting `docs/structure.md`, which agents are told to treat as authoritative. |
| `pyproject.toml` | `description = "Add your description here"`; no pytest config. |

## Constraints

- `tests/docs/test_skill_pointers.py` pins: the 6-skill roster, `name:` frontmatter matching each
  folder, 11 canonical docs present and non-empty, `docs/plans/` present, and every pointer file
  containing the literal `docs/skills/global-project-rules/SKILL.md`. Deleting `ui.md` /
  `frontend_structure.md` is safe (neither is in `CANONICAL_DOCS`).
- `docs/plans/` is a historical record and is **kept**; superseded plans get a banner, not a delete.
- No behavior changes to application code. The only non-doc edit is pytest configuration, which
  exists to make a documented command true.

## Phases

1. **Plan + branch.** This file; branch `docs-overhaul`.
2. **Root.** Delete `cover-letter-agent-design.md`; rewrite `README.md` compact and verified.
3. **Purge + rewrite `docs/`.** Delete `ui.md` and `frontend_structure.md`; rewrite
   `job_scraping.md`, `find_jobs.md`, `database.md` as reference docs for the shipped code; correct
   `architecture.md`, `routes.md`, `api-contract.md`, `design-system.md`, `component-map.md`,
   `documentation.md`, `structure.md`.
4. **Checklist.** Compact `checklist.md` to a shipped-work ledger plus the genuinely open items.
5. **Skills.** Rewrite the six canonical skills to be repo-true; delete the three `SETUP.md` files
   and the two inapplicable `structures/` references; remove dead skill cross-references; keep the
   `.claude` / `.agents` / `.cursor` pointer sets consistent.
6. **Make the docs true.** Add `[tool.pytest.ini_options] pythonpath` + a real project description
   to `pyproject.toml`; re-verify every command in `workflow.md`.
7. **Validate + merge.** Full offline suite, `import app`, link check over every relative link in
   every Markdown file; merge to `main`.

## Validation per phase

Each phase ends with: `uv run pytest tests/docs` green, a link check over the files touched, and a
commit. Phase 6 additionally runs the full suite; phase 7 re-runs everything before the merge.

## Deliverables

| Deliverable | Location |
| --- | --- |
| Rewritten root README | `README.md` |
| Deleted stale docs | `cover-letter-agent-design.md`, `docs/ui.md`, `docs/frontend_structure.md` |
| Rewritten subsystem docs | `docs/{job_scraping,find_jobs,database}.md` |
| Corrected web docs | `docs/{architecture,routes,api-contract,design-system,component-map}.md` |
| Corrected core docs | `docs/{documentation,structure,workflow,checklist}.md` |
| Repo-true skills | `docs/skills/**`, pointer files in `.claude/`, `.agents/`, `.cursor/` |
| Working test command | `pyproject.toml` |
| Link checker | `tests/docs/test_doc_links.py` |
