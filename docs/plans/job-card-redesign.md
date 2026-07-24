# Job Card Redesign — Industry Detection + Row-Based Layout

Branch: `job-card-redesign` (worktree `../Magnification-jobcard`). Commit per phase; merge to
`main`; remove the worktree.

## Requirements (user)

Reroute/restructure the New Jobs (and Saved) job cards to be more detailed.

**Feature 1 — Industry extraction.** Detect each job's industry/genre (Health, Industrial,
Finance, Business, Tech, …). Pull it from the description **in the same LLM pass that already
extracts compensation**, since both come from the description in one shot.

**Feature 2 — Row-based card layout**, top → bottom:
1. Source pill (left) + retrieved date.
2. Industry pill (left), styled like the location pill but with a **unique, consistent color per
   industry** (neon/distinct; all "Health" share one color, etc.).
3. Job title (fills remaining width) + Match % + "?" breakdown button (both fixed-width).
4. Company name.
5. Location + compensation.
6. Description — truncated to max 3 lines, ellipsis.
7. Primary actions: keep the **Generate** (renamed from "Apply") / **Applied** pair.
8. Icon action buttons (SVG): Info (details), Block company, Hide, Save, Link out.

## Key design decisions

- **Industry coverage (fork resolved → every job).** The requirement says "categorize **each**
  job," so industry is not limited to no-pay jobs. The current compensation pass only runs for
  jobs missing pay (`needs_compensation`). We generalize the pass to an **enrichment** pass that
  runs for jobs needing **either** compensation **or** industry, and the single LLM call returns
  both fields. A job needing both is still one call ("single pass"). A `jobs.industry_checked`
  flag (mirroring `compensation_checked`) stops re-querying jobs the model already classified.
- **Fixed industry taxonomy = source of truth for colors.** The LLM must classify into one of a
  fixed label set so the frontend can map label → color deterministically and consistently.
  Canonical set (backend `INDUSTRIES`): Tech, Health, Finance, Business, Industrial, Science,
  Education, Government, Retail, Media, Legal, Energy, Other. Unknown/blank → Other.
- **Gating.** Industry recovery reuses the LLM-enabled check and a new `enable_llm_industry`
  runtime default (True), independent of `enable_llm_compensation` so industry still fills when
  pay extraction is off. When both toggles are on, one combined call serves both.
- **Icon row replaces the current mixed text/icon actions.** Row 7 keeps Generate/Applied text
  buttons; Row 8 becomes five icon-only buttons (Info, Block, Hide, Save, Link).
- **Both New Jobs and Saved grids** use the same `job.*` view-model, so the markup change is made
  in both `sc-for` blocks; the detail panel keeps its existing controls (add industry line).

## Phases

### (1/7) Plan doc + worktree — this file.

### (2/7) Backend: industry storage + combined enrichment extraction
- `models.py`: `Job.industry = Column(String(64))` + `industry_checked = Column(Integer, default=0)`;
  docstring.
- `migrate_job_industry.py` (idempotent ALTER TABLE add both columns) wired into `_run_migrations`.
- `_job_to_dict`: expose `industry` + `industry_checked`.
- `compensation.py` → extend to combined enrichment: `INDUSTRIES` list, a combined prompt that
  returns `{"compensation": …|null, "industry": <one label>|null}`, `_parse_industry`,
  `extract_enrichment_llm(jobs, client, comp=True, industry=True, …)` mutating job dicts and
  returning `(comp_count, industry_count)`; `needs_industry(job)` + `needs_industry_recovery(job,
  force)` + `needs_enrichment(job, comp_on, industry_on, force)`. Keep `extract_compensation_llm`
  / `needs_compensation*` as-is (back-compat for existing tests + callers).
- `runtime_config.py`: add `enable_llm_industry: True`.
- Tests (`tests/recommend/test_industry.py`): predicates, taxonomy normalization (unknown→Other),
  combined extraction fills both, `industry_checked` semantics.

### (3/7) Wire enrichment into the two pipelines
- `recommend/service.py`: generalize `_recover_compensation` → `_recover_enrichment` (persists
  `compensation`/`compensation_checked` + `industry`/`industry_checked`, each gated by its toggle);
  keep the summary key `compensation_extracted` and add `industry_extracted`; progress copy.
- `scrapers/scraping_service.py`: the post-scrape compensation block also captures industry via the
  combined extractor and persists it.
- Extend/adjust `tests/recommend/test_analyze_gapfill.py` + `tests/scrapers/test_scraping_service_order.py`
  as needed (keep them green).

### (4/7) Frontend: row-based card + industry pill + icon action row
- `mapDbJob`: carry `industry` through.
- `decorate`: `industryLabel` + `industryBadge` (per-industry color via an `INDUSTRY_COLORS` map;
  Other→muted), and per-icon button styles for the new Row 8 (info/block/hide/save/link). `onOpen`
  already exists for Info; `onLink` exists.
- Rewrite both New Jobs + Saved `<article>` blocks to the 8-row structure. Row 3 uses
  flex with the title `flex:1;min-width:0` and the match badge + "?" `flex:0 0 auto`. Rename the
  Generate button label; move Details→icon (Info), keep Block/Hide(ignore)/Save/Link as icons.
- Detail panel: add an Industry line near Location/Compensation.

### (5/7) Frontend wiring test + live verification
- `tests/test_frontend_wiring.py`: assert the card exposes `job.industryBadge`/`industryLabel`,
  the "Generate" label, and the five icon buttons; industry pill present.
- Live-verify via the served page/DOM (Browser pane compositing is unavailable here — verify via
  served HTML + `/api/jobs` `industry` field, per prior UI work).

### (6/7) Docs
- `database.md` (industry columns), `api-contract.md` (`industry` field + runtime key),
  `data-flow.md` (enrichment pass), `component-map.md` + `design-system.md` (card rows + industry
  color tokens), `recommendation.md` (combined extraction), `structure.md` if needed, `documentation.md`
  status, this checklist entry in `docs/checklist.md`.

### (7/7) Validate, merge, clean up
- Offline subsets green (`tests/recommend`, `tests/database`, `tests/scrapers`,
  `tests/test_frontend_wiring.py`), `import app` clean, migration verified on the real DB.
- Merge to `main`; remove the worktree.
