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
  - `progress.details` carries the counters behind the Find Jobs stat tiles, all **cumulative
    across every search iteration** and non-decreasing for the life of a run: `jobs_found` (raw
    listings the boards returned), `jobs_saved` (rows inserted — updated as each iteration's
    storage step completes, not only at the end), `jobs_kept` (survived filtering), and, on the
    terminal event, `jobs_unique` (after in-batch dedup). A fresh scraper is constructed per
    iteration, so these are accumulated by `execute_full_scraping_workflow`, never read off a
    single pass.
  - `results` mirrors the same run totals at top level — `jobs_found`, `jobs_unique`,
    `jobs_saved`, `jobs_kept`, `jobs_added` — alongside `steps`. Inside `steps`,
    `scraping.raw_jobs_count`, `processing.processed_count`, `db_dedup.removed`, and
    `storage.stored_count`/`job_ids` are run totals; each keeps the pass-local figure as
    `last_pass_count` (`db_dedup.last_pass_removed`). Multi-iteration runs also get
    `steps.iterations = {count, total_raw, total_unique, total_new_stored, passes:[{iteration,
    offset, raw, stored}]}`.

## Jobs

- `GET /api/jobs` → array of job records; supports query filtering (e.g., new vs. tracked, hidden/non-hidden). Each record includes a `saved` flag (0/1); an `industry` string (one of the fixed taxonomy, or `null` until classified) plus its `industry_checked` flag; and the durable, write-once pipeline dates `date_found` (= `created_at`), `date_first_applied`, `date_first_interview`, `date_first_offer`, `date_first_rejected`, `date_first_ghosted` (YYYY-MM-DD, or `null` until the stage is reached).
- `GET /api/jobs/counts` → `{total, feed, hidden}` — row counts for the jobs table. `hidden` is how many ignored jobs the default `/api/jobs` payload leaves out, so the client can label "Show Ignored" without loading those rows.
- `GET /api/jobs/filter/options` → facets for the New Jobs **Filter** popup, measured over the jobs a pass can act on (visible and not saved): `{success, total, industries:[{label, count}, ...], unclassified, scored, unscored, oldest, newest}`. `industries` holds only real labels, sorted by count descending; jobs with no label yet are counted in `unclassified` (the popup offers them as the `"Unclassified"` selection). `scored` counts jobs that have a `rag_score` to compare a threshold against. `oldest`/`newest` are the found-date bounds (`YYYY-MM-DD`, or `null` on an empty feed).
- `POST /api/jobs/filter` — bulk hide. Two modes, one contract. In both, saved jobs are exempt, already-hidden jobs are skipped, and the pass is one-directional (jobs are hidden, never un-hidden — "Show Ignored" + the manual un-hide is the reverse). Body, all optional:
  - `job_ids: [int, ...]` — scope the pass to specific jobs.
  - `rules: {...}` — the **ad-hoc** criteria behind the Filter popup. Criteria are **OR**-ed: a job is hidden if it matches any enabled one. Keys: `keywords` (a *kill* list — hide a job containing any term; note this is the opposite direction from the `jobs_config` keep-list), `keyword_scopes` ⊆ `{"title","description"}` (defaults to both), `found_before` (`YYYY-MM-DD`; compares `date_found`/`created_at` — no board posting date is stored), `min_match` (0–100; the displayed `round(rag_score × 100)`), `hide_unscored` (also hide jobs with no analysis — off by default, since they have no percentage), and `industries` (labels from `/api/jobs/filter/options`, plus the sentinel `"Unclassified"`).
  - `dry_run: bool` — with `rules`, count what would be hidden without writing anything.

  Omitting `rules` re-applies the **saved** rule sets — the `jobs_config.json` `job_titles` / `description_keywords` filter *and* the active profile's `blocked_companies`, `title_blocklist`, and `keyword_groups` — exactly as before, returning `{"success": true, "checked": <n>, "hidden": <n>}`. The rules mode returns `{"success": true, "checked", "matched", "hidden", "job_ids": [...], "breakdown": {"keywords", "date", "match", "industry"}, "dry_run"}`; `hidden` is `0` on a dry run and a job can appear in several `breakdown` buckets. A malformed rules payload (e.g. a bad date) → `400 {"success": false, "error": ...}`.
