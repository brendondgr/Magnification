# Find Jobs

How the "Find Jobs" modal is configured, prefilled, and run. The modal lives in the single served
page `utils/frontend/templates/index.html`; the backend side is
`utils/backend/routes/config_routes.py`, `utils/backend/routes/scrape_routes.py`, and
`utils/backend/scrapers/scraping_service.py`.

## Config storage

Find Jobs settings persist to `config/jobs_config.json`, loaded/saved via `GET /api/config/load`
and `POST /api/config/save` (`config_routes.py`). The file is **gitignored** (see
`.gitignore`) — it is a per-install search configuration, not checked-in data. If the file is
missing, `load_jobs_config()` returns an in-memory default (empty terms/titles, all five sites,
`hours_old: 24`, `results_wanted: 20`, `max_iterations: 1`).

## Config schema

| Key | Type | Meaning |
|---|---|---|
| `search_terms` | `string[]` | Job titles/queries searched, one scraping task per term (see `task_generator.py`). Falls back to `job_titles` for backward compatibility if empty. |
| `job_titles` | `string[]` | Legacy/back-compat alias for search terms; also reused as the **title filter** allow-list by `job_filter.py` when non-empty (flat list = OR, list-of-lists = AND-of-OR groups). |
| `description_keywords` | `string[]` or `string[][]` | Keyword filter applied to job descriptions after scraping. Flat list = OR; list of lists = AND across groups, OR within each group (`job_filter.apply_keyword_filter`). The modal always saves the list-of-lists form ("AND groups" UI). |
| `sites` | `string[]` | Job boards to query. Valid values: `indeed`, `linkedin`, `glassdoor`, `zip_recruiter`, `google` (`SUPPORTED_SITES`). |
| `countries` | `string[]` | Zero or more countries (e.g. `"USA"`). One scrape task runs per title × country via jobspy's `country_indeed`; empty defaults to a single default country. |
| `location` | `string` | Optional free-text city/remote filter passed to jobspy alongside the country selector. |
| `job_type` | `string \| null` | One of `fulltime` / `internship` / `contract` / `parttime`, passed straight to jobspy's `job_type` filter; `null`/absent = no filter. |
| `hours_old` | `int` | Max posting age in hours. UI maps a 6-step age slider to `[24, 72, 168, 336, 504, 720]`. |
| `results_wanted` | `int` | Results requested per term per site, per pass. |
| `max_iterations` | `int` | Number of scrape passes (clamped to 1–5 server-side). Each pass pages deeper by advancing jobspy's `offset` by `results_wanted`, surfacing additional unique jobs; cross-pass duplicates are dropped by in-batch + database dedup. |
| `use_llm` | `bool` | Whether the "LLM refinement" toggle is on — enables LLM re-ranking/filtering of matches after the scrape (see `docs/recommendation.md`). |

## Prefill behavior

On open, `openFindAndLoad()` fetches `GET /api/config/load` and `GET /api/profile` in parallel.
The active profile's `job_titles` and `keyword_groups` take precedence over the saved config for
**Title (search terms)** and **Description keyword groups** — so the modal always reflects the
latest built profile rather than a stale saved search — and it re-fetches every time the modal
opens. If the profile has no titles/keyword groups, it falls back to the saved
`search_terms`/`job_titles` and `description_keywords`. `sites`, `countries`, `location`,
`job_type`, `results_wanted`, `max_iterations`, and `use_llm` are always taken from the saved
config (or current UI state / defaults if unset). When prefilled from the profile, the modal
shows a "★ Prefilled from your active profile" hint above the keyword groups.

A **Generate (LLM)** button calls `POST /api/recommend/keywords` (empty body) and, on success,
overwrites the terms, keyword groups, and job type with the model's suggestions derived from the
active profile.

## Running a search

1. **Start Search** saves the current modal state via `POST /api/config/save` (see schema above),
   then calls `POST /api/scrape/start` with `{"use_config": true}`, which returns a `job_id` and
   spawns a background thread running `execute_full_scraping_workflow` (`scraping_service.py`).
2. The client polls `GET /api/scrape/status/<job_id>` on an interval until `status` is
   `completed` or `failed`. See `docs/api-contract.md` for the exact response shape.
3. The progress view shows a percent ring, a stage label (`init` → `scraping` →
   `processing` → `fetching_descriptions` → `saving` → `filtering` →
   `extracting_enrichment`/`analyzing` → `completed`), a status message, three stat tiles, and a
   live **activity feed** built from the run's append-only `events[]` log.

Stat tile meanings (all cumulative across every iteration of the run, monotonic — a later poll
never shows a smaller number):

| Tile | Source field | Meaning |
|---|---|---|
| Jobs Found | `details.jobs_found` / `results.jobs_found` | Raw listings returned by the job boards. |
| Jobs Saved | `details.jobs_saved` / `results.jobs_saved` | New rows actually inserted into the database (after in-batch and database dedup). |
| Not Hidden | `details.jobs_kept` / `results.jobs_kept` | Saved jobs that survived the title/keyword filter (i.e. not marked `ignore=1`). |

On completion the client also reads `results.jobs_unique` (post-dedup, pre-storage count) to
show alongside the found/saved/kept summary, and reloads the job feed. On failure, the modal
shows `data.error` and lets the user retry.

## Not implemented

There is no cancel/stop endpoint — once a scrape starts via `POST /api/scrape/start` it runs to
completion or failure server-side; closing the modal only stops polling, it does not abort the
background thread. There is no `cancel_scraping(job_id)` route.

## See also

- `docs/job_scraping.md` — scraping pipeline internals (jobspy wrapper, dedup, LinkedIn
  description fetch, filtering, enrichment/analysis).
- `docs/api-contract.md` — full request/response contract for `/api/config/*` and
  `/api/scrape/*`.
- `docs/component-map.md` — where these routes and the modal fit in the overall app.
