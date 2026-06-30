# Workflow — Magnification

Operational rules for working in this repository. Read alongside `docs/skills/global-project-rules/SKILL.md`.

## Environment

- **Manager:** `uv` (Python ≥ 3.12). Do not use pip/conda in committed instructions.
- **Virtualenv:** managed by `uv` (`.venv/`, gitignored).
- **Config files:** `jobs_config.json`, `llm_config.json` are runtime config and are **gitignored**. There are no required environment variables today, so no `.env.example` is maintained. If env vars are introduced later, add `.env.example` and document them here.

## Commands

| Task | Command |
| --- | --- |
| Install / sync deps | `uv sync` |
| Add a dependency | `uv add <package>` |
| Run the app (dev) | `uv run app.py` (Flask dev server, `debug=True`, default `http://127.0.0.1:5000`) |
| Run tests | `uv run pytest` |
| Run a single test | `uv run pytest tests/<area>/test_<name>.py` |
| Smoke-check import | `uv run python -c "import app; print('ok')"` |

> Lint/format/type-check tools are not yet configured. Adding `ruff` (lint+format) is a recommended follow-up in `docs/checklist.md`.

## Testing & Verification

- Tests live in top-level `tests/`, grouped by area (`tests/<area>/test_<behavior>.py`).
- After backend changes: confirm `app.py` imports and the app starts.
- After UI changes: validate the responsive/accessibility checklist in `docs/skills/accessibility-mobile/SKILL.md`.
- Doc/skill integrity is checked by `tests/docs/test_skill_pointers.py`.

## Documentation Maintenance

Update the relevant `docs/` file in the same change as the code:

- Stack/status → `docs/documentation.md`
- Files/dirs → `docs/structure.md`
- Commands/env/deps → `docs/workflow.md`
- Routes/endpoints → `docs/routes.md`, `docs/api-contract.md`
- UI components → `docs/component-map.md`
- Data flow → `docs/data-flow.md`
- Visual decisions → `docs/design-system.md`
- Outstanding work → `docs/checklist.md`
- Plans → `docs/plans/`

## Git Workflow

- Branch for non-trivial work; do not commit directly to `main`.
- Commit per logical phase. **Do not push unless the user explicitly asks.**
- End commit messages with the `Co-Authored-By` trailer when produced with an agent.

## Supported Agent Tools

Pointer files are maintained for: **Claude Code** (`.claude/skills/`), **OpenAI Codex** (`.agents/skills/`), and **Cursor** (`.cursor/rules/`). Each points to `docs/skills/global-project-rules/SKILL.md` and the relevant canonical skill. Gemini CLI and Antigravity are not configured.

## Handoff

When handing work to another agent or contributor: ensure the relevant `docs/` are updated, the active branch is committed, and any open items are listed in `docs/checklist.md`.
