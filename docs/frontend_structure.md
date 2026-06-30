# Frontend Structure - Magnification

## Overview

The frontend is a single **dc-runtime design component** exported from Claude's
design tool and wired to the Flask API. It completely replaces the previous
modular Tailwind/partials frontend. The entire UI — New Jobs grid, application
Tracker (kanban), job detail panel with status timeline, the Find Jobs scrape
modal, and the sidebar — is one React component rendered by the dc-runtime.

---

## Directory Structure

```
utils/frontend/
├── static/
│   └── js/
│       └── dc-runtime.js     # Vendored design runtime (boots React, renders <x-dc>)
└── templates/
    └── index.html            # The whole app: <x-dc> template + <script data-dc-script> Component
```

There are no separate CSS/partials/view files — styling is inline in the
template (CSS variables + a small keyframes block in `<helmet>`), and all
behaviour lives in the `Component` class.

---

## How It Renders

1. Flask serves `templates/index.html` at `/` (`app.py` → `index()`).
2. `<script src="/static/js/dc-runtime.js">` loads the runtime, which fetches
   React 18 (+ Babel) from unpkg and Google Fonts, then boots the `<x-dc>` block.
3. The runtime compiles the template's `{{ … }}` interpolations and binds them to
   the values returned by `Component.renderVals()`.
4. `Component` (in the `<script type="text/x-dc" data-dc-script>` block) holds all
   state and fetches/persists data through the API.

> Requires internet at page load (React/Babel/fonts come from CDN).

---

## Component Data Flow (the wiring)

`Component extends DCLogic` is the single source of truth.

| Concern | Method(s) | API |
| --- | --- | --- |
| Initial load | `componentDidMount` → `loadJobs` → `mapDbJob` | `GET /api/jobs` |
| DB → view mapping | `deriveApplied`, `deriveColumn`, `daysAgoFrom`, `siteLabel` | — |
| Ignore toggle | `toggleIgnore` | `PATCH /api/jobs/<id>/ignore` |
| Timeline / apply / kanban move | `toggleStatus`, `markApplied`, `moveTo` → `persistStatuses` | `PATCH /api/jobs/<id>/status` |
| Clear database | `clearDatabase` | `POST /api/database/clear` |
| Find modal prefill | `openFindAndLoad` | `GET /api/config/load` |
| Start scrape | `startScrape` → `configToSave` | `POST /api/config/save`, `POST /api/scrape/start` |
| Progress polling | `pollScrape` | `GET /api/scrape/status/<job_id>` |

### Model mapping notes

- **Status / column**: the DB has 9 `APPLICATION_STATUSES`; the tracker has 4
  columns. `deriveColumn` maps them: archived (Rejected / Post-Interview
  Rejection / Ignored-Ghosted), offers (Offer / Accepted), interviewing (any
  Interview N), else applied. A job is "new" when `Applied` is unchecked.
- **Timeline** uses the 9 real statuses so each toggle persists.
- **Config mapping**: `terms`↔`search_terms`, `ageIndex`↔`hours_old`
  ([24,72,168,336,504,720]), site labels↔config keys (Indeed↔indeed,
  LinkedIn↔linkedin, Glassdoor↔glassdoor, ZipRecruiter↔zip_recruiter,
  Google↔google), keyword groups↔`description_keywords`, `useLLM`↔`use_llm`.

---

## API Endpoints Consumed

- `GET  /api/jobs` — all jobs hydrated with their 9 statuses
- `GET  /api/jobs/<id>` — single job
- `PATCH /api/jobs/<id>/ignore` — `{ ignore: 0|1 }`
- `PATCH /api/jobs/<id>/status` — `{ status, checked, date_reached }`
- `POST /api/database/clear`
- `GET  /api/config/load` · `POST /api/config/save`
- `POST /api/scrape/start` — `{ use_config: true }`
- `GET  /api/scrape/status/<job_id>`

The LLM server/model-management UI from the old frontend was dropped; only the
"LLM refinement" checkbox remains (saved into the scrape config as `use_llm`).
The `llm_routes.py` blueprint still exists server-side but is no longer used by
the UI.

---

## Tests

`tests/test_frontend_wiring.py` (Flask test client) locks the contract: the
index page is the dc shell, the runtime asset is served, the jobs API hydrates
+ persists ignore/status, and config save creates its dir and round-trips.

---

## Modifying the UI

The design is a single exported artifact. To change behaviour, edit the
`Component` class inside `templates/index.html`. To restyle, edit the inline
styles in the `<x-dc>` template / the CSS-variable theme blocks in `THEMES`.
Keep `dc-runtime.js` as-is (it is generated; do not hand-edit).
