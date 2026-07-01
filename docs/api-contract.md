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
- `GET /api/scrape/status/<job_id>` → run status/progress for polling: `{status, progress:{stage,percent,details}, events:[{t,stage,percent,message},...], results, ...}`. `events` is an append-only, timestamped, de-duplicated log of every pipeline step, surfaced as the UI's live activity feed.

## Jobs

- `GET /api/jobs` → array of job records; supports query filtering (e.g., new vs. tracked, hidden/non-hidden).
- `GET /api/jobs/<int:job_id>` → a single job record.
- `PATCH /api/jobs/<int:job_id>/ignore` → marks the job hidden/ignored.
- `PATCH /api/jobs/<int:job_id>/status` — body: new tracker/application status → updates the job's status.
- `POST /api/database/clear` — body: `{"scope": "full" | "jobs"}` (defaults to
  `"full"`). `"full"` drops and recreates every table (jobs + profiles +
  analyses); `"jobs"` deletes jobs, application statuses, and analyses while
  **keeping** profiles. Unknown scope → `400`. Response: `{"success": true, "scope": <scope>}`.

## LLM (prefix `/api`)

- `GET /api/config` / `POST /api/config` → get / save local-LLM configuration (`llm_config.json`).
- `POST /api/config/directories` → set model directories.
- `GET /api/models` → installed models; `GET /api/models/refresh` → re-scan directories.
- `POST /api/models/manage` → download or delete a model.
- `POST /api/server/start` / `POST /api/server/stop` → control the local llama server.
- `GET /api/server/status` → server running state.

## Options (recommendation system) (`options_bp`)

- `GET /api/options/llm` → the OpenAI-compatible endpoint config: `{enabled, base_url, api_key, model, temperature, max_tokens, timeout}`. `base_url` is expected to include the `/v1` prefix.
- `POST /api/options/llm` — body: any subset of those keys (unknown keys ignored) → merged + persisted to `config/llm_endpoint_config.json`; returns `{success, config}`.
- `POST /api/options/llm/test` — body: optional config overrides → builds a client (ignoring `enabled`), sends a tiny chat probe, returns `{ok: true, model, sample}` (200) or `{ok: false, error}` (502/400).
- `GET /api/options/runtime` → runtime knobs: `{enable_analysis, enable_llm_rerank, enable_llm_skills, enable_llm_compensation, embed_workers, embed_batch_size, linkedin_workers, linkedin_delay, llm_workers, top_n_llm, weights:{semantic,bm25,keyword,skill,llm}}`. `enable_llm_rerank` (default true) adds an LLM fit verdict to **all** analyzed jobs and folds it into `rag_score` via the `llm` weight; `top_n_llm` (default `0`) is an optional cap — `0` means all jobs, `N>0` limits the verdict to the top-N candidates by `semantic+bm25`; `enable_llm_compensation` (default true) lets the scrape pipeline LLM-extract pay from a job's description when the board lists none. **`weights` must sum to 1.0** (the UI enforces it); the `llm` share is renormalized out for jobs with no verdict. `linkedin_workers` is retained for reference but LinkedIn description fetch is forced serial.
- `POST /api/options/runtime` — body: any subset (weights deep-merged) → persisted to `config/runtime_config.json`; returns `{success, config}`.

## Profile (recommendation system) (`profile_bp`)

- `GET /api/profile` → active profile `{exists, interests_paragraph, skills, job_titles, keyword_groups, blocked_companies, title_blocklist, llm_instructions, resume_text, source_filename, ...}` (or `{exists:false}` + empty fields). Each `keyword_groups` entry is `{label, terms:[...], scopes:[...]}` where `scopes` ⊆ `{"title","description"}` (defaults to both).
- `POST /api/profile` — body: any of `interests_paragraph, skills, job_titles, keyword_groups, blocked_companies, title_blocklist, llm_instructions, resume_text, source_filename, name` → `upsert_active_profile`, then re-applies the profile block rules to the existing feed (one-directional hide). Returns `{success, profile, hidden}` (`hidden` = jobs newly ignored).
- `POST /api/profile/block-company` — body: `{company}` → adds the company to `blocked_companies` (case-insensitive de-dupe, creates a default profile if none) and hides its jobs. Returns `{success, blocked_companies:[...], hidden}`. Empty company → `400`.
- `POST /api/profile/add-skill` — body: `{skill}` → appends the skill to `skills` (case-insensitive de-dupe, creates a default profile if none). Returns `{success, skills:[...]}`. Empty skill → `400`.
- `POST /api/profile/upload` — multipart `file` (.pdf/.tex/.md/.markdown/.txt) → `{success, source_filename, resume_text, profile, llm_used, llm_error}`. Draft is **not** persisted.
- `POST /api/profile/build` — body: `{resume_text, instructions?}` → `{success, profile, llm_used}` (requires the LLM endpoint enabled). `instructions` steers the build; when omitted it falls back to the saved profile's `llm_instructions`.

## Recommend (recommendation system) (`recommend_bp`)

- `POST /api/recommend/analyze` — body: optional `{job_ids:[int,...]}` (omit to analyze all) → `{success, analyzed, profile_id, top:[...]}`. 400 if no active profile.
- `GET /api/recommend/report` — query `limit` (default 50), `include_ignored` → `{success, count, jobs:[{...job, analysis:{...}}]}` sorted by `rag_score` desc.
- `POST /api/recommend/keywords` — body: optional `{seed}` (else uses the active profile) → `{success, search_terms:[...], keyword_groups:[{label,terms}], job_type}`. 400 if the LLM endpoint is disabled or there is no seed/profile.
- `GET /api/jobs?with_analysis=1` → each job dict gains `analysis: {rag_score, semantic_score, bm25_score, keyword_score, skill_score, keyword_group_hits, skill_match:{matched,missing}, extracted_skills, llm_score, llm_rationale, ...}` (or `null`).

## Shared Schema

Job and related records are defined as SQLAlchemy models in `utils/backend/database/models.py`. See `docs/database.md` for the schema deep-dive.
