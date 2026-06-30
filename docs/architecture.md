# Web Architecture — Magnification

The structural decisions for Magnification's web layer, per `docs/skills/website-architecture/SKILL.md`.

## 1. Application Mode

**Primary mode:** Flask/Jinja monolith (Mode F). Flask renders a single `index.html` shell and serves HTML partials that are stitched together client-side via `fetch`; a JSON API (blueprints) backs all dynamic data. There is no separate frontend build step today.

**Secondary/future mode:** API + separate React frontend (Mode G). Planned, not started — see `docs/checklist.md`.

## 2. Frontend Stack

| Concern | Current choice |
| --- | --- |
| Language | Vanilla JavaScript (no build step) |
| Rendering | Server-rendered Jinja shell + client-fetched HTML partials |
| Styling | Tailwind via CDN + project CSS (`variables.css`, `main.css`, `components.css`, `modal.css`, `dropdown.css`) |
| UI primitives | Native HTML elements |
| Icons / fonts | FontAwesome, Lucide, Google Fonts (DM Sans, Space Grotesk, JetBrains Mono) |
| Data fetching | Direct `fetch` calls to the Flask JSON API |
| Routing | Backend-owned (Flask); client-side tab switching for views |
| Forms / validation | Native HTML + server-side validation |
| Tables / dense data | Custom card grid + kanban board |
| Motion | CSS transitions/animations |

> The React overhaul will re-decide this table. Do not assume React tooling now.

## 3. User Roles

Single-user, local-first. No authentication. One implicit role (the local operator) with full access to all routes and actions. There is no public/admin separation.

## 4. Frontend / Backend Boundary

- **Routing:** Flask owns all HTTP routing. `app.py` serves `/`, `/parts/<file>`, `/primary/<file>`; blueprints own `/api/*`.
- **Auth/session:** none.
- **Validation:** server-side, inside route handlers / service layer.
- **Contracts:** JSON over HTTP; documented in `docs/api-contract.md`.
- **Errors/caching:** handled per-endpoint server-side; the client renders loading/empty/error states.

## 5. Data Flow

Summarized here, detailed in `docs/data-flow.md`: scrapers → SQLite (via SQLAlchemy) → `/api/jobs*` → client renderers. LLM config/model/server state flows through the `llm` blueprint to `utils/LocalLLM`.

## 6. Backend / API

- Framework: Flask with four blueprints — `config_bp`, `scrape_bp`, `job_bp`, `llm_bp` (prefix `/api`).
- Contracts and error shapes: `docs/api-contract.md`.
- Shared schema location: SQLAlchemy models in `utils/backend/database/models.py`.

## 7. Design-Quality Gate

The visual motif, tokens, domain vocabulary, and required UI states are defined in `docs/design-system.md`. Mobile/responsive and accessibility requirements follow `docs/skills/accessibility-mobile/SKILL.md`.

## 8. Commands

See `docs/workflow.md` for install/run/test commands and `docs/deployment.md` for runtime/deploy assumptions.
