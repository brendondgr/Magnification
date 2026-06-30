# Magnification

A local-first **job-search application**: scrape job boards, store listings in SQLite, and review/track them through a Flask web UI — with an optional local LLM for assistance.

## Quick Start

```bash
uv sync          # install dependencies
uv run app.py    # start the Flask dev server → http://127.0.0.1:5000
```

Requires Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/).

## Documentation

All project documentation lives under [`docs/`](docs/) and is the single source of truth:

- [`docs/documentation.md`](docs/documentation.md) — purpose, stack, architecture, status
- [`docs/structure.md`](docs/structure.md) — repository layout
- [`docs/workflow.md`](docs/workflow.md) — commands, environment, git, docs rules
- [`docs/architecture.md`](docs/architecture.md) · [`docs/routes.md`](docs/routes.md) · [`docs/api-contract.md`](docs/api-contract.md) · [`docs/data-flow.md`](docs/data-flow.md) — web architecture
- [`docs/design-system.md`](docs/design-system.md) — visual system
- [`docs/checklist.md`](docs/checklist.md) — active and deferred work

## Agents & Skills

Agent-facing skills are canonical under [`docs/skills/`](docs/skills/). Start with
[`docs/skills/global-project-rules/SKILL.md`](docs/skills/global-project-rules/SKILL.md).
Tool pointer files live in `.claude/skills/`, `.agents/skills/` (Codex), and `.cursor/rules/`.