- `GET /api/jobs/<int:job_id>` → a single job record, plus a `statuses` array of its per-status milestones.
- `PATCH /api/jobs/<int:job_id>/ignore` → marks the job hidden/ignored.
- `PATCH /api/jobs/<int:job_id>/save` — body: `{"saved": 0 | 1}` (defaults to `1`) → pins/unpins the job to the **Saved** lane. Saved jobs are removed from the New Jobs feed and always appear under the Saved tab, independent of the ignore flag and application status. Response: `{"success": true}` (or `404` if the job is missing).
- `PATCH /api/jobs/<int:job_id>/status` — body: `{"status", "checked"?, "date_reached"?}` → updates the job's per-status milestone. Side effect: when a milestone is checked, its **durable write-once** pipeline date is stamped on the `jobs` row (first occurrence only; never cleared when the card is later moved backward).
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

- `GET /api/options/llm` → the OpenAI-compatible endpoint config: `{enabled, base_url, api_key, model, temperature, max_tokens, timeout, thinking_token_budget}`. `base_url` is expected to include the `/v1` prefix. `thinking_token_budget` (default & minimum `1024`) is the number of tokens a reasoning model may spend thinking before it must answer; it is sent top-level on the request and the client raises the effective `max_tokens` by it so the answer still fits (endpoints that reject the parameter degrade gracefully). It is clamped to `≥ 1024` on save. See `docs/plans/thinking-token-budget.md` (supersedes the earlier `disable_thinking`).
- `POST /api/options/llm` — body: any subset of those keys (unknown keys ignored) → merged + persisted to `config/llm_endpoint_config.json`; returns `{success, config}`.
- `POST /api/options/llm/test` — body: optional config overrides → builds a client (ignoring `enabled`), sends a tiny chat probe, returns `{ok: true, model, sample}` (200) or `{ok: false, error}` (502/400).
- `GET /api/options/runtime` → runtime knobs: `{enable_analysis, enable_llm_rerank, enable_llm_skills, enable_llm_compensation, enable_llm_industry, embed_workers, embed_batch_size, linkedin_workers, linkedin_delay, llm_workers, llm_fraction, weights:{semantic,bm25,keyword,skill,llm}}`. `enable_llm_rerank` (default true) adds an LLM fit verdict to **all** analyzed jobs and folds it into `rag_score` via the `llm` weight — this holds for both manual Web-UI searches and the automatic daily bot, which share one workflow. `llm_fraction` (default `1.0`, clamped to `[0,1]`) is the **single LLM coverage dial** (Options → Runtime → "LLM coverage"): `1.0` sends every final job to the LLM, `<1.0` keeps only the top `ceil(fraction × N)` candidates by `semantic+bm25`. `enable_llm_compensation` (default true) LLM-extracts pay **from the description of every job that has one** — the board's own salary field is unreliable, so it is not treated as authoritative. `enable_llm_industry` (default true) classifies each job's industry from its description. Compensation + industry are pulled in a **single combined LLM pass** per job, each field gated by its own toggle, by the one shared `recommend/enrichment.enrich_jobs` used by both the scrape pipeline and "Analyze Matches". Both are toggled in Options → Runtime. **`weights` must sum to 1.0** (the UI enforces it); the `llm` share is renormalized out for jobs with no verdict. `linkedin_workers` is retained for reference but LinkedIn description fetch is forced serial.
- `POST /api/options/runtime` — body: any subset (weights deep-merged) → persisted to `config/runtime_config.json`; returns `{success, config}`.

## Profile (recommendation system) (`profile_bp`)

- `GET /api/profile` → active profile `{exists, interests_paragraph, skills, job_titles, keyword_groups, blocked_companies, title_blocklist, llm_instructions, resume_text, source_filename, ...}` (or `{exists:false}` + empty fields). Each `keyword_groups` entry is `{label, terms:[...], scopes:[...]}` where `scopes` ⊆ `{"title","description"}` (defaults to both).
- `POST /api/profile` — body: any of `interests_paragraph, skills, job_titles, keyword_groups, blocked_companies, title_blocklist, llm_instructions, resume_text, source_filename, name` → `upsert_active_profile`, then re-applies the profile block rules to the existing feed (one-directional hide). Returns `{success, profile, hidden}` (`hidden` = jobs newly ignored).
- `POST /api/profile/block-company` — body: `{company}` → adds the company to `blocked_companies` (case-insensitive de-dupe, creates a default profile if none), removes it from `favorite_companies`, and hides its jobs. Returns `{success, blocked_companies:[...], favorite_companies:[...], hidden}`. Empty company → `400`.
- `POST /api/profile/favorite-company` — body: `{company, favorite?}` → stars (`true`) or un-stars (`false`) the company on `favorite_companies`; omitting `favorite` toggles. Case-insensitive match, first-seen spelling kept, creates a default profile if none. Visual only — hides nothing. Returns `{success, favorite, favorite_companies:[...]}`. Empty company → `400`. `favorite_companies` is not accepted by `POST /api/profile`; this is its only writer.
- `POST /api/profile/add-skill` — body: `{skill}` → appends the skill to `skills` (case-insensitive de-dupe, creates a default profile if none). Returns `{success, skills:[...]}`. Empty skill → `400`.
- `POST /api/profile/upload` — multipart `file` (.pdf/.tex/.md/.markdown/.txt) → `{success, source_filename, resume_text, profile, llm_used, llm_error}`. Draft is **not** persisted.
- `POST /api/profile/build` — body: `{resume_text, instructions?}` → `{success, profile, llm_used}` (requires the LLM endpoint enabled). `instructions` steers the build; when omitted it falls back to the saved profile's `llm_instructions`.

