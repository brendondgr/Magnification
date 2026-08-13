# Project Checklist — Magnification

What is still open, and a ledger of what has shipped. Each shipped entry links its plan in
`docs/plans/`, which keeps the full root-cause analysis, phase breakdown, and verification notes —
this file no longer repeats them.

## Open

### Roadmap

- [ ] **Migrate web code to `web/`** per `docs/skills/repository-structure/structures/web-interfaces.md`.
  Deferred: the app works and a frontend rebuild is planned first.
- [ ] **React frontend overhaul** — rebuild `utils/frontend` as a React app, and re-run
  `docs/skills/website-architecture/` to choose the stack.
- [ ] **Add `ruff`** for lint + format; record the commands in `docs/workflow.md`.
- [ ] **`.env.example`** — only if environment variables are ever introduced (config is JSON files
  today).

### Feature gaps

- [ ] **Application submission (design §4.3)** — the browser-automation adapter and a persisted
  `application_sessions` table. The Apply flow currently generates and reviews documents; the user
  submits them manually. See `docs/plans/agentic-documents-application-mode.md`.
- [ ] **Mobile theme toggle** — the switch is `data-desk` (hidden below 880px). Decide a mobile home
  (e.g. the Options panel) if phone users need the dark theme.

### Housekeeping

- [ ] **Two tests are not offline.** `tests/test_config_loading.py` hits real job boards and
  `tests/recommend/test_recommend_service.py::test_analyze_api_and_report` needs the cached
  embedding model plus a reachable LLM endpoint (it fails against a 502-ing proxy). Both violate
  the offline-tests rule in `docs/workflow.md` — mock them or mark them so a plain `uv run pytest`
  is green everywhere.
- [ ] **`utils/backend/database/migrate_site_field.py` is orphaned** — a working migration that
  `init_db._run_migrations()` never calls and nothing else imports. Fresh databases get `jobs.site`
  from `create_all`, so it only matters for a pre-existing DB missing that column. Wire it in or
  delete it.

### Environment-dependent verification

These paths are covered by offline tests with a mocked LLM client or a mocked scraper. They have
never been exercised against live services, and cannot be from this environment:

- [ ] **A live LLM endpoint** (Options → LLM Endpoint) is needed to judge real output quality for:
  fit verdicts and LLM coverage, compensation + industry enrichment, keyword generation, profile
  building, cover-letter and résumé prose, the flow-smoothing audit/rewrite pass, and bounded
  reasoning via `thinking_token_budget`.
- [ ] **A live multi-iteration scrape** against real job boards is needed to watch the cumulative
  counters climb end-to-end. The accumulation and poller math are proven against a replayed real
  status stream with faked boards.
- [ ] **`pdflatex` on the host** is needed for PDF preview/download; without it `/api/documents/<id>/pdf`
  returns 422 and only the raw `/tex` source is available.
- [ ] **The daily systemd scrape** has never fired a real run. The gate, retry, once-per-day stamp,
  and scrape invocation are covered by mocked tests plus a live `--check-llm` probe.

## Shipped

Every entry below was delivered on a branch, committed per phase, and merged to `main`. Read the
linked plan for the details.

| Area | Work | Plan |
| --- | --- | --- |
| Recommendation | RAG + LLM recommendation overhaul (profile, embeddings, BM25, hybrid ranker) | `rag-llm-recommendation.md` |
| Recommendation | Pipeline reorder + LLM-weighted scoring (weights must total 1.0) | `reco-pipeline-scoring.md` |
| Recommendation | LLM fit for every analyzed job, with an adjustable coverage fraction | `all-jobs-llm-fitting.md`, `llm-fit-coverage.md` |
| Recommendation | Analyze Matches gap-fill (verdicts + pay for jobs still missing them) | `llm-reanalyze-missing.md` |
| Recommendation | Coverage fix — `llm_fraction` applies to the whole analyzed set, not the gap | `analyze-matches-llm-coverage.md` |
| Recommendation | Coverage knob simplification + skill reuse + `compensation_checked` gate | `analyze-matches-coverage-and-rework.md` |
| Recommendation | Cheap rescore on weight/profile change, without re-embedding | `auto-update-match-percent.md` |
| Recommendation | Analyze Matches progress popup (background task + poll) | `analyze-progress-popup.md` |
| Recommendation | Embedder model-load fix (anonymous HF access + persistent cache) | `fix-embedder-model-load.md` |
| LLM | Thinking token budget — bounded reasoning, replacing `disable_thinking` | `thinking-token-budget.md` (supersedes `llm-fit-reasoning-exhaustion.md`) |
| Profile | Blocklists + scoped keyword groups (retroactive hiding) | `profile-blocklists.md` |
| Profile | Model instructions steering the profile build | `profile-llm-instructions.md` |
| Profile | Skills quick-add from a job's missing-skill chips | `skills-quick-add.md` |
| Scraping | Cumulative "Jobs Found" / "Jobs Saved" across iterations | `cumulative-scrape-counts.md` |
| Scraping | Max results 100 + up to 5 offset iterations | `find-jobs-iterations.md` |
| Scraping | Shared description enrichment (compensation + industry in one pass, two callers) | `job-card-rows-and-shared-enrichment.md` |
| Scraping | LLM-gated daily search under systemd | `systemd-daily-search.md` |
| Documents | Agentic documents: data foundation, generation graphs, Application Mode, LaTeX + PDF | `agentic-documents-{system,foundation,graphs,application-mode}.md` |
| Documents | Cover-letter Winning Formula as structured output | `cover-letter-skill-structure.md` |
| Documents | Flow smoothing — audit and rewrite asserted fit into shown fit | `cover-letter-flow-smoothing.md` |
| Documents | Profile sidebar collapsed to Candidate ∣ Guidance; one editable Document Guidance | `documents-sidebar-simplify.md` |
| UI | New Jobs "Filter" button — re-apply keyword filter + block rules to the visible feed | `new-jobs-filter-button.md` |
| UI | Job card redesign — row layout, industry pills, icon action row | `job-card-redesign.md`, `job-card-rows-and-shared-enrichment.md` |
| UI | Saved lane + saved jobs exempt from auto-hide | `save-jobs.md`, `saved-jobs-not-auto-hidden.md` |
| UI | Tracker: search, a distinct Rejected column, slim cards, durable pipeline dates | `tracker-search-rejected.md`, `tracker-cards-and-pipeline-dates.md` |
| UI | Per-page search + Saved sort (Newest ∣ Match) | `jobs-search-and-saved-sort.md` |
| UI | Logo-derived `arctic` / `midnight` themes + header toggle | `logo-color-themes-and-toggle.md` |
| UI | Hover and movement animations across every surface | `ui-hover-animations.md` |
| UI | Recommendation-era UI refinements (match breakdown, résumé drop zone, activity feed) | `ui-recommendation-refinements.md` |
| UI | Frontend redesign wired to the API (the current single-page export) | `2026-06-30-frontend-redesign-wiring.md` |
| Platform | Shared data root across worktrees (fixed the vanishing-profile bug) | `shared-data-root.md` |
| Platform | Scoped database clear (full ∣ jobs only) | `clear-db-options.md` |
| Docs | `docs/` established as the single source of truth; skills + pointers | `2026-06-30-skills-and-docs-initialization.md` |
| Docs | Documentation purge and rewrite (this pass) | `documentation-purge-and-rewrite.md` |

## Conventions

- A feature is not done until its docs are updated in the same change (`docs/workflow.md`).
- Retained on purpose: `requirements.txt` as a legacy mirror of `pyproject.toml`, and `main.py`
  (the `uv` default stub).
