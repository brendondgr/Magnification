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

> **File-size exception:** `index.html` far exceeds the repo's 800-line guideline (~2,800 lines).
> It is a generated single-file design export and the runtime requires the component class
> inline, so it cannot be split without modifying the vendored runtime. Accepted and tracked.

## Component model (dc-runtime)

- **State** lives in `this.state`; mutate via `this.setState(...)`.
- **`renderVals()`** returns the object the template interpolates against.
- Template syntax: `{{ value }}` interpolation, `<sc-if value="{{ x }}">`, `<sc-for list="{{ y }}" as="item">`, and `on*` handlers (`onclick`, `oninput`, `onchange`, `onkeydown`).

### Feature areas inside the component

| Area | State keys | Key methods |
| --- | --- | --- |
| Jobs / Tracker / Saved | `jobs, tab, selectedId, searchNew, searchSaved, searchTracker, sortByMatch, savedSortByMatch, filterBusy, page, dragOverCol` | `loadJobs`, `filterJobs` (POST `/api/jobs/filter`), `mapDbJob`, `keywordMatch`, `deriveColumn`, `statusesForColumn`, `toggleIgnore`, `toggleSave`, `unsave`, `copyJobMarkdown`, `blockCompany`, `addSkillToProfile`, `markApplied`, `onMarkApplied`, `moveTo`, `toggleStatus` |
| **Application Mode** | `app{open,jobId,company,title,stage('intake'\|'generating'\|'review' — the last two render one unified workspace),tab,pane('process'\|'preview'),wantCover,wantResume,guidance,gen{cover_letter{active,taskId,percent,stage,message},resume{...}},feed{cover_letter,resume},docs{cover_letter,resume},pdf{cover_letter{url,loading,error,log},resume{...}},edit{cover_letter,resume},refine{cover_letter,resume}}` | `openApply`, `closeApply`, `_clearAppPollers`, `setApp`, `_setAppNested`, `toggleAppKind`, `setGuidance`, `loadAppDocs`, `reviewExisting`, `startApply`, `_startGen`, `_pollApp`, `_fetchAppDoc`, `_finishGen`, `_genFail`, `selectAppTab`, `setAppPane`, `loadPdf`/`_setPdf`/`openAppPdf`, `editDoc`/`editInput`/`cancelEdit`/`saveEdit`, `refineInput`/`quickRefine`/`submitRefine`, `approveAppDoc`, `downloadAppDoc`, `downloadAppTex`, `markAppliedAndClose`, `appCard`, `appToggleStyle`/`appCheckStyle` |
| Find Jobs | `findOpen, findView, terms, sites, groups, location, ageIndex, maxResults, maxIterations, useLLM, percent, stage, statusMsg, found, saved, notHidden, scrapeEvents, scrapeDone` | `openFind`, `startScrape`, `pollScrape`, `configToSave` |
| Analyze Matches popup | `analyzing, analyzeOpen, aPercent, aStage, aStatusMsg, aEvents, aDone, aTotal, aLLM, aComp` | `analyzeJobs` (POST `/analyze/start`), `pollAnalyze` (poll `/analyze/status/<id>`), `closeAnalyze` |
| **Profile & Documents** | `profileOpen, docsTab('candidate'\|'guidance'), profile{llm_instructions,interests_paragraph,skills,job_titles,keyword_groups(+scopes),blocked_companies,title_blocklist,resume_text,...}, pf*Draft, pfBusy, pfSkillsExpanded, guidanceText, guidanceBusy, guidanceStatus, guidanceIsDefault` | `openProfile` (now also calls `loadDocuments`), `loadProfile`, `saveProfile`, `blockCompany`, `addSkillToProfile`, `onResumeFile`, `rebuildProfile` (unions `skills` + `blocked_companies`), `pfSet`; guidance: `loadDocuments` (loads the guidance), `saveGuidance`, `resetGuidance` |
| **Options** | `optionsOpen, optionsTab, llm{...}, runtime{...}, llmTest` | `openOptions`, `loadOptions`, `saveLlmOptions`, `testLlmOptions`, `saveRuntimeOptions`, `llmSet`/`rtSet`/`rtWeightSet` |

