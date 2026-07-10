# Component Map — Magnification

Ownership of the frontend. Source: `utils/frontend/`.

> **Current frontend = a single design-tool export.** The "Frontend Redesign" replaced the
> old Jinja-partials + vanilla-JS frontend with one `index.html` driven by a vendored
> `dc-runtime.js` (a small React runtime). There is no build step and no `parts/`/`primary/`
> partials or per-feature JS modules anymore.

## Files (`utils/frontend/`)

| File | Role |
| --- | --- |
| `templates/index.html` | The whole app: an `<x-dc>` template (header, sidebar, New Jobs grid, Tracker kanban, job detail panel, Profile panel, Options panel, Find Jobs modal) + a `<script type="text/x-dc">` block holding `class Component extends DCLogic` (all state, methods, and `renderVals()`). |
| `static/js/dc-runtime.js` | Vendored runtime: parses `<x-dc>` + the component script, loads React/ReactDOM/Babel from unpkg, and renders. Reads the component from the inline script's `textContent` (no external-src support). |

> **File-size exception:** `index.html` exceeds the repo's 800-line guideline (~1240 lines).
> It is a generated single-file design export and the runtime requires the component class
> inline, so it cannot be split without modifying the vendored runtime. Accepted and tracked.

## Component model (dc-runtime)

- **State** lives in `this.state`; mutate via `this.setState(...)`.
- **`renderVals()`** returns the object the template interpolates against.
- Template syntax: `{{ value }}` interpolation, `<sc-if value="{{ x }}">`, `<sc-for list="{{ y }}" as="item">`, and `on*` handlers (`onclick`, `oninput`, `onchange`, `onkeydown`).

### Feature areas inside the component

| Area | State keys | Key methods |
| --- | --- | --- |
| Jobs / Tracker / Saved | `jobs, tab, selectedId, search, page, dragOverCol` | `loadJobs`, `mapDbJob`, `toggleIgnore`, `toggleSave`, `blockCompany`, `addSkillToProfile`, `markApplied`, `moveTo`, `toggleStatus` |
| **Job Detail — Documents** | `docGen{active,kind,taskId,percent,stage,message}, docsByJob{jobId->[docs]}, docView{open,title,content,id}` | `loadJobDocuments`, `generateDoc`, `pollGen`, `viewDoc`, `approveDoc`, `downloadDoc`, `closeDocView` |
| Find Jobs | `findOpen, findView, terms, sites, groups, location, ageIndex, maxResults, useLLM` | `openFind`, `startScrape`, `pollScrape`, `configToSave` |
| Analyze Matches popup | `analyzing, analyzeOpen, aPercent, aStage, aStatusMsg, aEvents, aDone, aTotal, aLLM, aComp` | `analyzeJobs` (POST `/analyze/start`), `pollAnalyze` (poll `/analyze/status/<id>`), `closeAnalyze` |
| **Profile & Documents** | `profileOpen, docsTab, profile{llm_instructions,interests_paragraph,skills,job_titles,keyword_groups(+scopes),blocked_companies,title_blocklist,resume_text,...}, pf*Draft, pfBusy, pfSkillsExpanded, beh{...}, wri{...}, behTraitsText, templates, tplSelId, uploadedDocs` | `openProfile` (now also calls `loadDocuments`), `loadProfile`, `saveProfile`, `blockCompany`, `addSkillToProfile`, `onResumeFile`, `rebuildProfile` (unions `skills` + `blocked_companies`), `pfSet`; docs: `loadDocuments`, `loadTemplates`, `loadUploadedDocs`, `behSet`/`wriSet`, `onBehFile`/`onWriFile`, `ingestDoc`, `saveBehavioral`, `saveWriting`, `tplSet`/`addTemplate`/`saveTemplate`/`deleteTemplate` |
| **Options** | `optionsOpen, optionsTab, llm{...}, runtime{...}, llmTest` | `openOptions`, `loadOptions`, `saveLlmOptions`, `testLlmOptions`, `saveRuntimeOptions`, `llmSet`/`rtSet`/`rtWeightSet` |

