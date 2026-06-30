# Route Map — Magnification

Page routes and JSON API endpoints. Endpoint contracts are in `docs/api-contract.md`. Source: `app.py` and `utils/backend/routes/*.py`.

## Page / Shell Routes (`app.py`)

| Path | Method | Purpose | Returns |
| --- | --- | --- | --- |
| `/` | GET | Serves the SPA shell | `index.html` |
| `/parts/<filename>` | GET | Reusable UI partials | HTML from `templates/parts/` |
| `/primary/<filename>` | GET | Primary view sections | HTML from `templates/primary/` |
| `/static/<path>` | GET | Static CSS/JS/images | Flask static handler |

The client loads partials (`header`, `mobile-nav`, `sidebar`, `new-jobs`, `tracker`, `job-detail-panel`) via `loadPartial()` in `index.html`.

## Config API (`config_bp`)

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/config/load` | GET | Load job-search config (`jobs_config.json`) |
| `/api/config/save` | POST | Save job-search config |

## Scrape API (`scrape_bp`)

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/scrape/start` | POST | Start an async scraping run |
| `/api/scrape/status/<job_id>` | GET | Poll status/progress of a scraping run |

## Jobs API (`job_bp`)

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/jobs` | GET | List jobs (supports filtering) |
| `/api/jobs/<int:job_id>` | GET | Get a single job |
| `/api/jobs/<int:job_id>/ignore` | PATCH | Hide/ignore a job |
| `/api/jobs/<int:job_id>/status` | PATCH | Update application/tracker status |
| `/api/database/clear` | POST | Clear all jobs from the database |

## LLM API (`llm_bp`, prefix `/api`)

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/config` | GET / POST | Get / save LLM config (`llm_config.json`) |
| `/api/config/directories` | POST | Set model directories |
| `/api/models` | GET | List installed models |
| `/api/models/refresh` | GET | Re-scan model directories |
| `/api/models/manage` | POST | Download / delete models |
| `/api/server/start` | POST | Start the local LLM (llama) server |
| `/api/server/stop` | POST | Stop the local LLM server |
| `/api/server/status` | GET | Local LLM server status |

> Note: `llm_bp` manages the **bundled local llama-server** (model downloads, GPU detection, start/stop). The recommendation features instead talk to a configurable **OpenAI-compatible endpoint** via the Options API below — which may point at the local server or any remote API.

## Options API (`options_bp`)

Configures the recommendation system. Config is stored in gitignored JSON (`config/llm_endpoint_config.json`, `config/runtime_config.json`).

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/options/llm` | GET / POST | Get / save the OpenAI-compatible endpoint config (base_url, api_key, model, temperature, max_tokens, timeout, enabled) |
| `/api/options/llm/test` | POST | Probe the endpoint (uses posted config if given, else saved); returns `{ok, ...}` |
| `/api/options/runtime` | GET / POST | Get / save runtime knobs (parallel worker counts, analysis toggles, score weights, top_n_llm) |

## UI States (per view)

- **New Jobs grid:** loading (scrape in progress), empty (no jobs / all ignored), populated, error (API failure).
- **Tracker (kanban):** empty columns, populated cards, drag-in-progress, status-update error.
- **Job detail panel:** loading, loaded, link-missing, error.
- **Find Jobs modal:** form, validating, scraping (progress), success, error.
- **LLM config:** server stopped / starting / running / error; model downloading / ready.