Main-view tabs: **New Jobs · Saved · Tracker** (desktop nav + mobile bottom nav). The **Saved**
tab is a grid (mirroring the New Jobs card) of every job with `saved=1`, shown regardless of
ignore/applied state; saved jobs are excluded from the New Jobs feed. Applying retires a job from
Saved: `markApplied` calls `unsave(id)` when the job was saved, so a job lives in Saved *or* the
Tracker, not both.

**Job card (New Jobs + Saved), row-based:** the `decorate(job)` view-model drives a 7-row
`<article>` — five information rows, then the two action rows:

| Row | Left | Right |
| --- | --- | --- |
| 1 | source pill (`siteBadge`) | industry tag (`industryBadge`/`industryDot`, colored per `Component.INDUSTRY_COLORS`, `margin-left:auto`; only when `hasIndustry`) |
| 2 | title — `-webkit-line-clamp:2`, never more than two lines | — |
| 3 | company + extraction date in parentheses (`foundOn`, back-to-back) | match % + "?" breakdown (only when `hasMatch`) |
| 4 | location pill | compensation pill (`compensationColor`: pay-green, or muted for "Not Specified") |
| 5 | description — `-webkit-line-clamp:4`, never more than four lines | — |

Row 6 is the primary actions — **Generate** (`onApply` → Application Mode; renamed from
"Apply") + **Applied** (`onMarkApplied`); row 7 is the icon-button row — Info (`onOpen`), Block
company (`onBlock`), Hide (`onIgnore`), Save (`onSave`), Link out (`onLink`), sharing the
neutral `iconBtn` style with the stateful `blockBtn`/`ignoreBtn`/`saveBtn`. The job detail panel
gains an **Industry** line and keeps the same Block/Save controls (`toggleSave` →
`PATCH /api/jobs/<id>/save`), plus a **Copy** button to the right of Save (`onCopy` →
`copyJobMarkdown`) that puts a Markdown document — `# title`, `**Company:**`, `## Job Description`
— on the clipboard via `navigator.clipboard` with a `execCommand('copy')` textarea fallback.

**Compensation display:** `payLabel(raw)` is the client-side mirror of the backend's
`clean_compensation` — a blank, placeholder, `nan`-carrying, or digit-less value renders as
**"Not Specified"** (`Component.NO_PAY`) in muted text rather than pay-green. It is the last
line of defense behind the fixed salary formatter and the `migrate_clean_bad_compensation`
repair, so a malformed board value can never reach the card.

**Per-page search + sort:** New Jobs and Saved each own an **independent** in-page search box
(`searchNew` / `searchSaved`). `keywordMatch(job, query)` matches across **every** card field —
title, company, location, compensation, site, description, and the analyzed skill lists
(`skill_match.matched`/`.missing`) — requiring every whitespace-separated token to appear
(case-insensitive substring; empty query = all). New Jobs keeps its Newest/Match toggle
(`sortByMatch`); Saved adds one (`savedSortByMatch`) defaulting to **Newest** (`createdAt` desc)
and toggling to **Match** (score desc, no-score last). The former single sidebar search box +
`matchSearch` were removed.

**New Jobs header actions**, left to right: the search box, the Newest/Match sort toggle,
**Filter**, **Analyze matches**, **Show Ignored (n)**. **Filter** (`filterJobs`, `filterBusy`,
`filterLabel`, `filterStyle`) POSTs `/api/jobs/filter` to re-apply the Find Jobs
title/description keywords *and* the profile's title blocklist / blocked companies / keyword
groups to every currently visible job, then toasts how many were hidden and reloads the feed. It
only ever hides (saved jobs exempt) — see `docs/data-flow.md`.

The **Application Tracker** owns its own in-page search box (`searchTracker`) using the same
`keywordMatch` matcher; each kanban column filters its cards by it (the `N ACTIVE` header count
stays the unfiltered pipeline total).

