# Profile System — Magnification

The **profile** is the comparison target for the RAG + LLM recommendation system. It is
built from the user's résumé and edited in the **Profile** panel (header button, left of
Find Jobs).

## What a profile contains

| Field | Purpose |
| --- | --- |
| `llm_instructions` | Optional free-text guidance the user types to steer the LLM profile build (which job titles/queries/skills to emphasize, how to frame interests). Injected ahead of the résumé as a prioritized instruction; edited in the Profile panel above the résumé section. |
| `interests_paragraph` | Open-body paragraph of research/job interests — used by the **LLM** matching pass. |
| `skills` | List of skills — matched against skills extracted from each job description. |
| `job_titles` | List of search-query titles — seed the Find Jobs search. |
| `keyword_groups` | `[{label, terms:[...], scopes:[...]}]` — **AND across groups, OR within a group**, applied as a **hard filter**: a job is hidden unless *every* group matches. `scopes` ⊆ `{"title","description"}` (defaults to both) picks where each group's terms must appear — e.g. an "intern" group scoped to Title-only requires "intern" in the title, not just the description. |
| `blocked_companies` | List of company names (case-insensitive, exact) whose jobs are always hidden. Added via the per-card **Block** button or edited in the Profile panel. |
| `title_blocklist` | List of substrings; any job whose **title** contains one is hidden (e.g. "Senior"). |
| `resume_text`, `source_filename` | The extracted résumé text + original filename (kept so the profile can be rebuilt). |

Profiles live in the `profiles` table (see `docs/database.md`); exactly one is `is_active`.
The shipped UI manages a single "default" profile.

## Blocking (blocklists & scoped keyword groups)

The active profile is the single source of truth for user-defined blocking. Three rules, any of
which hides a job (sets `ignore=1`): `blocked_companies`, `title_blocklist`, and an unsatisfied
scoped `keyword_groups` entry. The pure predicates live in
`utils/backend/scrapers/profile_filter.py` and are applied:

- **at scrape time** — `job_filter.filter_and_mark_jobs` consults the active profile alongside the
  per-search `jobs_config` keyword filter;
- **retroactively / on demand** — `job_filter.apply_profile_filters(job_ids=None)` re-hides
  matching jobs when a company is blocked (`POST /api/profile/block-company`) or the profile is
  saved (`POST /api/profile`).

Blocking is **one-directional**: applying rules only hides jobs; removing a rule does not un-hide
already-hidden jobs (a re-scrape re-evaluates from scratch).

## Building from a résumé

1. **Upload** (`POST /api/profile/upload`) — accepts **PDF / LaTeX (.tex) / Markdown (.md)**.
   `utils/backend/recommend/profile_builder.extract_resume_text` extracts plain text
   (`pypdf` for PDF; light comment-stripping for LaTeX; raw for Markdown).
2. **Draft** — if the LLM endpoint is enabled (Options), `build_profile_from_text` asks the
   model for a structured profile (`interests_paragraph`, `skills`, `job_titles`,
   `keyword_groups` **with per-group `scopes`**, `title_blocklist`, and `blocked_companies`)
   and `normalize_profile` coerces it into the canonical shape. The model chooses each group's
   `scopes` (Title-only for role/seniority words, both otherwise) and fills `title_blocklist`
   from the user's stated exclusions; it only returns `blocked_companies` when the user's
   instructions **explicitly name** companies to block (never invented). When the profile has
   **`llm_instructions`**, they are injected ahead of the résumé as a prioritized instruction so
   the generated sections follow the user's intent, not just the résumé. If the LLM is disabled,
   an empty draft is returned for manual entry. **Nothing is persisted yet.**
3. **Edit** — the user reviews/edits every field in the Profile panel.
4. **Save** (`POST /api/profile`) — `upsert_active_profile` writes the active profile.
5. **Rebuild** (`POST /api/profile/build`) — regenerate fields from the stored `resume_text`
   without re-uploading (requires the LLM). Regenerated fields replace their prior values, except
   **`blocked_companies`, which is unioned** so a rebuild never drops companies the user blocked
   via the card button.

## API

See `docs/routes.md` / `docs/api-contract.md` for the `profile_bp` endpoints
(`/api/profile`, `/api/profile/upload`, `/api/profile/build`).

## Frontend

The Profile panel is a right slide-over in `utils/frontend/templates/index.html`
(`profileOpen` state; `openProfile`/`loadProfile`/`saveProfile`/`onResumeFile`/`rebuildProfile`
methods; `pf*` render values). See `docs/component-map.md`.