## Recommend (recommendation system) (`recommend_bp`)

- `POST /api/recommend/analyze` — body: optional `{job_ids:[int,...], reanalyze_all:bool}` (omit `job_ids` to analyze all non-ignored jobs, saved included) → `{success, analyzed, llm_analyzed, compensation_extracted, industry_extracted, profile_id, top:[...]}`. 400 if no active profile. This is a **coverage-bounded gap-filler**: it first selects the LLM coverage set over **all** analyzed jobs — the top `ceil(llm_fraction × N)` by `semantic+bm25` (Options → Runtime "Jobs through the LLM"; `1.0` = every job, `0.5` = the top half) — then issues the LLM fit verdict only for jobs in that set that don't already have one (preserving existing verdicts), and recovers missing compensation **and industry** from descriptions in one combined pass; `llm_analyzed`/`compensation_extracted`/`industry_extracted` count what was newly filled. So at 100% every job ends up with a verdict while repeat calls stay cheap. Pass `reanalyze_all:true` to force a fresh LLM verdict on every covered job (e.g. after editing the profile).
- `POST /api/recommend/analyze/start` — same body as `/analyze`; runs the analysis in a background thread and returns `{success, job_id, message}` immediately (400 if no active profile). Powers the Analyze Matches progress popup.
- `GET /api/recommend/analyze/status/<job_id>` — poll a background analysis → the full task record `{status: 'pending'|'running'|'completed'|'failed', progress:{stage, percent, details:{message}}, events:[{t, stage, percent, message}], results:{...analyze summary} | null, start_time, end_time?, error?}`. `404` if the `job_id` is unknown (or aged out after ~1h). Progress `stage`s: `embedding` → `enrichment` (pay + industry) → `skills` → `scoring` → `llm` → `completed`; messages carry job counts.
- `POST /api/recommend/rescore` — no body → `{success, rescored, profile_id, top:[...]}`. 400 if no active profile. A **cheap refresh**: recomputes each analyzed job's sub-scores + `rag_score` from its **stored** artifacts (embedding, `extracted_skills`) against the current profile + `runtime_config.weights`, **preserving** the stored LLM verdict (no re-embedding, no LLM calls, no compensation recovery). Falls back to a reweight-only pass (recompute `rag_score` from the stored sub-scores) when the embedding model is unavailable, so score-weight changes still take effect offline. The frontend calls this automatically after a score-weight change (Options → Runtime save), a skill quick-add, or a Profile save, then reloads the feed so the displayed match percentages update without a full "Analyze Matches".
- `GET /api/recommend/report` — query `limit` (default 50), `include_ignored` → `{success, count, jobs:[{...job, analysis:{...}}]}` sorted by `rag_score` desc.
- `POST /api/recommend/keywords` — body: optional `{seed}` (else uses the active profile) → `{success, search_terms:[...], keyword_groups:[{label,terms}], job_type}`. 400 if the LLM endpoint is disabled or there is no seed/profile.
- `GET /api/jobs?with_analysis=1` → each job dict gains `analysis: {rag_score, semantic_score, bm25_score, keyword_score, skill_score, keyword_group_hits, skill_match:{matched,missing}, extracted_skills, llm_score, llm_rationale, ...}` (or `null`).

## Documents (`documents_bp`)

Per-job application-fit evaluations and the generated-document store. (The former ingestion /
behavioral / writing-style / template routes were retired in favor of the editable Document
Guidance — see `docs/plans/documents-sidebar-simplify.md`.)