Main-view tabs: **New Jobs · Saved · Tracker** (desktop nav + mobile bottom nav). The **Saved**
tab is a grid (mirroring the New Jobs card) of every job with `saved=1`, shown regardless of
ignore/applied state; saved jobs are excluded from the New Jobs feed. A **Save** button sits to
the right of the Hide (Ignore) button on each card and in the job detail panel (`toggleSave` →
`PATCH /api/jobs/<id>/save`).

Header nav order: **New Jobs · Tracker · Profile · Find Jobs · Options** (Profile left of Find
Jobs, Options right). Profile + Options are right-side slide-over panels mirroring the job
detail panel; Find Jobs is a centered modal.

### Job detail — Documents section

The job-detail slide-over (`selectedJob`) has a **Documents** section below the Job Description:
**Cover Letter** and **Tailor Résumé** buttons call `generateDoc(kind)` (`POST
/api/documents/cover-letter/start` or `/resume/start`), tracked in `docGen` and polled by
`pollGen` (`GET /api/documents/status/<task_id>` every 700ms, reusing the progress-bar/activity
idiom from Find Jobs/Analyze). While active, an inline progress card shows the node stage,
percent bar, and live message; `formatStage()` gained labels for the generation stages
(`research, evaluate, strategize, write, style, critique, truthfulness, finalize, evaluate_gap,
plan_edits, rewrite, ats_format, score`). Below it, `docsByJob[jobId]` (loaded via
`loadJobDocuments`, called when a job is opened) lists each generated document with its kind, a
Draft/Approved status chip, a match-lift badge for résumés (e.g. "42% → 61% match", colored via
`this.matchColorFor`), and **View**/**Approve** buttons (`viewDoc` → `GET /api/documents/<id>`;
`approveDoc` → `PATCH /api/documents/<id>` `status=approved`). **View** opens a centered
**Document viewer** modal (`docView`) rendering the markdown in a `<pre>` with a **Download**
button (`downloadDoc`, Blob-based `.md` download) and `closeDocView` to dismiss.

### Profile & Documents sidebar tabs

The Profile slide-over is a tabbed **"Profile & Documents"** sidebar (`docsTab` selects the
active tab):

| Tab | Purpose | Endpoints called |
| --- | --- | --- |
| **Candidate** | The original résumé/profile fields (unchanged) | `/api/profile*` |
| **Behavioral** | Upload zone → agent drafts a behavioral profile (traits JSON, strengths tags, work-style paragraph) for per-field editing, then save | `POST /api/documents/ingest`, `POST /api/documents/ingest/save` (falls back to `GET`/`POST /api/behavioral-profile` when there is no pending upload) |
| **Writing** | Upload zone → agent drafts a writing-style profile (tone/formality/sentence_length, sample text, dos/donts tags) for per-field editing, then save | `POST /api/documents/ingest`, `POST /api/documents/ingest/save` (falls back to `GET`/`POST /api/writing-style` when there is no pending upload) |
| **Templates** | List + edit body + set-default-per-kind + New + Delete for `cover_letter`/`resume`/`job_evaluation` templates | `GET/POST /api/templates`, `GET/PATCH/DELETE /api/templates/<id>` |

Both the Behavioral and Writing tabs share the same upload → draft → edit → save flow: a file
dropped in the upload zone is posted to `POST /api/documents/ingest`, which runs the in-house
ingestion agent and returns an editable **draft** (nothing is persisted yet); approving it posts
to `POST /api/documents/ingest/save`, which upserts the record into its target table and logs a
`GET /api/documents/uploaded` row. A "Recent uploads" list (`uploadedDocs`, via `loadUploadedDocs`)
traces each uploaded file to the record it produced.

## Backend the frontend talks to

Same-origin `fetch` to the Flask JSON API (`/api/jobs*`, `/api/config*`, `/api/scrape*`,
`/api/profile*`, `/api/options/*`, `/api/recommend/*`, `/api/documents*`,
`/api/behavioral-profile`, `/api/writing-style`, `/api/templates*`, `/api/job-evaluation/<job_id>`).
See `docs/routes.md`.

> When/if a full React overhaul replaces dc-runtime, this map is replaced by a React
> component tree per `docs/skills/repository-structure/structures/web-interfaces.md`.
