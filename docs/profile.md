# Profile System — Magnification

The **profile** is the comparison target for the RAG + LLM recommendation system. It is
built from the user's résumé and edited in the **Profile** panel (header button, left of
Find Jobs).

## What a profile contains

| Field | Purpose |
| --- | --- |
| `interests_paragraph` | Open-body paragraph of research/job interests — used by the **LLM** matching pass. |
| `skills` | List of skills — matched against skills extracted from each job description. |
| `job_titles` | List of search-query titles — seed the Find Jobs search. |
| `keyword_groups` | `[{label, terms:[...]}]` — **AND across groups, OR within a group** (same convention as `utils/backend/scrapers/job_filter`). E.g. an "AI/ML" group AND a "Healthcare" group. |
| `resume_text`, `source_filename` | The extracted résumé text + original filename (kept so the profile can be rebuilt). |

Profiles live in the `profiles` table (see `docs/database.md`); exactly one is `is_active`.
The shipped UI manages a single "default" profile.

## Building from a résumé

1. **Upload** (`POST /api/profile/upload`) — accepts **PDF / LaTeX (.tex) / Markdown (.md)**.
   `utils/backend/recommend/profile_builder.extract_resume_text` extracts plain text
   (`pypdf` for PDF; light comment-stripping for LaTeX; raw for Markdown).
2. **Draft** — if the LLM endpoint is enabled (Options), `build_profile_from_text` asks the
   model for a structured profile (`interests_paragraph`, `skills`, `job_titles`,
   `keyword_groups`) and `normalize_profile` coerces it into the canonical shape. If the LLM
   is disabled, an empty draft is returned for manual entry. **Nothing is persisted yet.**
3. **Edit** — the user reviews/edits every field in the Profile panel.
4. **Save** (`POST /api/profile`) — `upsert_active_profile` writes the active profile.
5. **Rebuild** (`POST /api/profile/build`) — regenerate fields from the stored `resume_text`
   without re-uploading (requires the LLM).

## API

See `docs/routes.md` / `docs/api-contract.md` for the `profile_bp` endpoints
(`/api/profile`, `/api/profile/upload`, `/api/profile/build`).

## Frontend

The Profile panel is a right slide-over in `utils/frontend/templates/index.html`
(`profileOpen` state; `openProfile`/`loadProfile`/`saveProfile`/`onResumeFile`/`rebuildProfile`
methods; `pf*` render values). See `docs/component-map.md`.
