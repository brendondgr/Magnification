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

The scrape+store block (scrape → dedup → db-dedup → LinkedIn → save) runs once per
**iteration** (`max_iterations`, 1–5 from the Find Jobs config), each pass advancing a jobspy
page `offset` by `results_wanted` to surface additional unique jobs; the database dedup drops
anything an earlier pass saved. The filter + analysis steps run once over the accumulated new
jobs.

The dedup/database-check/filter steps run *before* the LinkedIn fetch and LLM compensation
steps specifically so those expensive calls only ever touch jobs that are both new and pass
the keyword filter — not the full scraped batch. LinkedIn descriptions are fetched
**serially** (one at a time) to avoid rate-limiting. The analysis stage runs over **only the
keyword-filtered remainder** (non-ignored jobs): embed → rank by semantic+bm25 → LLM fit
verdict on **all** of them by default (`llm_fraction` = `1.0`; lower it to send only the top
share by semantic+bm25, and the optional `top_n_llm` cap composes on top: `0` = all, `N>0` =
top-N) → fold the `llm` signal into `rag_score` (renormalized when no verdict). This holds for
**both** manual Web-UI searches (`/api/scrape/start`) and the automatic daily bot
(`utils/backend/scheduler`) — both run through the same `execute_full_scraping_workflow`. See
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

The "Analyze Matches" button uses the **background** variant so the UI can show a live progress
popup: `POST /api/recommend/analyze/start` spawns a thread (in-memory `analyze_tasks` store,
mirroring the scrape task store) and returns a `job_id`; the client polls
`GET /api/recommend/analyze/status/<job_id>` once per second for `{progress, events, results}`
and renders a percent ring + count-rich activity feed. The synchronous `POST /api/recommend/analyze`
remains for programmatic use. Both call the same service:

```
Scrape completes (or POST /api/recommend/analyze[/start] — "Analyze Matches")
   → recommend.service.analyze_jobs(job_ids, llm_only_missing=not reanalyze_all,
                                    progress_callback=…)   [staged progress: embedding→
                                    compensation→skills→scoring→llm→completed, w/ job counts]
       → embed missing job descriptions (fastembed, parallel)   [embed-on-retrieve]
       → recover missing compensation from descriptions (LLM)   [gap-fill, non-ignored jobs]
       → extract skills (gazetteer, or LLM batch if enabled)
       → ranker.rank_batch (semantic + bm25 + keyword-group + skill → rag_score)
       → LLM fit verdict only for jobs missing one (gap-fill; reanalyze_all re-scores all)
       → save_job_analysis → JobAnalysis table
Read: GET /api/jobs?with_analysis=1  /  GET /api/recommend/report  → match badges + detail breakdown
```

**Cheap rescore (auto-refresh of match %).** When only the score weights or the profile's
skills/keywords change, a full re-analyze is overkill. `POST /api/recommend/rescore` →
`service.rescore_jobs` recomputes each analyzed job's sub-scores + `rag_score` from its
**stored** embedding + `extracted_skills` against the current profile + weights, **preserving**
the stored LLM verdict — no job re-embedding, no LLM calls, no compensation recovery (reweight-
only fallback when the embedder is unavailable). The frontend fires it automatically after a
score-weight save (Options → Runtime), a skill quick-add, or a Profile save, then reloads the
feed so the displayed match percentages update on the page. "Analyze Matches" already reloads
the feed after a full analyze.

See `docs/recommendation.md`. Stored embeddings are reused on re-analysis; analysis in the
scrape pipeline is gated by `runtime_config.enable_analysis` + an active profile and is
non-fatal (a scrape still succeeds if the embedding model is unavailable).

## Document Ingestion Flow

Uploading a résumé/behavioral/writing-style file drafts a structured record via an in-house
agent (plain Python, no LangGraph) before anything is saved — the user reviews/edits the draft,
then explicitly saves it:

```
Upload zone (Profile & Documents sidebar) → POST /api/documents/ingest  {file, doc_type?}
   → agents.ingestion.ingest_document(filename, data, doc_type, client)
       → extract_resume_text (recommend.profile_builder)          [text extraction]
       → classify doc_type (resume|behavioral|writing|reference|other) when not given
       → summarize/normalize into a target-table-shaped record
           via build_profile_from_text + OpenAIClient                [OPTIONAL — LLM]
   → DRAFT returned to the client — NOT persisted
       {success, filename, doc_type, target_table, draft, summary, raw_text,
        llm_used, llm_error}
(no LLM endpoint configured → degrades to an empty, still-editable draft, llm_used=False;
 malformed uploads never 500)

User edits the drafted fields in the sidebar (strengths tags + traits JSON + work-style
paragraph, or tone/formality/sentence_length + sample_text + dos/donts tags), then Save:

POST /api/documents/ingest/save  {doc_type, target_table, record, filename?, raw_text?, summary?}
   → documents_ops upsert of `record` into its target table
       (profiles | behavioral_profiles | writing_style_profiles — single-active row upsert;
        reference/other kept summary-only, no target-table row)
   → documents_ops logs an uploaded_documents row (raw_text, summary, status=saved,
       derived_table + derived_id pointing at the row just upserted)
   → {success, derived_table, derived_id, uploaded_id}

Read: GET /api/documents/uploaded → uploaded_documents log (traces each file to the record
      it produced) — rendered as the "Recent uploads" list.
```

`job_evaluations` (per-job application-fit: verdict, fit_score, emphasize, gaps, risks,
talking_points) is a separate 1:1-per-job table from `JobAnalysis` — it is conceptually seeded
from a `JobAnalysis` verdict but written independently via `GET/POST /api/job-evaluation/<job_id>`;
it is not produced by the ingestion agent above. `document_templates` (cover_letter/resume/
job_evaluation, default-per-kind) and `generated_documents` are unrelated to ingestion; they are
the substrate for the cover-letter/résumé generation graphs below.

## Document Generation Flow

Cover letters and tailored résumés are produced by two in-house, plain-Python agent graphs
(no LangGraph) under `utils/backend/agents/`. Their "ingestion" is a DB read, not a scrape —
loading the job's existing analysis rather than fetching anything new:

```
utils/backend/agents/context.py load_context(job_id, kind, template_id)
   → Job + JobAnalysis (skill_match, keyword hits, llm_rationale, stored embedding)
   → active Profile + active BehavioralProfile + active WritingStyleProfile
   → chosen DocumentTemplate
```

**Cover Letter graph** (`utils/backend/agents/cover_letter.py`):

```
research_company → evaluate_fit → strategize
   → [Checkpoint 1: approve angle — only when interactive & low confidence]
   → (write → style → critique + truthfulness) looped up to 2 revisions
   → finalize
```

`evaluate_fit` persists a `job_evaluations` row (the job evaluation system described above),
seeded from `JobAnalysis.skill_match` + `llm_rationale` and refined by the LLM. `finalize`
persists `generated_documents(kind='cover_letter')`.

**Résumé fine-tuner graph** (`utils/backend/agents/resume.py`):

```
evaluate_gap → plan_edits
   → [Checkpoint 1: approve plan — only when interactive & large cuts]
   → (rewrite → ats_format → score → truthfulness) looped up to 2 revisions
   → finalize(kind='resume', match_before, match_after)
```

`score` is the differentiator: it treats the tailored résumé as a throwaway profile and
reuses the recommender (`recommend/ranker.py`) against the single target job to produce an
objective `match_before` → `match_after` lift — the loop's stop criterion and headline
metric. Offline-safe: bm25 + keyword + skill sub-scores are pure Python and the ranker
renormalizes over whichever signals are present, so a real lift is measurable even without
the embedding model; semantic scoring folds in when embeddings exist. The LLM fit verdict is
excluded from the lift score. Rewrites are truth-preserving — never fabricate skills the
candidate lacks.

**Execution/runtime** (`utils/backend/agents/service.py`): each graph runs in a daemon thread
via an in-memory `generation_tasks` store, emitting staged progress events in the
`{status, progress: {stage, percent, details}, events}` shape the frontend polls — the same
pattern as the recommend analyze background task. Semi-auto checkpoints pause the worker on a
`threading.Event` until the `/resume` route delivers a decision; the paused state is also
snapshotted to `generated_documents.checkpoint_state`. Every node degrades to a deterministic
fallback when no LLM endpoint is configured.

Application Mode (the interactive Apply-button flow meant to drive these graphs from the job
detail panel) is designed but deferred — not built.

## State Ownership

- **Server-side / durable:** scraped jobs, tracker status, config files, model files. Owned by the backend; SQLite is the source of truth for jobs.
- **Client-side / ephemeral:** active tab/view, open panels/modals, in-flight drag state, polling timers.
- **Derived:** "new vs. tracked" and column grouping are computed client-side from job status fields.

## Caching / Real-time

- No dedicated cache layer; the client re-fetches on demand.
- Scrape progress is surfaced by **polling** `/api/scrape/status/<job_id>` (no websockets).
