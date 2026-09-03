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
          → recommend/enrichment.enrich_jobs (OPTIONAL — when the LLM is enabled and
              runtime.enable_llm_compensation and/or enable_llm_industry; extracts pay +
              industry from descriptions in one combined pass per job, parallel. This is the
              SAME function "Analyze Matches" calls — see below) +
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

Because every iteration builds a **fresh** `JobSpyScraper` (whose own tally restarts at zero)
and rewrites its slice of `results['steps']`, the run counters are accumulated by
`execute_full_scraping_workflow` itself and pushed through the progress callback as
`details.jobs_found` / `jobs_saved` / `jobs_kept`. They are **cumulative across all iterations
and never decrease mid-run**, which is what the Find Jobs progress view's three stat tiles show:

| Tile | Meaning |
| --- | --- |
| **Jobs Found** | every raw listing the boards returned, summed over all iterations |
| **Jobs Saved** | rows actually inserted — bumped as each iteration's storage step completes |
| **Not Hidden** | of those, the ones that survived the keyword filter (filtering runs once) |

The in-batch-unique count sits alongside them as `jobs_unique` (terminal event + `results`) and
is surfaced in the completion summary line when it differs from `Jobs Found`. The client also
clamps each tile monotonically, so an out-of-order poll cannot walk a counter backwards.

The dedup/database-check/filter steps run *before* the LinkedIn fetch and LLM compensation
steps specifically so those expensive calls only ever touch jobs that are both new and pass
the keyword filter — not the full scraped batch. LinkedIn descriptions are fetched
**serially** (one at a time) to avoid rate-limiting. The analysis stage runs over **only the
keyword-filtered remainder** (non-ignored jobs): embed → rank by semantic+bm25 → pick the LLM
coverage set over **all** analyzed jobs — top ceil(`llm_fraction` × N) by semantic+bm25
(default `1.0` = every job; lower it to send only that top share; the slider is the single
coverage control) — then issue the fit verdict for jobs in that set (gap-fill: only those
still missing one) → fold the `llm` signal into `rag_score` (renormalized when no
verdict). This holds for
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
      → PATCH /api/jobs/<id>/status  (tracker status; also stamps a durable write-once pipeline date)
      → PATCH /api/jobs/<id>/ignore  (hide)
      → PATCH /api/jobs/<id>/save    (pin to the Saved lane)
      → database/operations → SQLite
```

The per-status `date_reached` written here is **mutable** (cleared when a card is dragged
backward and a milestone is un-checked). To keep a durable record, `update_application_status`
also stamps a **write-once** `jobs.date_first_*` column the first time each pipeline stage is
reached (found = `created_at`, applied, interview, offer, rejected, ghosted); those are never
cleared or overwritten, and the job detail panel's **Pipeline History** reads them back.

**Saved jobs are never auto-hidden.** A saved job (`saved=1`) is an explicit user keep, so the
three filters that set `ignore=1` without user action — `job_filter.filter_and_mark_jobs` (Step 6
of a scrape), `job_filter.apply_profile_filters` (retroactive apply on Profile Save /
Block Company), and `job_filter.apply_all_filters` (the New Jobs **Filter** button) — skip it.
Only the manual hide button (`PATCH /api/jobs/<id>/ignore`) can hide a saved job. This prevents a
saved job the user un-hid from being silently re-hidden on the next search, profile save, or
daily-search-on-boot.

## On-Demand Filtering (the New Jobs "Filter" popup)

The **Filter** button opens a popup with two ways to cut the feed down. Both hide only.

**Ad-hoc bulk rules** — the answer to "there are 300 active jobs and I can't read them all":

```
Filter popup opens → GET /api/jobs/filter/options
      → operations.get_feed_filter_facets()   (industries + counts, scored/unscored, date bounds)
      → the popup's industry chips, unscored hint, and oldest-found note

every control edit (debounced 250ms) → POST /api/jobs/filter {rules, dry_run:true}
      → bulk_filter.apply_bulk_filters(rules, dry_run=True)
      → {checked, matched, breakdown} → the live "Will hide N of M" line

Hide N jobs → POST /api/jobs/filter {rules}
      → bulk_filter.apply_bulk_filters(rules)
            → for each visible, non-saved job, OR over the enabled criteria:
                  keyword kill-list (title and/or description)
                  found_before   (date_found = created_at; no board posting date is stored)
                  min_match      (round(rag_score × 100); unscored kept unless hide_unscored)
                  industries     ("Unclassified" selects jobs with no label yet)
            → set_job_ignore(id, 1) on a match
      → {checked, matched, hidden, breakdown} → toast + loadJobs()
