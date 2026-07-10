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

## Profile API (`profile_bp`)

Builds/edits the active recommendation profile (see `docs/profile.md`).

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/profile` | GET | Load the active profile (or an empty skeleton with `exists:false`) |
| `/api/profile` | POST | Upsert the active profile from edited fields (incl. `blocked_companies`, `title_blocklist`, scoped `keyword_groups`); re-applies block rules to the current feed |
| `/api/profile/upload` | POST | Upload a résumé (PDF/.tex/.md), extract text, return an LLM-drafted (or empty) profile — not persisted |
| `/api/profile/build` | POST | Rebuild a draft from stored `resume_text` (requires the LLM) |
| `/api/profile/block-company` | POST | Add a company to the profile blocklist and immediately hide its jobs (body `{company}`) |
| `/api/profile/add-skill` | POST | Add a skill to the profile's `skills` list, de-duped case-insensitively (body `{skill}`); used by the job detail panel's "click a missing skill to add it" affordance |

## Recommend API (`recommend_bp`)

RAG scoring of jobs against the active profile (see `docs/recommendation.md`).

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/recommend/analyze` | POST | Embed + score jobs against the active profile synchronously (body: optional `{job_ids, reanalyze_all}`); persists `JobAnalysis` |
| `/api/recommend/analyze/start` | POST | Start a **background** analysis (same body); returns `{job_id}` to poll — powers the Analyze Matches progress popup |
| `/api/recommend/analyze/status/<job_id>` | GET | Poll a background analysis: `{status, progress, events, results}` (404 if unknown) |
| `/api/recommend/report` | GET | Jobs ranked by `rag_score` (query: `limit`, `include_ignored`) |
| `/api/recommend/keywords` | POST | LLM-generate search terms + AND/OR keyword groups + job type (body: optional `{seed}`; falls back to the active profile) |

`GET /api/jobs?with_analysis=1` attaches each job's analysis under an `analysis` key.

## Documents API (`documents_bp`)

Agentic ingestion of supporting documents (résumé/behavioral/writing-style/reference uploads), template management, per-job application-fit evaluations, and the (dormant) generated-document store — the data + ingestion foundation described in `docs/plans/agentic-documents-system.md` (§8.1–§8.2). Registered in `app.py`.

**Ingestion**

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/documents/ingest` | POST | Multipart `{file, doc_type?}` — runs the in-house ingestion agent (extract → classify → summarize/normalize) and returns a **draft** (`{success, filename, doc_type, target_table, draft, summary, raw_text, llm_used, llm_error}`); nothing is persisted |
| `/api/documents/ingest/save` | POST | `{doc_type, target_table, record, filename?, raw_text?, summary?}` — upserts the approved draft into its target table (`profiles` / `behavioral_profiles` / `writing_style_profiles`) or keeps a summary-only upload for `reference`/`other`; logs an `uploaded_documents` row (`{success, derived_table, derived_id, uploaded_id}`) |
| `/api/documents/uploaded` | GET | List raw-upload log entries (`{documents: [...]}`) |

**Supporting-doc CRUD**

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/behavioral-profile` | GET | Load the active behavioral profile (`{exists, ...}`) |
| `/api/behavioral-profile` | POST | Upsert the active behavioral profile (`{traits, strengths, work_style_paragraph, ...}` → `{success, profile, id}`) |
| `/api/writing-style` | GET | Load the active writing-style profile (`{exists, ...}`) |
| `/api/writing-style` | POST | Upsert the active writing-style profile (`{tone, formality, sentence_length, sample_text, dos, donts, ...}` → `{success, profile, id}`) |
| `/api/templates` | GET | List templates, optionally filtered by kind (query: `kind`) → `{templates: [...]}` |
| `/api/templates` | POST | Create a template (`{kind, name, body, format?, is_default?}` → `{success, template}`) |
| `/api/templates/<id>` | GET / PATCH / DELETE | Fetch / update / delete a single template |

**Job evaluation**

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/job-evaluation/<job_id>` | GET | Load the application-fit evaluation for a job (`{exists, ...}`) |
| `/api/job-evaluation/<job_id>` | POST | Upsert the evaluation (`{verdict, fit_score, emphasize, gaps, risks, talking_points}` → `{success, evaluation}`; 404 if the job doesn't exist) |

**Generated documents**

| Path | Method | Purpose |
| --- | --- | --- |
| `/api/documents` | GET | List generated documents for a job (query: `job_id`) → `{documents: [...]}` — dormant until the cover-letter/résumé generators land |

## UI States (per view)

- **New Jobs grid:** loading (scrape in progress), empty (no jobs / all ignored), populated, error (API failure).
- **Tracker (kanban):** empty columns, populated cards, drag-in-progress, status-update error.
- **Job detail panel:** loading, loaded, link-missing, error.
- **Find Jobs modal:** form, validating, scraping (progress), success, error.
- **LLM config:** server stopped / starting / running / error; model downloading / ready.
