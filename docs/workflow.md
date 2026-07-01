# Workflow — Magnification

Operational rules for working in this repository. Read alongside `docs/skills/global-project-rules/SKILL.md`.

## Environment

- **Manager:** `uv` (Python ≥ 3.12). Do not use pip/conda in committed instructions.
- **Virtualenv:** managed by `uv` (`.venv/`, gitignored).
- **Config files:** `jobs_config.json`, `llm_config.json`, `llm_endpoint_config.json`, and `runtime_config.json` are runtime config and are **gitignored**. There are no required environment variables today, so no `.env.example` is maintained. If env vars are introduced later, add `.env.example` and document them here.
- **Shared data root across worktrees:** the SQLite database (`data/magnificiation.db`) and every
  gitignored `config/*.json` file resolve through `utils/backend/paths.get_project_root()`, which
  uses `git rev-parse --git-common-dir` to find the **one** project root shared by the main checkout
  and every git worktree (falling back to a `__file__`-relative computation when `git` is
  unavailable). Do not reintroduce a bare `Path(__file__).resolve().parents[N]` for a gitignored
  runtime path — git worktrees do not share untracked files, so that pattern silently gives each
  worktree its own empty, disconnected database/config. See `docs/plans/shared-data-root.md`.

### Recommendation dependencies (fastembed / BM25 / PDF)

The RAG + LLM recommendation features add `fastembed` (ONNX, CPU embeddings for
`BAAI/bge-small-en-v1.5`), `rank-bm25`, `pypdf`, and `requests` to `pyproject.toml`.

The committed `uv.lock` is fragile (it pins `regex` to an sdist with no offline wheel), so
`uv sync` / `uv add` can fail. Install these as **binary wheels** into the existing venv
without touching the lock:

```
uv pip install --only-binary=:all: fastembed rank-bm25 pypdf requests
```

The bge embedding model (~130 MB) is downloaded from HuggingFace on **first embed** and cached
under `~/.cache/`; that one call needs network. Tests that depend on the model skip when it is
not cached, and all LLM-dependent tests run against a mocked endpoint (no network/keys needed).

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
- **Every worktree now shares the real `data/magnificiation.db`** (see the shared-root note above).
  Tests that exercise `utils/backend/database/operations.py` must either run against an isolated
  in-memory engine (patch `init_db.SessionLocal`, e.g. `tests/database/test_clear_jobs.py`) or
  snapshot/restore the pre-existing active profile (e.g. `tests/profile/test_profile_api.py`).
  Never mutate real rows without one of these two guards.

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