```

The preview and the commit run the *same* function, so the number promised on the button is the
number that gets hidden.

**Saved rules** — the popup's secondary action, unchanged from the original Filter button:

```
Re-apply saved rules → POST /api/jobs/filter {}
      → job_filter.apply_all_filters()
            → load_filter_config()  (jobs_config.json: job_titles + description_keywords)
            → get_active_profile()  (blocked_companies, title_blocklist, keyword_groups)
            → for each visible, non-saved job: apply_filters(...) AND NOT job_blocked_by_profile(...)
            → set_job_ignore(id, 1) on failure
      → {success, checked, hidden} → toast + loadJobs()
```

This is the only path that re-applies the **`jobs_config` keyword filter** to jobs already in the
database; the scrape applies it only to the ids it just wrote, and Profile Save applies only the
profile block rules. Every path here is one-directional — a job is hidden, never un-hidden, so
loosening a filter still needs a re-scrape (or "Show Ignored" + the manual un-hide).

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
                                    enrichment→skills→scoring→llm→completed, w/ job counts]
       → embed missing job descriptions (fastembed, parallel)   [embed-on-retrieve]
       → extract compensation + industry from descriptions in one combined LLM pass
         (recommend/enrichment.enrich_jobs — the SAME function the scrape workflow calls; the
         gating, candidate selection, and persistence live there and nowhere else)
         [non-ignored jobs]
       → extract skills (reuse stored extracted_skills; only extract jobs missing them)
       → ranker.rank_batch (semantic + bm25 + keyword-group + skill → rag_score)
       → LLM fit verdict: coverage = top ceil(llm_fraction × N) of ALL analyzed jobs by
         semantic+bm25, then gap-fill within it — only jobs missing one
         (reanalyze_all re-scores every covered job)
       → save_job_analysis → JobAnalysis table
Read: GET /api/jobs?with_analysis=1  /  GET /api/recommend/report  → match badges + detail breakdown
```

### Description enrichment (compensation + industry) — one shared pass

Both workflows that touch job descriptions — **Find Jobs** (scrape step 7a) and **Analyze
Matches** — call the same function, `utils/backend/recommend/enrichment.enrich_jobs`. It is the
only place that gates on the toggles + endpoint, selects candidates, issues the combined
extraction call, and persists the result; `compensation.py` underneath it holds the pure
prompt/predicate/parsing layer. The two paths previously re-implemented all four steps around
the shared extractor and drifted; `tests/recommend/test_enrichment.py` asserts they no longer do.

- **Compensation is always taken from the description**, whatever the board reported. Board
  salary fields are unreliable — Indeed hands JobSpy `NaN` amounts, which used to reach the
  card as `"USDnan - USDnan hourly"` — so any job with description text is a candidate. A
  figure found in the description wins; when the description states no pay, the board's value
  is left alone and the card shows **"Not Specified"**.
- **Industry is classified in the same call** (one call fills both fields), into the fixed
  `INDUSTRIES` taxonomy that keys the card's pill color.
- `compensation_checked` is stamped on every attempted job — including the ones whose
  description genuinely states no pay — so each job costs one call, not one per run.
  `industry_checked` is stamped **only when a label came back**, because the model is asked to
  always pick one: an empty response means the call failed, so the job retries next run.
- A forced reanalyze (`reanalyze_all`) re-queries jobs regardless of either flag.

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

## Document Guidance Flow

Both generation graphs are steered by one **editable Document Guidance** document — plain text held
in `config/document_guidance.json` (resolved through the shared project root), with a built-in
default (the cover-letter Winning Formula + résumé tailoring principles). It is edited from the
Profile sidebar's **Guidance** tab and injected into every generation and refine:

```
Profile & Documents sidebar → Guidance tab
   GET  /api/document-guidance          → {guidance, is_default}      (loads into a textarea)
   PUT  /api/document-guidance {guidance} → persists the edit (blank string ⇒ revert to default)
   POST /api/document-guidance/reset    → clears the override (built-in default back in effect)
```

`job_evaluations` (per-job application-fit: verdict, fit_score, emphasize, gaps, risks,
talking_points) is a separate 1:1-per-job table from `JobAnalysis` — conceptually seeded from a
`JobAnalysis` verdict but written independently via `GET/POST /api/job-evaluation/<job_id>`.
`generated_documents` is the store for the produced cover letters/résumés below. (The former
upload-ingestion pipeline and the behavioral/writing/template tables were retired — see
`docs/plans/documents-sidebar-simplify.md`.)

