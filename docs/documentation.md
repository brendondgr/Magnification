# Magnification — Project Documentation

## Purpose

Magnification ("Job Finder") is a personal job-search application. It scrapes job listings from multiple boards, stores them in a local database, and presents them through a web UI where the user can review new jobs, track applications on a kanban board, and optionally run a local LLM to assist with job descriptions.

Primary users: the developer (single-user, local-first). It is not a multi-tenant or publicly deployed app at this stage.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Language / runtime | Python ≥ 3.12, managed with `uv` |
| Web framework | Flask (server-rendered Jinja, blueprint-based API) |
| Frontend | HTML + Jinja partials, vanilla JS modules, Tailwind (CDN), FontAwesome/Lucide icons |
| Database | SQLite via SQLAlchemy ORM |
| Scraping | `python-jobspy` + a custom concurrent scraper and LinkedIn description scraper |
| Local LLM | `utils/LocalLLM` — llama-server management, model downloads, GPU detection |
| Logging | `loguru` (wrapped by `LoggerWrapper`) |

## Architecture (current)

Magnification is a **Flask/Jinja monolith** (Mode F in `docs/skills/repository-structure/structures/web-interfaces.md`):

- `app.py` boots Flask, registers four blueprints (config, scrape, job, llm), initializes the SQLite database and logger, and serves the SPA-style `index.html` plus its HTML partials.
- `utils/backend/` holds the API blueprints, scraping pipeline, and database layer.
- `utils/frontend/` holds Jinja templates (`templates/`) and static assets (`static/css`, `static/js`).
- `utils/LocalLLM/` is a self-contained local-LLM management library exposed through the `llm` blueprint.

See `docs/architecture.md` for the full web-architecture breakdown, `docs/routes.md` for the route map, `docs/api-contract.md` for endpoint contracts, and `docs/data-flow.md` for how data moves.

## Domain Deep-Dives

These existing references remain canonical for their subsystems:

- `docs/database.md` — database schema and models
- `docs/job_scraping.md` — the scraping pipeline
- `docs/find_jobs.md` — the "Find Jobs" configuration/flow
- `docs/ui.md` — UI notes

## Major Decisions

- **`docs/` is the single source of truth.** Agent tool folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointer files. See `docs/skills/global-project-rules/SKILL.md`.
- **`uv` is the package/environment manager** for all Python work.
- **Current code layout is retained** under `utils/` + `app.py`. The initializer's `web/` convention and a React frontend overhaul are deferred (tracked in `docs/checklist.md`).

## Current Status

- Working Flask app: scraping, job listing/tracking, LLM management endpoints.
- Documentation and agent skills initialized per `bdgrSkills/initialize.md` (this overhaul).
- **Next:** physical migration to `web/` and a React frontend rebuild — not started.
