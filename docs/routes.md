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

## UI States (per view)

- **New Jobs grid:** loading (scrape in progress), empty (no jobs / all ignored), populated, error (API failure).
- **Tracker (kanban):** empty columns, populated cards, drag-in-progress, status-update error.
- **Job detail panel:** loading, loaded, link-missing, error.
- **Find Jobs modal:** form, validating, scraping (progress), success, error.
- **LLM config:** server stopped / starting / running / error; model downloading / ready.
