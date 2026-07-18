# Magnification — Project Documentation

## Purpose

Magnification ("Job Finder") is a personal job-search application. It scrapes job listings from multiple boards, stores them in a local database, and presents them through a web UI where the user can review new jobs, track applications on a kanban board, and get **recommendations**: a RAG + LLM system builds a profile from the user's résumé and scores each scraped job against it (semantic + BM25 + keyword-group + skill signals, with an optional LLM verdict). See `docs/recommendation.md` and `docs/profile.md`.

Primary users: the developer (single-user, local-first). It is not a multi-tenant or publicly deployed app at this stage.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Language / runtime | Python ≥ 3.12, managed with `uv` |
| Web framework | Flask (server-rendered Jinja, blueprint-based API) |
| Frontend | Single `index.html` design export driven by a vendored `dc-runtime.js` (React runtime); no build step |
| Database | SQLite via SQLAlchemy ORM (`Job`, `ApplicationStatus`, `Profile`, `JobAnalysis`) |
| Scraping | `python-jobspy` + a custom concurrent scraper and a parallel LinkedIn description scraper |
| Recommendation | `fastembed` (bge-small-en-v1.5, CPU) + `rank-bm25`; `pypdf` for résumé parsing; `utils/backend/recommend` |
| LLM | OpenAI-compatible client (`utils/backend/llm`, configurable endpoint) for all AI features; `utils/LocalLLM` still manages an optional bundled llama-server |
| Logging | `loguru` (wrapped by `LoggerWrapper`) |

## Architecture (current)

Magnification is a **Flask/Jinja monolith** (Mode F in `docs/skills/repository-structure/structures/web-interfaces.md`):

- `app.py` boots Flask, registers the blueprints (config, scrape, job, llm, options, profile, recommend), initializes the SQLite database and logger, and serves the dc-runtime `index.html`. It listens on port **13374** by default (`PORT` overrides; `FLASK_DEBUG=0` disables the reloader) and can run on boot via `deploy/systemd/magnification-web.service`.
- `utils/backend/` holds the API blueprints, scraping pipeline, and database layer.
- `utils/frontend/` holds Jinja templates (`templates/`) and static assets (`static/css`, `static/js`).
- `utils/LocalLLM/` is a self-contained local-LLM management library exposed through the `llm` blueprint.

See `docs/architecture.md` for the full web-architecture breakdown, `docs/routes.md` for the route map, `docs/api-contract.md` for endpoint contracts, and `docs/data-flow.md` for how data moves.

## Domain Deep-Dives

These existing references remain canonical for their subsystems:

- `docs/database.md` — database schema and models
- `docs/job_scraping.md` — the scraping pipeline
- `docs/find_jobs.md` — the "Find Jobs" configuration/flow
- `docs/recommendation.md` — the RAG + LLM recommendation system
- `docs/profile.md` — the résumé → profile builder
- `docs/ui.md` — UI notes
- `docs/plans/agentic-documents-system.md` — design for the agentic documents system (in-house ingestion agent + cover-letter/résumé generation)

## Major Decisions

- **`docs/` is the single source of truth.** Agent tool folders (`.claude/`, `.agents/`, `.cursor/`) contain only pointer files. See `docs/skills/global-project-rules/SKILL.md`.
- **`uv` is the package/environment manager** for all Python work.
- **Current code layout is retained** under `utils/` + `app.py`. The initializer's `web/` convention and a React frontend overhaul are deferred (tracked in `docs/checklist.md`).

## Current Status

- Working Flask app: scraping, job listing/tracking, LLM management endpoints.
- **RAG + LLM recommendation overhaul complete:** Profile + Options menus, résumé→profile
  builder, configurable OpenAI-compatible endpoint, fastembed + BM25 hybrid scoring with
  optional LLM verdict, parallel LinkedIn fetch, multi-country + job-type + LLM-keyword Find Jobs.
- **UI/UX refinements complete:** cleaner New Jobs cards (no company icon, relocated match %
  with a breakdown popover + color tiers, YYYY-MM-DD dates), a stylized résumé drag-and-drop +
  "Build Profile (LLM)" action, a unified searchable country selector, Find Jobs prefilled from
  the active profile, a live step-by-step scraping activity feed, and LLM compensation extraction
  that recovers pay from job descriptions (e.g. LinkedIn).
- **Pipeline + scoring refinements complete:** LinkedIn description fetch is serial (rate-limit
  safe); analysis scores only the keyword-filtered remainder, ranks by semantic+bm25, sends the
  top 30 to the LLM for a 2–3 sentence fit verdict, and folds that verdict into the score (LLM
  weight 0.40, renormalized when unavailable); score weights are sliders that must total 1.0.
- **Automated daily search complete:** `utils/backend/scheduler` + `deploy/systemd/`
  user units run the scrape on boot and daily, **gated on the LLM being reachable**
  (re-checks every 10 min ×6, else skips the day; once-per-day stamp). See
  `docs/plans/systemd-daily-search.md`.
- **Agentic Documents foundation complete:** data layer (behavioral/writing-style profiles,
  templates, job evaluations), the in-house ingestion agent, and a tabbed "Profile & Documents"
  sidebar have shipped; the cover-letter/résumé generation graphs and Application Mode remain
  deferred. See `docs/plans/agentic-documents-system.md`.
- **Reasoning-endpoint LLM fitting fixed:** the OpenAI-compatible client suppresses a
  reasoning model's hidden chain-of-thought by default (`disable_thinking`, toggle in
  Options → LLM Endpoint), so verdict/skill/compensation calls stop exhausting `max_tokens`
  on reasoning and return parseable JSON; verdict parsing also tolerates nested/string score
  shapes. This is what "Analyze Matches" needs to fit **every** job rather than a couple per
  run. See `docs/plans/llm-fit-reasoning-exhaustion.md`.
- **Next:** physical migration to `web/` and a full React frontend rebuild — not started.
