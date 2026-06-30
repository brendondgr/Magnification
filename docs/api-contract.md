# API Contract — Magnification

JSON-over-HTTP contracts for the Flask blueprints. All endpoints return JSON unless noted. Source of truth: `utils/backend/routes/*.py` and the SQLAlchemy models in `utils/backend/database/models.py`.

> This document captures the observable contract at initialization time. When an endpoint's request/response shape changes, update this file and `docs/routes.md` in the same change.

## Conventions

- **Base:** same-origin, no auth.
- **Content type:** `application/json` for request bodies and responses.
- **Errors:** endpoints return an error JSON body with a non-2xx status. The exact error envelope is defined per handler; standardizing it is a follow-up.
- **IDs:** job IDs are integers (`<int:job_id>`); scrape runs use a string `job_id` task identifier.

## Config

- `GET /api/config/load` → current job-search configuration object (titles, filters, locations).
- `POST /api/config/save` — body: the configuration object → persisted to `jobs_config.json`; returns success status.

## Scrape

- `POST /api/scrape/start` — body: scrape parameters derived from config → returns a `job_id` for the async run.
- `GET /api/scrape/status/<job_id>` → run status/progress (e.g., state, counts) for polling.

## Jobs

- `GET /api/jobs` → array of job records; supports query filtering (e.g., new vs. tracked, hidden/non-hidden).
- `GET /api/jobs/<int:job_id>` → a single job record.
- `PATCH /api/jobs/<int:job_id>/ignore` → marks the job hidden/ignored.
- `PATCH /api/jobs/<int:job_id>/status` — body: new tracker/application status → updates the job's status.
- `POST /api/database/clear` → removes all job records.

## LLM (prefix `/api`)

- `GET /api/config` / `POST /api/config` → get / save local-LLM configuration (`llm_config.json`).
- `POST /api/config/directories` → set model directories.
- `GET /api/models` → installed models; `GET /api/models/refresh` → re-scan directories.
- `POST /api/models/manage` → download or delete a model.
- `POST /api/server/start` / `POST /api/server/stop` → control the local llama server.
- `GET /api/server/status` → server running state.

## Shared Schema

Job and related records are defined as SQLAlchemy models in `utils/backend/database/models.py`. See `docs/database.md` for the schema deep-dive.