## Document Generation Flow

Cover letters and tailored résumés are produced by two in-house, plain-Python agent graphs
(no LangGraph) under `utils/backend/agents/`. Their "ingestion" is a DB read, not a scrape —
loading the job's existing analysis rather than fetching anything new:

```
utils/backend/agents/context.py load_context(job_id, kind)
   → Job + JobAnalysis (skill_match, keyword hits, llm_rationale, stored embedding)
   → active Profile
   → the editable Document Guidance (document_guidance.get_guidance())
```

**Cover Letter graph** (`utils/backend/agents/cover_letter.py`):

```
research_company → evaluate_fit → strategize
   → [Checkpoint 1: approve angle — only when interactive & low confidence]
   → (write → style → refine_flow → critique + truthfulness) looped up to 2 revisions
   → render (assemble LaTeX) → finalize
```

`evaluate_fit` persists a `job_evaluations` row (the job evaluation system described above),
seeded from `JobAnalysis.skill_match` + `llm_rationale` and refined by the LLM. `strategize` and
`write` are given a `candidate_facts(profile)` block (the profile's stated `interests_paragraph`
plus résumé/skills) so the letter's motivation is grounded in the candidate's own words rather
than invented; the prompts target a **300-400 word** letter, and the revision loop enforces a
minimum length (`COVER_MIN_WORDS`) on the LLM path — a short first draft triggers another pass.
Every letter is written to the user-editable **Document Guidance** (default = the *Winning Formula*:
Opening Hook → two-paragraph, quantified Value Proposition → Why-This-Company → Strong Close, plus
writing rules). It is read from `utils/backend/agents/document_guidance.py` and injected at call time
(via `nodes_shared.guidance_preamble`) into the `strategize`/`write`/`critique` nodes, so it is
referenced on **every** generation and every Application-Mode refine/regenerate, and a user edit
takes effect on the next run. The prompts also forbid echoing the job
posting's wording/jargon and manufacturing motivation from JD keywords (the JD is passed as
*context only*), and the critic penalizes JD-parroting / AI-generic voice **and a letter missing any
part of the formula or with an unquantified value proposition** — so the letter reads like the
candidate, not the posting.

