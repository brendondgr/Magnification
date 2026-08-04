# Web Architecture — Magnification

The structural decisions for Magnification's web layer, per `docs/skills/website-architecture/SKILL.md`.

## 1. Application Mode

**Mode F — Flask monolith.** `app.py` serves one page (`utils/frontend/templates/index.html`) and
ten JSON API blueprints. The page is a self-contained design export: a vendored runtime
(`utils/frontend/static/js/dc-runtime.js`) hydrates a `<script type="text/x-dc">` block into React
elements in the browser. There is **no build step**, no bundler, and no HTML partials — the whole
UI is that one file.

**Future mode:** API + a separately built React frontend (Mode G). Planned, not started — see
`docs/checklist.md`.

## 2. Frontend Stack

| Concern | Current choice |
| --- | --- |
| Language | Plain JavaScript inside `index.html` (class `Component extends DCLogic`) |
| Rendering | `dc-runtime.js` hydrates the inline template + `React.createElement` in JS methods |
| Styling | Inline `style` attributes plus per-theme CSS custom properties (`Component.THEMES`) — no external stylesheets, no Tailwind |
| Themes | `midnight` (dark) and `arctic` (light), swapped by writing the token set onto the root element |
| Icons | Inline SVG built with `React.createElement` — no icon library |
| Fonts | `Archivo` (body), `Space Grotesk` / `Newsreader` (headings, per theme), `JetBrains Mono` (numeric/label) |
| Data fetching | Direct `fetch` calls to the Flask JSON API |
| Routing | Flask owns HTTP; the client hash-routes the three top-level views (`#/new-jobs`, `#/saved`, `#/tracker`) |
| Long-running work | Start-then-poll: `POST .../start` returns a task id, the client polls `.../status/<id>` |
| Forms / validation | Native inputs; validation in the route handlers |
| Dense data | Card grid (New Jobs, Saved) + five-column kanban (Tracker) |
| Motion | CSS transitions via `style-hover` / `style-active` / `style-focus` attributes |

> The React overhaul will re-decide this table. Do not assume React tooling now.

## 3. User Roles

Single-user, local-first. No authentication, no sessions, one implicit role with full access.

## 4. Frontend / Backend Boundary

- **Routing:** `app.py` serves only `/` (plus Flask's `/static/<path>`); every blueprint owns its
  own `/api/*` paths. Full map in `docs/routes.md`.
- **Auth/session:** none.
- **Validation:** server-side, inside route handlers and the service modules they call.
- **Contracts:** JSON over HTTP, documented in `docs/api-contract.md`.
- **Errors:** each endpoint returns its own error shape; the client renders loading/empty/error
  states per view.

## 5. Data Flow

Summarized here, detailed in `docs/data-flow.md`: scrapers → SQLite (SQLAlchemy) → `/api/jobs*` →
the client. Recommendation scoring, description enrichment, and document generation each read from
the same database and write back through `utils/backend/database/operations.py`.

## 6. Backend / API

- Flask with **ten** blueprints registered in `app.py`: `config_bp`, `scrape_bp`, `job_bp`,
  `llm_bp`, `options_bp`, `profile_bp`, `recommend_bp`, `documents_bp`, `generation_bp`,
  `guidance_bp`.
- Schema: SQLAlchemy models in `utils/backend/database/models.py`; migrations run on import via
  `init_database()`.
- Background work (scrape, analyze, document generation) runs in daemon threads with an in-memory
  task store per blueprint — nothing survives a restart by design.

## 7. Design-Quality Gate

Visual motif, tokens, and required UI states live in `docs/design-system.md`. Responsive and
accessibility requirements follow `docs/skills/accessibility-mobile/SKILL.md`.

## 8. Commands

See `docs/workflow.md` for install/run/test commands and `docs/deployment.md` for runtime and
deploy assumptions.
