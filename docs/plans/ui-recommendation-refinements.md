# Plan: Recommendation UI/UX Refinements & LLM-Assisted Scraping

## Introduction

This plan refines the working RAG/LLM job app with targeted UX and intelligence
improvements. Most work lives in the single dc-runtime export
`utils/frontend/templates/index.html` (card layout, profile résumé UX, unified country
selection, profile-driven keywords) with two backend efforts: live step-by-step scraping
analytics and LLM-based compensation extraction for LinkedIn jobs.

Delivered in independently-committable phases from a dedicated git worktree branched off
`main`, validated per phase (`uv run pytest` + `import app` + `node --check` on the
component script + targeted preview checks), committed-not-pushed per phase, and merged
to `main` at the end. The bulk of changes concentrate in one large file (`index.html`)
that can't be safely edited by concurrent agents, so the work is implemented directly
rather than via a multi-agent fan-out.

## Gaps & Resolutions

- **Country unification** — *user-decided*: one searchable multi-country selector as the
  primary "Where", plus a clearly-separate optional "City / Remote" field. Backend keeps
  both params (`countries` → `country_indeed`; `location` → jobspy `location`); only the
  UI is unified.
- **Match-% breakdown popup** — anchored popover (not the full detail panel) showing the
  same score bars (semantic/keyword/BM25/skill) + LLM rationale from `analysis`. Jobs
  without analysis show no badge/"?".
- **Match-% color tiers** — red `<40`, amber `40–65`, green `≥66`.
- **Date format** — always `YYYY-MM-DD` from `created_at`, replacing relative strings.
- **Live analytics** — append-only, timestamped event log in the scrape job record,
  surfaced via the existing 1s status poll; progress view renders a live auto-scrolling
  feed. No new transport.
- **LinkedIn compensation extraction** — runs only when the LLM endpoint is enabled, only
  for LinkedIn jobs with a description but no parsed compensation, parallel via
  `chat_many`, non-fatal, gated behind a new `enable_llm_compensation` runtime toggle.
- **Profile-driven keywords** — opening Find Jobs prefers the active profile's
  `job_titles` (→ search terms) and `keyword_groups` (→ keyword groups) when present,
  falling back to saved config; re-fetched on each open.

## Steps

1. **Worktree + plan doc** — worktree `ui-reco-refinements` off `main`, this plan,
   smoke test. Commit `UI Refinements (1/7)`.
2. **New-Jobs card refinements** — remove company avatar; relocate match % below the
   ignore button with a `?` breakdown popover + color tiers; `YYYY-MM-DD` dates.
   `index.html`. Commit `(2/7)`.
3. **Résumé drag-and-drop + Build button** — stylized dropzone + "Build Profile (LLM)"
   action in the Profile panel. `index.html`. Commit `(3/7)`.
4. **Unified country selector** — one searchable multi-country select + optional
   City/Remote, under a single "Where" section; expand the country list. `index.html`.
   Commit `(4/7)`.
5. **Profile-built keywords drive Find Jobs** — `openFindAndLoad` fetches the active
   profile and prefers its titles/keyword groups; refresh on open. `index.html`.
   Commit `(5/7)`.
6. **Live scraping analytics** — append-only event log in `scrape_routes.py`, finer
   `update_progress` in `scraping_service.py`, live feed in the progress view.
   Commit `(6/7)`.
7. **LLM compensation extraction + docs + merge** — `utils/backend/recommend/compensation.py`,
   runtime toggle + Options UI, wire into `scraping_service.py`, tests, docs; merge to
   `main`. Commit `(7/7)`.

## Deliverables

| Deliverable | Location |
| --- | --- |
| Card refinements | `utils/frontend/templates/index.html` |
| Résumé dropzone + Build | `utils/frontend/templates/index.html` |
| Unified country selector | `utils/frontend/templates/index.html` |
| Profile→keywords wiring | `utils/frontend/templates/index.html` |
| Live scrape analytics | `scrape_routes.py`, `scraping_service.py`, `index.html` |
| LLM compensation extractor | `recommend/compensation.py`, `scraping_service.py`, `runtime_config.py`, `options_routes.py`, `index.html` |
| Compensation test | `tests/recommend/test_compensation.py` |
| Scrape-events test | `tests/scrapers/test_scrape_events.py` |
| Docs | `docs/*` |