- `GET /api/job-evaluation/<int:job_id>` → the `job_evaluations` row for that job (1:1, distinct from `recommend_bp`'s analysis): `{exists, id, job_id, profile_id, verdict, fit_score, emphasize, gaps, risks, talking_points, created_at, updated_at}` (or `{exists:false}` + empty fields).
- `POST /api/job-evaluation/<int:job_id>` — body: `{verdict, fit_score, emphasize, gaps, risks, talking_points}` → upserts by `job_id` (unique). Returns `{success, evaluation}`, or `404` if the job doesn't exist.
- `GET /api/documents` — query `job_id` (required) → `{documents:[...]}`, the `generated_documents` rows (kind `cover_letter|resume`) for that job; `400` without `job_id`.

## Document Guidance (`guidance_bp`)

The single editable house-style document (`config/document_guidance.json`, resolved through the
shared project root) injected into every cover-letter and résumé generation and refine. Default =
the cover-letter Winning Formula + résumé tailoring principles.

- `GET /api/document-guidance` → `{success, guidance, is_default}`.
- `PUT /api/document-guidance` — body: `{guidance}` (string; blank reverts to the default) → `{success, guidance, is_default}`; `400` if `guidance` is not a string.
- `POST /api/document-guidance/reset` → clears the override → `{success, guidance, is_default: true}`.

## Document Generation (`generation_bp`)

Runs the cover-letter and résumé agent graphs as background tasks, using the same async task+poll pattern as `/api/recommend/analyze/start` — plus a resume path for human-in-the-loop checkpoints.

- `POST /api/documents/cover-letter/start` — body: `{job_id, interactive?, instructions?, revise_from?}` (`interactive`, `instructions`, `revise_from` all optional) → starts the cover-letter agent graph in the background. The editable Document Guidance is always injected; `instructions` is folded (high-priority) into the writer/strategist prompts so the re-run follows it; `revise_from` (an existing `generated_documents` id) makes the run update that document in place (bumping `revision`) instead of creating a new row, loading its current content as the prior draft to build on. Returns immediately: `{success, task_id, kind: "cover_letter", job_id}`.
- `POST /api/documents/resume/start` — same request/response shape as above, with `kind: "resume"` (`instructions` folds into the planner/rewriter prompts instead of writer/strategist).
- `GET /api/documents/status/<task_id>` — poll a background generation task → `{status, kind, job_id, progress:{stage, percent, details:{message}}, events:[{t, stage, percent, message}], results, checkpoint}`. `results` is `null` until the task finishes. On completion: cover letter → `{success, document_id, job_id, kind: "cover_letter", content, needs_review, evaluation, critique}`; résumé → `{success, document_id, kind: "resume", content, needs_review, match_before, match_after, lift}`. The returned `content` is now **LaTeX** (a full `\documentclass{article}` document, `format: "latex"`) rather than markdown. For the résumé, `match_before`/`match_after`/`lift` are computed on the plain tailored text before the LaTeX render, so keyword scoring isn't polluted by TeX markup. When the graph pauses at a human-in-the-loop checkpoint, `status` is `"paused"` and `checkpoint` is `{name: "angle" | "plan", payload:{...}}`.
- `POST /api/documents/<task_id>/resume` — body: `{decision: "approve" | "edit" | "reject"}` (`"edit"` also carries `edits`: `{thesis}` for the cover-letter graph or `{plan}` for the résumé graph) → resumes the paused graph from its checkpoint. Returns `{success, task: {...same shape as the status endpoint...}}`.
- `GET /api/documents/<int:doc_id>` → a single `generated_documents` row: `{id, job_id, kind, content, format, status, match_before, match_after, revision, checkpoint_state, created_at, updated_at}`. For generated cover letters and résumés, `content` is **LaTeX** (a full `\documentclass{article}` document) and `format` is `"latex"`.
- `PATCH /api/documents/<int:doc_id>` — body: any subset of `{status, content, format}` → updates the document record. Returns `{success, document: {...updated row...}}`.
- `GET /api/documents/<int:doc_id>/pdf` — compiles the document's stored LaTeX source to a PDF (cached on disk under `data/generated_pdfs/`, keyed by a hash of the source) and streams it as `application/pdf`, served **inline** for the review-pane preview; `?download=1` sets an attachment disposition. Errors: `404` (document not found), `415` (document is not LaTeX — e.g. a legacy markdown row), `422 {success:false, message, log}` (compile failed; `log` is the tail of the TeX log).
- `GET /api/documents/<int:doc_id>/tex` — downloads the raw LaTeX source of a generated document as `application/x-tex` (attachment).

## Shared Schema

Job and related records are defined as SQLAlchemy models in `utils/backend/database/models.py`. See `docs/database.md` for the schema deep-dive.
