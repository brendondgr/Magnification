---
name: repository-structure
description: Use when setting up, restructuring, documenting, or enforcing repository layout, structure docs, or project organization.
---

# Repository Structure Standard

The layout rules for this repository. `docs/structure.md` is the authoritative tree — this file is
the standard that tree is held to. Where the two disagree, `docs/structure.md` describes reality
and this file describes intent; reconcile them rather than leaving the gap.

## Current Layout

```text
Magnification/
├── app.py        # Flask entry point
├── docs/         # Source of truth: docs, plans, canonical skills
├── utils/        # All application code
│   ├── backend/  # Blueprints, scrapers, recommender, agents, database, scheduler
│   ├── frontend/ # The single served page + static assets
│   └── LocalLLM/ # Self-contained local-LLM management library
├── tests/        # Lightweight offline tests, grouped by area
├── deploy/       # systemd units + the jobsctl wrapper
├── config/       # Runtime JSON config (gitignored)
├── data/         # SQLite database + generated artifacts (gitignored)
└── images/       # Brand assets + README media
```

There is no `libs/` directory: nothing here is a shared internal package. If code is ever extracted
for reuse across projects, add `libs/` then — not preemptively.

**Known deviation:** the web-interface convention (`structures/web-interfaces.md`) puts web code
under `web/`. This repo keeps it under `utils/` + `app.py`. That migration is deferred and tracked
in `docs/checklist.md`; do not start it as a side effect of other work.

## Rules

### Documentation

- `docs/structure.md` is mandatory and must be updated in the same change that adds, moves, or
  removes a file or directory.
- Documentation never lives in an agent folder (`.claude/`, `.agents/`, `.cursor/`) — those hold
  pointer files only.

### Application code (`utils/`)

- A small utility is one file directly under its package; anything with real internal structure gets
  its own sub-package.
- Every Python sub-package has an `__init__.py`.
- Pure logic (predicates, formatters, normalizers) belongs in an I/O-free module so it can be tested
  without a database or a network — `scrapers/profile_filter.py` and `recommend/compensation.py` are
  the pattern to copy.

### Tests (`tests/`)

- `tests/<area>/test_<behavior>.py`, mirroring the package the code lives in.
- Tests are offline: no network, no live LLM. Mock the client, or skip when a model isn't cached.
- Tests that touch the database must isolate themselves — every worktree shares the real
  `data/magnificiation.db`. See `docs/workflow.md`.

### File length

- Hard cap 800 lines; aim under 500. Split logic into modules rather than growing a file.
- One accepted exception: `utils/frontend/templates/index.html`, a single-file design export whose
  runtime requires the component class inline. Documented in `docs/component-map.md`.

### Package management

`uv` only — `uv add`, `uv sync`, `uv run`. Do not add pip or conda workflows to committed
instructions.

## Related

- `structures/web-interfaces.md` — the web-layout modes, including the `web/` convention this repo
  currently deviates from.
- `docs/skills/website-architecture/SKILL.md` — owns routes, app mode, data flow, and the
  design-quality gate for any web work.
