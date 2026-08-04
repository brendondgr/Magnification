<p align="center">
  <img src="images/magnify.svg" alt="Magnification logo — a penguin inspecting the world through a magnifying glass" width="132">
</p>

<h1 align="center">Magnification</h1>

<p align="center"><em>Track · Apply · Land</em></p>

A local-first job-search platform: it scrapes job boards on a schedule, ranks every listing against
your résumé with a hybrid RAG + LLM recommender, drafts tailored cover letters and résumés, and
gives you a web UI to review, save, and track applications through a kanban board.

No hosted demo — it's a single-user, local-first app by design (see [Setup](#setup) to run it), so
here's what it looks like instead.

<p align="center">
  <img src="images/FullBodyScreenshot.png" alt="The New Jobs queue: a grid of scraped listings, each showing its source board, industry, match percentage, location, salary, and description preview, with Generate/Applied actions and a pipeline sidebar" width="900">
</p>

<p align="center"><sub><strong>The New Jobs queue</strong> — every scraped listing scored against your résumé and sorted by match.<br>
▶ <a href="images/FullAppOverview-web.webm">Watch the 37-second walkthrough</a> (WebM, 1 MB · <a href="images/FullAppOverview-web.mp4">MP4</a>)</sub></p>

## Overview

Job searching means checking a dozen boards a day and re-reading listings you've already dismissed.
Magnification automates the first half and augments the second: a scheduler pulls new listings from
multiple boards, a hybrid recommender scores each one against a profile built from your résumé, and
a web UI turns the results into a working queue — new jobs, saved jobs, and an application tracker.

![Pipeline: job boards → scraper → SQLite → hybrid recommender → web UI](docs/assets/pipeline-diagram.svg)

## Tech Stack

- **Python 3.12+ / Flask** — ten API blueprints; the UI is one server-rendered page driven by a
  vendored React runtime, so there is no build step
- **SQLite via SQLAlchemy** — four core models plus per-job document tables, with idempotent
  migrations that run on startup
- **`python-jobspy`** plus a custom concurrent scraper for multi-board, multi-country scraping
- **Hybrid recommender** — `fastembed` (bge-small-en-v1.5, CPU) semantic similarity + `rank-bm25`
  + keyword-group and skill signals + an optional LLM fit verdict, combined with tunable weights
- **`pypdf`** for résumé parsing, and any OpenAI-compatible LLM endpoint (local or hosted) for
  profile building, fit verdicts, enrichment, and document generation
- **systemd** user units for an LLM-gated daily scrape

## Key Features

- **Hybrid job ranking** — semantic + BM25 + keyword groups + skills + an optional LLM verdict,
  under user-tunable score weights that must sum to 1.0
- **Résumé → profile pipeline** — drop in a résumé, get an editable structured profile (skills,
  keyword groups, company/title blocklists) that retroactively hides matches you don't want
- **Document generation** — in-house agent graphs draft a cover letter or a tailored résumé per
  job, steered by one editable Document Guidance doc, and render to LaTeX → PDF
- **Review workflow** — New Jobs → save or hide → a five-column application tracker with durable,
  write-once pipeline dates
- **LLM-gated daily automation** — a systemd timer scrapes on boot and daily, but only once the
  configured LLM answers (retries every 10 min for up to an hour, otherwise skips the day)

<p align="center">
  <img src="images/InProgressJobSearch.png" alt="The Find Jobs panel mid-scrape: a 38 percent progress ring, counters for jobs found, jobs saved, and not hidden, and a timestamped live activity log" width="480">
</p>

<p align="center"><sub>A scrape in progress — per-iteration progress and a timestamped activity log, with counters cumulative across all iterations.</sub></p>

## Setup

```bash
uv sync
```

```bash
uv run app.py
```

The app starts on `http://127.0.0.1:13374`. Requires Python ≥ 3.12 and
[`uv`](https://docs.astral.sh/uv/); `PORT` overrides the port and `FLASK_DEBUG=0` disables the dev
reloader. If `uv sync` fails to build `regex` from source, install the recommender's dependencies
as wheels instead — see [`docs/workflow.md`](docs/workflow.md).

LLM features (profile building, fit verdicts, enrichment, document generation) need an
OpenAI-compatible endpoint configured in **Options → LLM Endpoint**. The app runs without one; those
features fall back or stay idle. For the daily-scrape units, see [`deploy/systemd/`](deploy/systemd/).

## Architecture

- [`app.py`](app.py) — Flask entry point: registers the blueprints, runs migrations, serves the UI
- [`utils/backend/`](utils/backend/) — API blueprints, scraping pipeline, database layer, scheduler
- [`utils/backend/recommend/`](utils/backend/recommend/) — the hybrid recommender and the shared
  description-enrichment pass
- [`utils/backend/agents/`](utils/backend/agents/) — the cover-letter and résumé generation graphs
- [`utils/backend/llm/`](utils/backend/llm/) — OpenAI-compatible client + endpoint config
- [`utils/frontend/`](utils/frontend/) — the single-page UI (no build step)
- [`deploy/systemd/`](deploy/systemd/) — boot + daily-timer units

![LLM-gated daily scheduler: boot/timer → check LLM → retry up to 6x → run or skip](docs/assets/scheduler-flow.svg)

## Design Decisions

- **Every worktree shares one data root.** Runtime paths resolve through
  `git rev-parse --git-common-dir`, not `__file__`, because git worktrees don't share gitignored
  files — each checkout was silently getting its own empty database.
- **Reasoning models get a token budget, not a ban.** A reasoning endpoint can spend its whole
  `max_tokens` on hidden chain-of-thought and return nothing parseable. The client sends a
  `thinking_token_budget` and raises `max_tokens` to match, so the answer still fits.
- **One enrichment pass, two callers.** Compensation and industry are extracted from the job
  description by a single shared function that both the scrape and the analysis path call, rather
  than two implementations that drift.

## Roadmap

- [ ] Migrate web code into a `web/` layout and rebuild the frontend in React
- [ ] Add `ruff` for lint + format

## Documentation

All project documentation lives under [`docs/`](docs/) and is the single source of truth:

- [`docs/documentation.md`](docs/documentation.md) — purpose, stack, architecture, status
- [`docs/structure.md`](docs/structure.md) — repository layout
- [`docs/workflow.md`](docs/workflow.md) — commands, environment, git, docs rules
- [`docs/architecture.md`](docs/architecture.md) · [`docs/routes.md`](docs/routes.md) · [`docs/api-contract.md`](docs/api-contract.md) · [`docs/data-flow.md`](docs/data-flow.md) — web architecture
- [`docs/design-system.md`](docs/design-system.md) · [`docs/component-map.md`](docs/component-map.md) — UI
- [`docs/checklist.md`](docs/checklist.md) — shipped work and what's still open

## Agents & Skills

Agent-facing skills are canonical under [`docs/skills/`](docs/skills/). Start with
[`docs/skills/global-project-rules/SKILL.md`](docs/skills/global-project-rules/SKILL.md).
Pointer files for Claude Code, Codex, and Cursor live in `.claude/skills/`, `.agents/skills/`, and
`.cursor/rules/` and contain no canonical content.