**Flow refinement (`refine_flow`, the forced-fit fix):** after styling, a bounded audit → rewrite
loop hunts down *told-not-shown* fit claims — company flattery / narrated virtue ("…shows a clear
commitment to…"), asserted fit ("I would be a great fit because…"), and spliced keyword-list
transitions — and rewrites each flagged sentence into a **shown** connection grounded in
`candidate_facts` ("I build X and follow Y, which is the problem your team works on"), woven into
the surrounding prose. It re-audits after each rewrite and stops the moment the audit is clean
(cap `MAX_FLOW_PASSES = 2` rewrites, then a final audit records any remaining flags in
`state["flow"]`). The smoothed letter (`smoothed_draft`) is what the critic, truthfulness check,
`final_text`, and the LaTeX render all consume. The same show-don't-tell rule is enforced
first-shot by the writer prompt (hard rule 6), the critic (penalty d), and the default Document
Guidance writing rules. Offline, the stage passes the styled draft through untouched.

The deterministic fallback (used
when no endpoint is configured or every LLM call fails) is plain and honest: it never parrots the
JD, manufactures motivation, or splices third-person hooks into first-person prose. `finalize`
persists `generated_documents(kind='cover_letter')`.

**Résumé fine-tuner graph** (`utils/backend/agents/resume.py`):

```
evaluate_gap → plan_edits
   → [Checkpoint 1: approve plan — only when interactive & large cuts]
   → (rewrite → ats_format → score → truthfulness) looped up to 2 revisions
   → render (assemble LaTeX) → finalize(kind='resume', match_before, match_after)
```

`score` is the differentiator: it treats the tailored résumé as a throwaway profile and
reuses the recommender (`recommend/ranker.py`) against the single target job to produce an
objective `match_before` → `match_after` lift — the loop's stop criterion and headline
metric. Offline-safe: bm25 + keyword + skill sub-scores are pure Python and the ranker
renormalizes over whichever signals are present, so a real lift is measurable even without
the embedding model; semantic scoring folds in when embeddings exist. The LLM fit verdict is
excluded from the lift score. Rewrites are truth-preserving — never fabricate skills the
candidate lacks.

**Render step** (`utils/backend/agents/latex.py`). The graphs produce the substance (the plain
prose / tailored content in `state["final_text"]`); a final deterministic, offline `render` node
wraps it into a compilable single-column `article` document — `build_tex(kind, state)` →
`build_cover_letter_tex` / `build_resume_tex`, with `escape_latex` + `md_to_latex` helpers and
only base packages (geometry, titlesec, enumitem, parskip, hyperref, lmodern), hardened to
compile even on adversarial `& % _ $` / `C++` / `[Your Name]` content. It sets `state["final"]`
to the LaTeX source and `state["format"]="latex"` while keeping `state["final_text"]` as the
plain text; the résumé match-lift is scored on `final_text` (plain), **not** the LaTeX
(`ats_format` stashes `state["resume_slots"]` for the builder). A `render` progress stage
(~94%, "Rendering … as LaTeX") is reported before finalize, and `service._persist` records
`state["format"]`.

**PDF compile + serve** (`utils/backend/pdf_compile.py`). The stored LaTeX is compiled to a PDF
on demand:

```
GET /api/documents/<id>/pdf  → compile_pdf(doc_id, tex) → pdflatex (-interaction=nonstopmode
    -halt-on-error -no-shell-escape, 40s, temp dir) → cache data/generated_pdfs/doc_<id>_<hash>.pdf
    (one file per doc; older revisions pruned) → stream application/pdf
    (?download=1 attaches; 404 unknown doc, 415 non-LaTeX, 422 LatexCompileError(message, log))
GET /api/documents/<id>/tex  → raw LaTeX source
```

**Execution/runtime** (`utils/backend/agents/service.py`): each graph runs in a daemon thread
via an in-memory `generation_tasks` store, emitting staged progress events in the
`{status, progress: {stage, percent, details}, events}` shape the frontend polls — the same
pattern as the recommend analyze background task. Semi-auto checkpoints pause the worker on a
`threading.Event` until the `/resume` route delivers a decision; the paused state is also
snapshotted to `generated_documents.checkpoint_state`. Every node degrades to a deterministic
fallback when no LLM endpoint is configured.

**Application Mode** is the interactive flow that drives these graphs from an **Apply** button
on job cards / the job detail (distinct from the quick-mark **Applied** button). It opens a
frontend-only modal — no new DB table; the session itself is ephemeral, only the documents it
produces persist in `generated_documents`:

```
Intake (choose résumé and/or cover letter + optional free-text guidance)
   → Workspace (generation + review unified into one two-column stage; document tabs switch
       Tailored Résumé ∣ Cover Letter — the selected graphs still run as background tasks via the
       same generation_tasks/polling machinery, polled in parallel):
         LEFT  "Process"  = a live step-by-step agent feed rendered from the task events[] (prior
             steps + revision loops), the résumé match-lift, refine chips + textarea (Regenerate),
             and Edit LaTeX / Download PDF / Approve actions
         RIGHT "Preview"  = the compiled PDF (GET /api/documents/<id>/pdf) in an <iframe>,
             re-fetched/recompiled after each generation, refine, or edit
```

From the workspace, **Refine** is the key loop: the user gives feedback (typed, or a quick chip) and
Regenerate re-runs that document's graph with the feedback as high-priority `instructions` plus
the current draft as `prior_content`, via the start endpoint's `revise_from` — this updates the
same `generated_documents` row in place and bumps its `revision` rather than creating a new row.
The user iterates until they approve; manual **Edit LaTeX** edits instead persist immediately via
`PATCH /api/documents/<id>` (the PDF preview recompiles from the edited source). Approving is
followed by Mark as Applied, which advances the
Tracker through the existing status flow (see Status Updates above).

This is design §4 minus the deferred browser-automation submission adapter (§4.3) and the
still-unbuilt `application_sessions` table.

## State Ownership

- **Server-side / durable:** scraped jobs, tracker status, config files, model files. Owned by the backend; SQLite is the source of truth for jobs.
- **Client-side / ephemeral:** active tab/view, open panels/modals, in-flight drag state, polling timers.
- **Derived:** "new vs. tracked" and column grouping are computed client-side from job status fields.

## Caching / Real-time

- No dedicated cache layer; the client re-fetches on demand.
- Scrape progress is surfaced by **polling** `/api/scrape/status/<job_id>` (no websockets).
