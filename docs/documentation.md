# Magnification — Project Documentation

## Purpose

Magnification ("Job Finder") is a personal, local-first job-search application. It scrapes job
listings from multiple boards, stores them in a local SQLite database, ranks each one against a
profile built from the user's résumé, drafts tailored application documents, and presents all of it
through a single-page web UI with a review queue and an application tracker.

Primary user: the developer. It is not multi-tenant and is not publicly deployed.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Language / runtime | Python ≥ 3.12, managed with `uv` |
| Web framework | Flask — ten JSON API blueprints plus one page route |
| Frontend | One `index.html` design export hydrated by a vendored runtime (`static/js/dc-runtime.js`); no build step |
| Database | SQLite via SQLAlchemy (`Job`, `ApplicationStatus`, `Profile`, `JobAnalysis`, plus per-job `job_evaluations` / `generated_documents`) |
| Scraping | `python-jobspy` + a custom concurrent scraper and a serial LinkedIn description fetch |
| Recommendation | `fastembed` (bge-small-en-v1.5, CPU) + `rank-bm25` + keyword/skill signals; `pypdf` for résumé parsing |
| Document generation | In-house agent graphs in `utils/backend/agents/` (no LangGraph) → LaTeX → PDF via `pdflatex` |
| LLM | Any OpenAI-compatible endpoint (`utils/backend/llm`); `utils/LocalLLM` separately manages an optional bundled llama-server |
| Logging | `loguru`, wrapped by `LoggerWrapper` |

## Architecture

A Flask monolith (Mode F in `docs/skills/repository-structure/structures/web-interfaces.md`):

- `app.py` registers the ten blueprints, runs `init_database()` (table creation + idempotent
  migrations), initializes the logger, and serves `index.html` on `/`. It listens on port **13374**
  by default (`PORT` overrides, `FLASK_DEBUG=0` disables the reloader) and can run on boot via
  `deploy/systemd/magnification-web.service`.
- `utils/backend/` holds the blueprints, scraping pipeline, recommender, agent graphs, database
  layer, and the scheduled daily-search runner.
- `utils/frontend/` holds the single page and its static assets.
- `utils/LocalLLM/` is a self-contained local-LLM management library exposed through the `llm`
  blueprint. The recommendation and generation features do **not** use it — they talk to the
  configurable OpenAI-compatible endpoint instead.

Long-running work (scrape, analyze, generate) follows one pattern: `POST .../start` spawns a daemon
thread and returns a task id; the client polls `.../status/<id>` for progress, events, and results.
Task stores are in-memory and do not survive a restart.

See `docs/architecture.md` (web layer), `docs/routes.md` (route map), `docs/api-contract.md`
(endpoint contracts), and `docs/data-flow.md` (how data moves).

## Subsystem References

- `docs/database.md` — schema, migrations, and the operations layer
- `docs/job_scraping.md` — the scraping pipeline
- `docs/find_jobs.md` — the Find Jobs configuration and run flow
- `docs/recommendation.md` — the hybrid RAG + LLM recommender
- `docs/profile.md` — the résumé → profile builder
- `docs/component-map.md` — which part of `index.html` owns which UI
- `docs/design-system.md` — themes, tokens, and required UI states
- `docs/deployment.md` — runtime and systemd assumptions

## Major Decisions

- **`docs/` is the single source of truth.** `.claude/`, `.agents/`, and `.cursor/` hold pointer
  files only. See `docs/skills/global-project-rules/SKILL.md`.
- **`uv` is the only package/environment manager.**
- **Runtime paths resolve through `utils/backend/paths.get_project_root()`** (`git rev-parse
  --git-common-dir`), so every worktree shares one database and one config directory.
- **Agents are hand-rolled**, not LangGraph: plain-Python nodes driven by
  `utils/backend/agents/orchestrator.py`, with semi-automatic checkpoints.
- **One editable Document Guidance doc** steers both generation graphs, on the first pass and every
  refine. The earlier behavioral/writing-style/template subsystems were removed.
- **One shared enrichment pass.** Compensation and industry are extracted from the job description
  by `recommend/enrichment.enrich_jobs`, called by both the scrape pipeline and Analyze Matches.
- **Current layout is retained** under `utils/` + `app.py`; the `web/` migration and a React rebuild
  are deferred (`docs/checklist.md`).

## Status

The application is feature-complete for daily use: scraping, hybrid ranking with an optional LLM fit
verdict, profile building and blocklists, saved-jobs and tracker workflows, cover-letter and résumé
generation with LaTeX/PDF output, and an LLM-gated daily scrape under systemd.

What is not done, in `docs/checklist.md`: the `web/` migration and React rebuild, `ruff`, browser
automation for application submission, and a set of paths that are covered by mocked tests but have
never been exercised against a live LLM endpoint or a live scrape.
