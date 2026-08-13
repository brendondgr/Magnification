# Repository Structure — Magnification

Canonical repository tree and the reason each top-level path exists. Keep this file current when files or directories are added, moved, or removed (see `docs/skills/global-project-rules/SKILL.md`).

> **Note on layout:** The web-interface convention (`docs/skills/repository-structure/structures/web-interfaces.md`) places web code under `web/`. Magnification currently keeps web code under `utils/` + `app.py`; the `web/` migration is a deferred task in `docs/checklist.md`.

## Tree

```text
Magnification/
├── app.py                      # Flask entry point: registers blueprints, runs migrations, serves the page
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
│   ├── design-system.md        # Visual motif, tokens, motion + loading ladder, UI states
│   ├── frontend-polish-spec.md # Adopted contract: motion, loading states, responsiveness
│   ├── database.md             # Schema, migrations, operations layer
│   ├── job_scraping.md         # Scraping pipeline reference
│   ├── find_jobs.md            # Find-Jobs config + run flow
│   ├── recommendation.md       # Hybrid RAG + LLM recommender
│   ├── profile.md              # Résumé → profile builder
│   ├── assets/                 # Static SVG diagrams embedded in README.md
│   ├── plans/                  # Implementation/handoff plans
│   └── skills/                 # Canonical agent skills (source of truth)
│       ├── global-project-rules/
│       ├── planner/
│       ├── repository-structure/
│       ├── website-architecture/
│       ├── accessibility-mobile/
│       └── portfolio-readme/
│
├── .claude/skills/             # Claude Code pointer files → docs/skills
├── .agents/skills/             # OpenAI Codex pointer files → docs/skills
├── .cursor/rules/              # Cursor .mdc pointer rules → docs/skills
│
├── utils/                      # All application Python + frontend assets
│   ├── backend/
│   │   ├── paths.py            # get_project_root() — one data/config root shared by every worktree
│   │   ├── routes/             # The ten blueprints (see docs/routes.md for the full map)
│   │   ├── scrapers/           # Scraping pipeline (see docs/job_scraping.md)
│   │   ├── llm/                # OpenAI-compatible client + endpoint config
│   │   ├── recommend/          # Hybrid recommender + the one shared enrichment pass (docs/recommendation.md)
│   │   ├── agents/             # In-house generation graphs, no LangGraph (see the rationale table below)
│   │   ├── pdf_compile.py      # Compile document LaTeX → PDF via pdflatex; cached under data/generated_pdfs/
│   │   ├── database/           # Models, init, CRUD, idempotent migrations (see docs/database.md)
│   │   └── scheduler/          # LLM-gated daily search runner + CLI (llm_health, daily_runner, __main__)
│   ├── frontend/
│   │   ├── templates/          # index.html — single dc-runtime design export (no Jinja partials)
│   │   └── static/             # js/dc-runtime.js (vendored React runtime), img/ (brand mark + favicons)
│   └── LocalLLM/               # Local LLM management library (cli, core, server, utils)
│
├── tests/                      # Lightweight offline tests grouped by area
│   ├── test_config_loading.py  # Job-search config load/save
│   ├── test_frontend_wiring.py # Served page + job/config API contract
│   ├── job_scraper.py          # Manual scraper probe (hits the network; not a pytest module)
│   ├── agents/                 # Generation graphs, orchestrator, guidance, scoring, LaTeX
│   ├── backend/                # Shared project-root resolution, lazy jobs feed
│   ├── database/               # CRUD, migrations, pipeline dates, clear-scope (in-memory engines)
│   ├── docs/                   # Doc/skill-pointer + doc-link verification
│   ├── documents/              # Documents, generation, and PDF-route APIs
│   ├── frontend/               # Theme-token parity + the loading/motion/a11y contract of the served page
│   ├── llm/                    # OpenAI-compatible client + Options API
│   ├── profile/                # Profile API, blocklists, résumé parsing, skill quick-add
│   ├── recommend/              # Ranker, BM25, embedder, enrichment, analyze/gap-fill, rescore
│   ├── scheduler/              # LLM-health probe + once-per-day runner (mocked)
│   └── scrapers/               # Cleaning, dedupe, iterations, cumulative counts, events
│
├── images/                     # Brand source assets (magnify.svg / magnify.png) + README screenshots/demo
│
├── deploy/                     # Deployment assets (not app code)
│   ├── bin/                    # jobsctl — `jobs start|stop|restart|status|logs|search` app-control wrapper
│   └── systemd/                # User units: web app (magnification-web.service) + LLM-gated daily search (.service/.timer) + install.sh/uninstall.sh
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
| `utils/backend/` | API routes, scraping pipeline, database layer, the cover-letter/résumé generation graphs, and the scheduled daily-search runner. |
| `utils/backend/agents/` | In-house, plain-Python agents (no LangGraph): `orchestrator.py` drives a node pipeline with progress events and semi-automatic checkpoints; `context.py` loads the job, analysis, and profile; `nodes_shared.py` + `nodes_cover_letter.py` / `nodes_resume.py` hold the nodes; `service.py` runs a graph in a daemon thread; `latex.py` renders the result deterministically. Both graphs are steered by the single editable **Document Guidance** (`document_guidance.py`, persisted to `config/document_guidance.json`) on the first pass and every refine, and `utils/backend/pdf_compile.py` compiles the LaTeX to a cached PDF. (The former ingestion agent and the Behavioral/Writing/Template subsystems were retired — see `docs/plans/documents-sidebar-simplify.md`.) |
| `utils/backend/scheduler/` | LLM-gated, once-per-day job-search runner + CLI invoked by the systemd units. |
| `deploy/systemd/` | Systemd **user** units + installer for the web app on boot and the automated daily search (see `deploy/systemd/README.md`). |
| `utils/frontend/` | The single served page (`templates/index.html`) and its static assets (`static/js/dc-runtime.js`, `static/img/`). No build step, no partials. |
| `images/` | Source brand assets plus README media. `images/magnify.svg` is the canonical logo; the copy served to the browser lives at `utils/frontend/static/img/magnify.svg`. `FullBodyScreenshot.png` / `InProgressJobSearch.png` are the README screenshots, and `FullAppOverview-web.webm` / `.mp4` are the compressed walkthrough (1280×660, 24 fps — re-encode any new capture the same way; the full-size master stays out of git via `.gitignore`). |
| `utils/LocalLLM/` | Self-contained local-LLM management library. |
| `tests/` | Lightweight, area-grouped tests. |
| `data/` | Local SQLite DB and runtime data (gitignored). |

## Conventions

- Python sub-packages include `__init__.py`.
- Files target < 500 lines, hard cap 800; split larger logic into modules.
- `uv` is the only package manager (`uv add`, `uv sync`, `uv run`).
