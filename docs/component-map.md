# Component Map — Magnification

Ownership of frontend templates, JavaScript modules, and stylesheets. Source: `utils/frontend/`.

## Templates (`utils/frontend/templates/`)

| File | Role |
| --- | --- |
| `index.html` | SPA shell: loads CSS/JS, Tailwind config, and fetches all partials via `loadPartial()` |
| `parts/header.html` | Top nav: logo, desktop tabs (New Jobs / Tracker), "Find Jobs" button |
| `parts/mobile-nav.html` | Fixed bottom nav for mobile (icon tabs) |
| `parts/sidebar.html` | Desktop filters sidebar (search, filters) |
| `parts/job-detail-panel.html` | Slide-over job detail panel + backdrop |
| `parts/find_jobs.html` | "Find Jobs" configuration modal content |
| `parts/llm-dropdown.html` | Local-LLM selector dropdown |
| `primary/new-jobs.html` | New-jobs card grid view |
| `primary/tracker.html` | Kanban tracker board (Applied / Interviewing / Offers / Archived) |

## JavaScript (`utils/frontend/static/js/`)

| File | Role |
| --- | --- |
| `data.js` | Status definitions and shared client data |
| `helpers.js` | Utility helpers (e.g., `isJobNew`, `getCurrentStatus`) |
| `renderers.js` | Render functions for job cards, kanban cards, timeline |
| `handlers.js` | Event handlers: drag/drop, apply/ignore, tab switch, panel open/close |
| `app.js` | Entry point: DOM-ready init, column setup, initial render |
| `components/find_jobs_modal.js` | Find-Jobs modal behavior + scrape trigger |
| `components/llm-config.js` | LLM configuration UI logic |
| `components/llm-dropdown.js` | LLM dropdown behavior |

**Load order** (from `index.html`): `data.js` → `helpers.js` → `renderers.js` → `components/find_jobs_modal.js` → `handlers.js` → `app.js`. Dependencies must precede dependents.

## Styles (`utils/frontend/static/css/`)

| File | Role |
| --- | --- |
| `variables.css` | CSS custom properties / design tokens |
| `main.css` | Base styles, typography, scrollbars, animations |
| `components.css` | Timeline, kanban, drag-drop component styles |
| `modal.css` | Modal/dialog styles |
| `dropdown.css` | Dropdown styles |

Tailwind is loaded via CDN and configured inline in `index.html` (theme maps to the CSS variables).

## Ownership Guidance

- Reusable UI fragments → `templates/parts/`.
- Primary views → `templates/primary/`.
- Component behavior → `static/js/components/`.
- Cross-view rendering/handlers → top-level `static/js/`.
- Design tokens → `static/css/variables.css` and `docs/design-system.md`.

> When the React overhaul begins, this map is replaced by a React component tree (`components/ui`, `components/layout`, `components/feature`) per `docs/skills/repository-structure/structures/web-interfaces.md`.
