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
│   │   ├── routes/             # Flask blueprints: config, scrape, job, llm, options, documents (per-job job-evaluation + generated-documents read), guidance (editable Document Guidance: GET/PUT /api/document-guidance, POST .../reset), document_generation (cover-letter/résumé generation: start, status/<task_id>, <task_id>/resume, GET/PATCH <doc_id>, GET <doc_id>/pdf, GET <doc_id>/tex)
│   │   ├── scrapers/           # Scraping pipeline (jobspy wrapper, concurrent, linkedin, filter, service)
│   │   ├── llm/                # OpenAI-compatible client + endpoint config (recommendation system)
│   │   ├── recommend/          # RAG/LLM recommendation: embedder, bm25, ranker, skills, compensation, service, keywords, profile_builder, runtime_config
│   │   ├── agents/             # In-house agents (no LangGraph): orchestrator.py (node-pipeline driver: progress + semi-auto checkpoints), context.py (DB read: job/JobAnalysis/profile + the editable Document Guidance), scoring.py (résumé match-lift via recommend/ranker), prompts.py, document_guidance.py (the single editable house-style document — default = cover-letter Winning Formula + résumé tailoring principles — persisted to config/document_guidance.json and injected into every generation & refine), nodes_shared.py (research/evaluate/truthfulness + guidance_preamble), nodes_cover_letter.py + cover_letter.py (cover-letter graph, incl. the refine_flow forced-fit audit→rewrite stage), nodes_resume.py + resume.py (résumé fine-tuner graph), service.py (generation_tasks store + daemon-thread runner), latex.py (deterministic offline LaTeX assembly — wraps graph prose into a compilable single-column `article`)
│   │   ├── pdf_compile.py      # Compile document LaTeX → PDF via pdflatex; cache under data/generated_pdfs/
│   │   ├── database/           # SQLAlchemy models (Job, ApplicationStatus, Profile, JobAnalysis, + per-job generation tables job_evaluations/generated_documents), init, CRUD, idempotent migrations (incl. migrate_job_saved, migrate_job_pipeline_dates — durable write-once tracker dates + backfill), documents_ops.py
│   │   └── scheduler/          # LLM-gated daily job-search runner + CLI (systemd-driven: llm_health, daily_runner, __main__)
│   ├── frontend/
│   │   ├── templates/          # index.html — single dc-runtime design export (no Jinja partials)
│   │   └── static/             # js/dc-runtime.js (vendored React runtime)
│   └── LocalLLM/               # Local LLM management library (cli, core, server, utils)
│
├── tests/                      # Lightweight tests grouped by area
│   ├── job_scraper.py
│   ├── test_config_loading.py
│   ├── test_frontend_wiring.py # dc-runtime page + job/config API contract
│   ├── agents/                 # Generation-graph + guidance + LaTeX builder tests (test_cover_letter_*.py, test_resume_graph.py, test_document_guidance.py, test_latex.py)
│   ├── documents/              # Documents API tests (test_documents_api.py, test_pdf_route.py)
│   ├── database/               # Profile + JobAnalysis CRUD round-trip, incl. test_agentic_documents.py for the new documents-foundation tables
│   ├── scheduler/              # LLM-health probe + once-per-day runner (offline, mocked)
│   └── docs/                   # Doc/skill-pointer verification tests
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
| `utils/backend/agents/` | In-house, plain-Python agents (no LangGraph): the cover-letter and résumé generation graphs (orchestrator, context loader, résumé match-lift scoring, shared/letter/résumé node modules, generation task-store service). Both are steered by the single editable **Document Guidance** (`document_guidance.py`) injected into every generation and refine, and end with a deterministic render step (`latex.py`) that wraps their prose into a compilable LaTeX document; `utils/backend/pdf_compile.py` compiles that source to a cached PDF for preview/download. (The former ingestion agent + Behavioral/Writing/Template subsystems were retired — see `docs/plans/documents-sidebar-simplify.md`.) |
| `utils/backend/scheduler/` | LLM-gated, once-per-day job-search runner + CLI invoked by the systemd units. |
| `deploy/systemd/` | Systemd **user** units + installer for the web app on boot and the automated daily search (see `deploy/systemd/README.md`). |
| `utils/frontend/` | Jinja templates and static CSS/JS assets. |
| `utils/LocalLLM/` | Self-contained local-LLM management library. |
| `tests/` | Lightweight, area-grouped tests. |
| `data/` | Local SQLite DB and runtime data (gitignored). |

## Conventions

- Python sub-packages include `__init__.py`.
- Files target < 500 lines, hard cap 800; split larger logic into modules.
- `uv` is the only package manager (`uv add`, `uv sync`, `uv run`).