**Tracker columns** (`Component.COLS`): **Applied · Interviewing · Offers · Rejected · Ghosted**
(the final lane's internal key/token stay `archived`/`--c-archive`; only the label is "Ghosted").
`deriveColumn` maps a job's checked statuses to a column — **Ignored/Ghosted** → Ghosted;
**Rejected** or **Post-Interview Rejection** → Rejected; **Offer**/**Accepted** → Offers;
any **Interview 1-3** → Interviewing; else Applied. Dragging a card runs `statusesForColumn`,
which sets the matching status and clears the others for that column (Rejected sets `Rejected`;
the Ghosted lane sets `Ignored/Ghosted`). The Rejected column is tinted with the `--c-reject` token.

Tracker **cards are slimmed to title + company only** (no initials avatar, location, or
compensation chip — those live on the New Jobs / Saved cards). The lane row is capped to the
viewport with `min-width:0;min-height:0` on the tracker `section` + row so its `overflow-x:auto`
scrolls the columns instead of overflowing the screen. The **job detail panel** adds a read-only
**Pipeline History** (`selectedJob.pipeline`) listing Found / Applied / Interviewing / Offer /
Rejected / Ghosted with their durable, write-once first-dates (from the `date_first_*` / `date_found`
job fields).

Header nav order: **New Jobs · Tracker · Profile · Find Jobs · Options · theme toggle**
(Profile left of Find Jobs, Options right, and a `role="switch"` sun/moon pill right of
Options that flips the `arctic`/`midnight` themes — `toggleTheme()`, persisted to
`localStorage['magnify.theme']`, desktop-only via `data-desk`). Profile + Options are
right-side slide-over panels mirroring the job detail panel; Find Jobs is a centered modal.

### Find Jobs progress view

`startScrape` resets `found`/`saved`/`notHidden` to 0 and `pollScrape` polls
`/api/scrape/status/<id>` once a second, feeding three stat tiles (`scrapeStats`):
**Jobs Found** (`s.found`) · **Jobs Saved** (`s.saved`) · **Not Hidden** (`s.notHidden`), plus the
percent ring and the live activity feed built from `s.scrapeEvents`.

All three read the **run-cumulative** counters the backend reports in `progress.details`
(`jobs_found`, `jobs_saved`, `jobs_kept`) — a multi-iteration search accumulates across passes
instead of restarting per pass, and `jobs_saved` updates as each iteration's rows land rather than
only at completion. The poller additionally clamps each tile with `rise(cur,next)` (a `Math.max`
against the pre-patch state) so an out-of-order poll cannot walk a counter backwards, and reads
the final values off `results.jobs_found`/`jobs_saved`/`jobs_unique` rather than a last-pass
`steps` slice. See `docs/data-flow.md` and `docs/api-contract.md`.

### Application Mode

The job-detail slide-over no longer has a Documents section or a document-viewer modal; document
generation and review moved into **Application Mode**. Cards (New Jobs + Saved grids) and the
job-detail footer each show two buttons: **Apply** (`openApply(job)`, opens Application Mode) and
**Applied** (`onMarkApplied`, a quick one-step `markApplied` with no generation). Application Mode
itself is a centered modal — mirroring the Find Jobs modal shell — driven by the `app` state
object. It opens on an **Intake** stage, then hands off to one **unified two-column workspace**
(the `generating` and `review` stages render the same layout, gated by the `appWorkspace`
renderVal):

- **Intake** (`stage: 'intake'`) — toggles for "Tailor my résumé" / "Write a cover letter"
  (`toggleAppKind`, both on by default), an optional guidance textarea (`setGuidance`), and
  Start (`startApply`) / just-mark-Applied / Cancel (`closeApply`) actions. If the job already
  has drafts, a "Review existing drafts" shortcut (`reviewExisting`) skips straight to the
  workspace.
- **Workspace** (`stage: 'generating'` → `'review'`) — a `data-appws` CSS grid showing one
  document at a time. **Document tabs** (`appTabButtons`, `selectAppTab`) switch Tailored Résumé ∣
  Cover Letter; under 920px the grid collapses to one column and a **Process ∣ Preview** segmented
  control (`setAppPane`, `appPane`) picks which side is visible. `appCard(kind)` builds each
  document's view model, exposed as `appActive` for the selected tab. Documents are generated in
  parallel via `_startGen(kind, opts)`, each polled every 700ms by `_pollApp(kind, taskId)`
  (`GET /api/documents/status/<task_id>`); `_finishGen` fetches the finished doc (`_fetchAppDoc`)
  and triggers its PDF, `_genFail` handles a failure.
  - **Process** (left column) — a live **step-by-step agent feed** rendered from the task
    `events[]` (`feed`, showing prior node steps and revision loops), a percent bar + résumé
    match-lift badge (colored via `this.matchColorFor`) while running, the refine chips (Warmer
    tone / More concise / Different angle / Stronger opening) + free-text Regenerate box
    (`refineInput`, `quickRefine`, `submitRefine` — re-runs generation via `revise_from` +
    instructions), and **Edit LaTeX** (`editDoc`/`editInput`/`saveEdit`/`cancelEdit`, an inline
    source textarea PATCHed on save) / **Download PDF** (`downloadAppDoc`) / **Export .tex**
    (`downloadAppTex`, the raw LaTeX source from `GET /api/documents/<id>/tex`) / **Approve**
    (`approveAppDoc`) actions.
  - **Preview** (right column) — the compiled **PDF** in an `<iframe>` whose `src` is set via a
    React `ref` (`appActive.pdfRef`), **not** a bound `src` attribute (a bound `{{…}}` src would
    make the raw template fetch a literal URL before hydration). `loadPdf`/`_setPdf` fetch and
    cache the blob per kind (`pdf{url,loading,error,log}` from `GET /api/documents/<id>/pdf`),
    re-fetching after each generation, refine, or edit; `openAppPdf` opens it in a new tab.

  `appToggleStyle`/`appCheckStyle` drive the Intake toggle chips. The footer offers **Mark as
  Applied** (`markAppliedAndClose`) or **Close** (`closeApply`).

`componentWillUnmount` clears the Application Mode pollers (`_clearAppPollers`). The prior
`generateDoc`/`pollGen`/`viewDoc`/`closeDocView`/`approveDoc`/`downloadDoc`/`loadJobDocuments`
methods and the `docGen`/`docView`/`docsByJob` state are gone.

### Profile & Documents sidebar tabs

The Profile slide-over is a two-tab **"Profile & Documents"** sidebar (`docsTab` selects the
active tab):

| Tab | Purpose | Endpoints called |
| --- | --- | --- |
| **Candidate** | The résumé/profile fields (unchanged) | `/api/profile*` |
| **Guidance** | A textarea holding the single editable **Document Guidance** that steers every cover letter + résumé, with Save + Reset-to-default | `GET/PUT /api/document-guidance`, `POST /api/document-guidance/reset` |

The Guidance tab loads the guidance on open (`loadDocuments` → `GET /api/document-guidance`), edits
it in place (`guidanceText`), and `saveGuidance` / `resetGuidance` persist or clear the override. The
former Behavioral / Writing / Templates tabs and their upload-ingestion flow were removed (see
`docs/plans/documents-sidebar-simplify.md`).

## Backend the frontend talks to

Same-origin `fetch` to the Flask JSON API (`/api/jobs*`, `/api/config*`, `/api/scrape*`,
`/api/profile*`, `/api/options/*`, `/api/recommend/*`, `/api/documents*`,
`/api/document-guidance*`, `/api/job-evaluation/<job_id>`).
See `docs/routes.md`.

> When/if a full React overhaul replaces dc-runtime, this map is replaced by a React
> component tree per `docs/skills/repository-structure/structures/web-interfaces.md`.
