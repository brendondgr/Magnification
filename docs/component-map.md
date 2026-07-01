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
| Jobs / Tracker | `jobs, tab, selectedId, search, page, dragOverCol` | `loadJobs`, `mapDbJob`, `toggleIgnore`, `blockCompany`, `markApplied`, `moveTo`, `toggleStatus` |
| Find Jobs | `findOpen, findView, terms, sites, groups, location, ageIndex, maxResults, useLLM` | `openFind`, `startScrape`, `pollScrape`, `configToSave` |
| **Profile** | `profileOpen, profile{llm_instructions,interests_paragraph,skills,job_titles,keyword_groups(+scopes),blocked_companies,title_blocklist,resume_text,...}, pf*Draft, pfBusy` | `openProfile`, `loadProfile`, `saveProfile`, `blockCompany`, `onResumeFile`, `rebuildProfile`, `pfSet` |
| **Options** | `optionsOpen, optionsTab, llm{...}, runtime{...}, llmTest` | `openOptions`, `loadOptions`, `saveLlmOptions`, `testLlmOptions`, `saveRuntimeOptions`, `llmSet`/`rtSet`/`rtWeightSet` |

Header nav order: **New Jobs · Tracker · Profile · Find Jobs · Options** (Profile left of Find
Jobs, Options right). Profile + Options are right-side slide-over panels mirroring the job
detail panel; Find Jobs is a centered modal.

## Backend the frontend talks to

Same-origin `fetch` to the Flask JSON API (`/api/jobs*`, `/api/config*`, `/api/scrape*`,
`/api/profile*`, `/api/options/*`, `/api/recommend/*`). See `docs/routes.md`.

> When/if a full React overhaul replaces dc-runtime, this map is replaced by a React
> component tree per `docs/skills/repository-structure/structures/web-interfaces.md`.
