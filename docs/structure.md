# Repository Structure — Magnification

Canonical repository tree and the reason each top-level path exists. Keep this file current when files or directories are added, moved, or removed (see `docs/skills/global-project-rules/SKILL.md`).

> **Note on layout:** The web-interface convention (`docs/skills/repository-structure/structures/web-interfaces.md`) places web code under `web/`. Magnification currently keeps web code under `utils/` + `app.py`; the `web/` migration is a deferred task in `docs/checklist.md`.

## Tree

```text
Magnification/
├── app.py                      # Flask entry point: registers blueprints, serves index + partials
├── main.py                     # Stub entry (uv default); app is launched via app.py
├── pyproject.toml              # Project metadata + dependencies (uv)
├── uv.lock                     # Locked dependency versions
├── requirements.txt            # Legacy pip dependency list (mirrors pyproject)
├── .python-version             # Python version pin
├── README.md                   # Points to docs/ and summarizes setup
│
├── docs/                       # SINGLE SOURCE OF TRUTH — all project docs
│   ├── documentation.md        # Project purpose, stack, architecture, status
│   ├── structure.md            # This file
│   ├── workflow.md             # Install/run/test/lint commands, env, git, docs rules
│   ├── checklist.md            # Active checklist + deferred work
│   ├── architecture.md         # Web architecture (mode, stack, boundaries)
│   ├── routes.md               # Route/page + API endpoint map
│   ├── api-contract.md         # Request/response contracts for API endpoints
│   ├── component-map.md        # Frontend template/JS/CSS ownership
│   ├── data-flow.md            # Where data comes from and how it moves
│   ├── deployment.md           # Runtime, build, deploy assumptions
│   ├── design-system.md        # Visual motif, tokens, UI states
│   ├── database.md             # Database schema deep-dive
│   ├── job_scraping.md         # Scraping pipeline deep-dive
│   ├── find_jobs.md            # Find-Jobs flow deep-dive
│   ├── ui.md                   # UI notes
│   ├── plans/                  # Implementation/handoff plans
│   └── skills/                 # Canonical agent skills (source of truth)
│       ├── global-project-rules/
│       ├── planner/
│       ├── repository-structure/
│       ├── website-architecture/
│       └── accessibility-mobile/
│
├── .claude/skills/             # Claude Code pointer files → docs/skills
├── .agents/skills/             # OpenAI Codex pointer files → docs/skills
├── .cursor/rules/              # Cursor .mdc pointer rules → docs/skills
│
├── utils/                      # All application Python + frontend assets
│   ├── backend/
│   │   ├── routes/             # Flask blueprints: config, scrape, job, llm, options
│   │   ├── scrapers/           # Scraping pipeline (jobspy wrapper, concurrent, linkedin, filter, service)
│   │   ├── llm/                # OpenAI-compatible client + endpoint config (recommendation system)
│   │   ├── recommend/          # RAG/LLM recommendation: embedder, bm25, ranker, skills, service, keywords, profile_builder, runtime_config
│   │   └── database/           # SQLAlchemy models (Job, ApplicationStatus, Profile, JobAnalysis), init, CRUD
│   ├── frontend/
│   │   ├── templates/          # index.html — single dc-runtime design export (no Jinja partials)
│   │   └── static/             # js/dc-runtime.js (vendored React runtime)
│   └── LocalLLM/               # Local LLM management library (cli, core, server, utils)
│
├── tests/                      # Lightweight tests grouped by area
│   ├── job_scraper.py
│   ├── test_config_loading.py
│   ├── test_frontend_wiring.py # dc-runtime page + job/config API contract
│   ├── database/               # Profile + JobAnalysis CRUD round-trip
│   └── docs/                   # Doc/skill-pointer verification tests
│
└── data/                       # SQLite database + local data (gitignored)
```

## Top-Level Rationale

| Path | Purpose |
| --- | --- |
| `app.py` | Application entry point; wires blueprints, DB init, logger, and static/template folders. |
| `docs/` | Source of truth: project docs, plans, and canonical skills. |
| `docs/skills/` | Canonical skill definitions; agent folders only point here. |
| `.claude/`, `.agents/`, `.cursor/` | Tool-specific pointer files. No canonical content. |
| `utils/backend/` | API routes, scraping pipeline, and database layer. |
| `utils/frontend/` | Jinja templates and static CSS/JS assets. |
| `utils/LocalLLM/` | Self-contained local-LLM management library. |
| `tests/` | Lightweight, area-grouped tests. |
| `data/` | Local SQLite DB and runtime data (gitignored). |

## Conventions

- Python sub-packages include `__init__.py`.
- Files target < 500 lines, hard cap 800; split larger logic into modules.
- `uv` is the only package manager (`uv add`, `uv sync`, `uv run`).
