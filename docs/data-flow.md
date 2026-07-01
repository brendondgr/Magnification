# Data Flow — Magnification

How data enters, moves through, and reaches the UI. Source: `utils/backend/`, `app.py`.

## Sources

- **Job boards** via `python-jobspy` and a custom LinkedIn description scraper — the primary external data source.
- **SQLite database** (`data/*.db`) — the durable store for scraped jobs and their tracker status.
- **JSON config files** — `jobs_config.json` (search titles/filters) and `llm_config.json` (local-LLM settings); both gitignored.
- **Local LLM** — `utils/LocalLLM` manages model files and a local llama server.

## Scrape Pipeline (write path)

```
Find Jobs modal → POST /api/scrape/start
      → scraping_service.execute_full_scraping_workflow (orchestrator)
          → task_generator → jobspy_wrapper (concurrent_scraper)
          → data_processor.deduplicate_jobs (in-batch, within/across job sites, by Title+Company)
          → database/operations.get_existing_job_keys (drop jobs already tracked, same
              Title+Company match — before spending any LinkedIn/LLM calls on them)
          → linkedin_scraper.fetch_descriptions_for_jobs (SERIAL — one request at a time,
              with a jittered delay, to avoid the guest endpoint's rate-limiting)
      → database/operations.add_job (save new jobs) → SQLite
      → job_filter (apply config; mark ignore=1 for non-matching jobs)
          → recommend/compensation.extract_compensation_llm (OPTIONAL — when the LLM is enabled
              and runtime.enable_llm_compensation; recovers pay from descriptions, parallel) +
              recommend/service.analyze_jobs (OPTIONAL — gated by runtime.enable_analysis and an
              active profile), run together on every job that survived filtering
Client polls GET /api/scrape/status/<job_id> for progress + a live `events[]` activity feed
```

Each pipeline step calls a progress callback; `scrape_routes` records the messages into an
append-only, timestamped, de-duplicated `events` list on the job record (capped at 200), which
the Find Jobs progress view renders as a live, step-by-step activity feed.

The dedup/database-check/filter steps run *before* the LinkedIn fetch and LLM compensation
steps specifically so those expensive calls only ever touch jobs that are both new and pass
the keyword filter — not the full scraped batch. LinkedIn descriptions are fetched
**serially** (one at a time) to avoid rate-limiting. The analysis stage runs over **only the
keyword-filtered remainder** (non-ignored jobs): embed → rank by semantic+bm25 → LLM fit
verdict on **all** of them by default (optional `top_n_llm` cap: `0` = all, `N>0` = top-N) →
fold the `llm` signal into `rag_score` (renormalized when no verdict). See
`docs/recommendation.md`.

## Read Path (job display)

```
SQLite → database/operations (query) → GET /api/jobs[/<id>]
      → fetch() in client → renderers.js → New Jobs grid / Tracker / detail panel
```

## Status Updates

```
Drag/drop or action in handlers.js
      → PATCH /api/jobs/<id>/status  (tracker status)
      → PATCH /api/jobs/<id>/ignore  (hide)
      → database/operations → SQLite
```

## LLM Flow

```
LLM config UI → /api/config, /api/config/directories → llm_config.json
Model management → /api/models*, /api/models/manage → model files on disk
Server control → /api/server/{start,stop,status} → utils/LocalLLM/server/manager (llama server)
```

## Recommendation Config & LLM Endpoint Flow

```
Options panel (LLM tab)      → /api/options/llm[/test] → config/llm_endpoint_config.json
Options panel (Runtime tab)  → /api/options/runtime    → config/runtime_config.json

All AI features (profile build, skill extraction, recommendation, keyword gen)
  → utils/backend/llm/OpenAIClient.from_config()  →  POST {base_url}/chat/completions
    (the endpoint may be a remote API or the bundled local llama-server)
```

The endpoint config (Options) is **separate** from `llm_config.json` (the bundled
llama-server model manager): Options only describes *which* OpenAI-compatible endpoint
to call, while `utils/LocalLLM` manages *running* a local one.

## Recommendation Analysis Flow

```
Scrape completes (or POST /api/recommend/analyze)
   → recommend.service.analyze_jobs(job_ids)
       → embed missing job descriptions (fastembed, parallel)   [embed-on-retrieve]
       → extract skills (gazetteer, or LLM batch if enabled)
       → ranker.rank_batch (semantic + bm25 + keyword-group + skill → rag_score)
       → save_job_analysis → JobAnalysis table
Read: GET /api/jobs?with_analysis=1  /  GET /api/recommend/report  → match badges + detail breakdown
```

See `docs/recommendation.md`. Stored embeddings are reused on re-analysis; analysis in the
scrape pipeline is gated by `runtime_config.enable_analysis` + an active profile and is
non-fatal (a scrape still succeeds if the embedding model is unavailable).

## State Ownership

- **Server-side / durable:** scraped jobs, tracker status, config files, model files. Owned by the backend; SQLite is the source of truth for jobs.
- **Client-side / ephemeral:** active tab/view, open panels/modals, in-flight drag state, polling timers.
- **Derived:** "new vs. tracked" and column grouping are computed client-side from job status fields.

## Caching / Real-time

- No dedicated cache layer; the client re-fetches on demand.
- Scrape progress is surfaced by **polling** `/api/scrape/status/<job_id>` (no websockets).
