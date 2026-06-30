# Plan: RAG + LLM Job Recommendation Overhaul

## Context

Magnification today scrapes jobs into SQLite and shows them in a New Jobs grid / Tracker
kanban (single-file `index.html` driven by a vendored `dc-runtime.js`). It has a heavy,
wine-based local-LLM subsystem (`utils/LocalLLM`) and no notion of a user *profile* or any
relevance ranking — every scraped job is shown flat, filtered only by literal substring
keyword matching.

The user wants to turn it into a **recommendation system**: build a reusable **profile**
from the user's resume (interests paragraph, skill list, search-title list, and grouped
AND/OR keyword preferences); embed every scraped job's description on retrieval with
**bge-small-en-v1.5** (CPU, parallel) + **BM25**; score each job against the profile; and
layer an **LLM pass** (via a configurable OpenAI-compatible endpoint) on the top candidates
for a final verdict + rationale. The UI gains a **Profile** menu (left of Find Jobs) and an
**Options** menu (right of Find Jobs, with separate LLM-endpoint and runtime tabs), and
Find Jobs gains multi-select countries, a job-type filter, and LLM-assisted keyword
generation. Everything that can be parallelized (embedding, LinkedIn description fetch, LLM
queries) is parallelized with configurable worker counts.

Confirmed decisions: **fastembed (ONNX, no PyTorch)** for embeddings; a single **generic
OpenAI-compatible endpoint** (base_url + api_key + model) for all AI features; recommendations
surface as a **per-job match score + detail breakdown** (not a separate report view); delivered
in **independently-committable phases** from a worktree, merged to `main` at the end.

---

## Gaps & Unanswered Questions

- **Dependency install safety** — the venv is fragile (`regex` won't build offline; uv.lock
  broken on 3.14). *Resolved in Phase 1*: deps installed as binary wheels via
  `uv pip install --only-binary=:all: fastembed rank-bm25 pypdf requests` into the existing
  3.12 venv; `pyproject.toml` declares them but `uv.lock` is left untouched. The bge model
  (~130 MB) downloads from HuggingFace on first embed (one-time network requirement).
- **dc-runtime extensibility** — `index.html` is a single design-tool export (876 lines, already
  over the 800-line cap) with the component class inline in a `<script type="text/x-dc">` block.
  *Assumption*: verify during Phase 3 whether dc-runtime accepts an external `type="text/x-dc"`
  src; if yes, split the component logic into `static/js/component.js`; if not, accept the
  size overage for this generated file and document the exception in `structure.md`.
- **Skill extraction method** — "rapid" skill extraction. *Assumption*: default to a fast,
  deterministic **gazetteer matcher** (the profile's own skills + a seeded base tech-skill list,
  normalized substring/phrase match) so matching needs no LLM/network; expose an optional LLM
  extraction path for richer skills, gated by the runtime config.
- **Keyword-group semantics** — *Assumption*: reuse the existing `job_filter` convention —
  **AND across groups, OR within a group** (`[{label, terms:[...]}, ...]`). A job satisfies the
  preference if every group has at least one matching term.
- **Profile multiplicity** — *Assumption*: support multiple named profiles with one `is_active`,
  but the UI ships a single "default" profile; the schema leaves room to add more later.
- **Re-analysis on profile change** — *Assumption*: `JobAnalysis` stores which `profile_id` it
  was computed against; changing the active profile offers a "re-analyze" action rather than
  auto-recomputing everything.

---

## Architecture Summary

**New backend packages**
- `utils/backend/llm/` — `client.py`: thin `OpenAIClient(base_url, api_key, model, …)` over
  `requests` with `chat()`, `chat_json()` (structured output), and `chat_many()` (parallel via
  `ThreadPoolExecutor`); `config.py`: load/save the endpoint config file.
- `utils/backend/recommend/` — `embedder.py` (fastembed `TextEmbedding("BAAI/bge-small-en-v1.5")`,
  lazy singleton, batch+parallel), `bm25.py` (rank_bm25 index + tokenizer), `skills.py` (gazetteer
  + optional LLM extraction), `profile_builder.py` (resume text extraction + LLM→profile JSON),
  `ranker.py` (hybrid semantic+BM25+keyword-group+skill scoring → suggestions report; optional
  LLM verdict on top-N), `service.py` (orchestrates embed-on-retrieve + analysis, parallelized).

**New DB tables** (separate tables → `Base.metadata.create_all()` is sufficient, no destructive
migration): `Profile` (interests_paragraph, skills JSON, job_titles JSON, keyword_groups JSON,
resume_text, is_active) and `JobAnalysis` (1:1 with Job: embedding BLOB, extracted_skills JSON,
semantic_score, bm25_score, keyword_group_hits JSON, skill_match JSON, rag_score, llm_score,
llm_rationale, profile_id FK, analyzed_at).

**New routes**: `profile_bp` (`/api/profile*`), `options_bp` (`/api/options/llm*`,
`/api/options/runtime`), `recommend_bp` (`/api/recommend/analyze`, `/api/recommend/report`,
`/api/recommend/keywords`). `GET /api/jobs` extended with an opt-in `with_analysis` projection.

**Config files** (gitignored): `llm_endpoint_config.json` (base_url, api_key, model, temperature,
max_tokens, timeout, enabled) and `runtime_config.json` (worker counts + analysis toggles).

**Parallelism**: refactor `linkedin_scraper.fetch_descriptions_for_jobs()` from sequential→
`ThreadPoolExecutor` with jittered rate-limit; fastembed batch+`parallel`; `chat_many()` for LLM.
All worker counts read from `runtime_config.json`.

**Frontend** (`index.html` + `dc-runtime.js`): add Profile button (left of Find Jobs) + Options
button (right) in the header nav cluster; add `profileOpen`/`optionsOpen` state + slide-over
panels (mirroring the detail-panel pattern); Options has two tabs (LLM Endpoint / Runtime); New
Jobs cards get a match-score badge + sort-by-match; detail panel gets a skill-match / keyword-hit
/ LLM-rationale breakdown; Find Jobs gains multi-select countries, job-type select, and a
"Generate keywords (LLM)" button.

---

## Hierarchical Step-by-Step Instructions

### Step 0: Worktree + Dependencies + Plan  → commit "RAG/LLM Overhaul (1/7)"
- **Locations**: git worktree off `main`; `pyproject.toml`; `docs/plans/rag-llm-recommendation.md`;
  `docs/workflow.md`; dev-env memory.
- **Actions**: create the worktree; install deps as binary wheels; confirm `import app`.

### Step 1: Data Model — Profile & JobAnalysis  → commit "RAG/LLM Overhaul (2/7)"
- **Locations**: `utils/backend/database/models.py`, `operations.py`, `init_db.py`,
  `docs/database.md`, `docs/structure.md`. Separate tables keep `Job` and existing queries intact.

### Step 2: OpenAI-Compatible LLM Client + Options Config & Routes  → commit "RAG/LLM Overhaul (3/7)"
- **Locations**: `utils/backend/llm/client.py`, `llm/config.py`,
  `utils/backend/recommend/runtime_config.py`, `utils/backend/routes/options_routes.py`, `app.py`,
  `docs/routes.md`, `docs/api-contract.md`, `docs/data-flow.md`.

### Step 3: Profile Builder + Profile API + Profile UI  → commit "RAG/LLM Overhaul (4/7)"
- **Locations**: `utils/backend/recommend/profile_builder.py`,
  `utils/backend/routes/profile_routes.py`, `app.py`, `index.html`, `docs/profile.md`,
  `docs/component-map.md`, `docs/routes.md`, `docs/api-contract.md`.

### Step 4: Skill Extraction + Parallelism Refactors  → commit "RAG/LLM Overhaul (5/7)"
- **Locations**: `utils/backend/recommend/skills.py`,
  `utils/backend/scrapers/linkedin_scraper.py`, `scrapers/scraper_config.py`,
  `docs/job_scraping.md`, `docs/data-flow.md`.

### Step 5: RAG Ranking + Embed-on-Retrieve + Recommendation UI  → commit "RAG/LLM Overhaul (6/7)"
- **Locations**: `utils/backend/recommend/embedder.py`, `bm25.py`, `ranker.py`, `service.py`;
  `utils/backend/scrapers/scraping_service.py`; `utils/backend/routes/recommend_routes.py`;
  `routes/job_routes.py`; `app.py`; `index.html`; `docs/recommendation.md`, `docs/data-flow.md`,
  `docs/design-system.md`, `docs/routes.md`, `docs/api-contract.md`.

### Step 6: LLM Recommendation, Keyword Generation, Find-Jobs Upgrades + Merge  → commit "RAG/LLM Overhaul (7/7)"
- **Locations**: `recommend/ranker.py`, `recommend_routes.py`, `scrapers/task_generator.py`,
  `jobspy_wrapper.py`, `routes/config_routes.py`, `jobs_config.json` schema, `index.html`,
  `docs/find_jobs.md`, `docs/api-contract.md`, `docs/documentation.md`, `docs/checklist.md`.
  Finally: merge worktree → `main`, resolve conflicts.

Each step ends with: run the phase's tests + `import app`, then commit
`RAG/LLM Overhaul (<n>/7) Complete: <summary>`.

---

## Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| LLM client | OpenAI-compatible client w/ parallel `chat_many` | `utils/backend/llm/client.py` |
| LLM/runtime config | Endpoint + worker/toggle config load/save | `utils/backend/llm/config.py`, `utils/backend/recommend/runtime_config.py` |
| Embedder | fastembed bge-small-en-v1.5 batch/parallel singleton | `utils/backend/recommend/embedder.py` |
| BM25 index | rank_bm25 index + tokenizer | `utils/backend/recommend/bm25.py` |
| Skill extractor | Gazetteer (+optional LLM) skill extraction | `utils/backend/recommend/skills.py` |
| Profile builder | Resume (pdf/tex/md) → profile JSON via LLM | `utils/backend/recommend/profile_builder.py` |
| Hybrid ranker | semantic+BM25+keyword+skill (+LLM) scoring | `utils/backend/recommend/ranker.py` |
| Recommend service | Embed-on-retrieve + analysis orchestration (parallel) | `utils/backend/recommend/service.py` |
| DB models | `Profile`, `JobAnalysis` + CRUD | `utils/backend/database/models.py`, `operations.py` |
| Profile API | `/api/profile*` blueprint | `utils/backend/routes/profile_routes.py` |
| Options API | `/api/options/llm*`, `/api/options/runtime` | `utils/backend/routes/options_routes.py` |
| Recommend API | `/api/recommend/{analyze,report,keywords}` | `utils/backend/routes/recommend_routes.py` |
| Parallel LinkedIn fetch | ThreadPoolExecutor + rate-limit refactor | `utils/backend/scrapers/linkedin_scraper.py` |
| Frontend Profile/Options/scores | Header menus, panels, match UI, Find-Jobs upgrades | `utils/frontend/templates/index.html` (+ optional `static/js/component.js`) |
| Embedder test | dims + similarity (skipped offline if model absent) | `tests/recommend/test_embedder.py` |
| BM25 test | deterministic ranking order | `tests/recommend/test_bm25.py` |
| Skills test | gazetteer extraction + profile match | `tests/recommend/test_skills.py` |
| Keyword-group test | AND-across / OR-within semantics | `tests/recommend/test_keyword_groups.py` |
| Ranker test | hybrid score w/ fake embedder + fake LLM | `tests/recommend/test_ranker.py` |
| LLM client test | request shape + parallel fan-out (mocked) | `tests/llm/test_client.py` |
| Resume parse test | `.md`/`.tex` extraction; PDF if sample present | `tests/profile/test_resume_parse.py` |
| Wiring tests | new blueprints registered + routes resolve | `tests/test_wiring.py` (extend existing) |
| Docs | new `recommendation.md`, `profile.md`; updates across `docs/` | `docs/*` |

---

## Verification (end-to-end)

1. **Per-phase**: `pytest tests/<area>` for the phase's new tests; `import app` after every
   backend change.
2. **LLM-dependent paths** run against a **mock OpenAI endpoint** (monkeypatched client) so tests
   need no network/keys; the embedder test skips if the bge model isn't cached.
3. **UI verification** via the preview tools: Profile → upload a sample `.md` resume → editable
   draft → save; Options → set a mock endpoint + runtime workers → Test connection; Find Jobs with
   multi-country + job-type → New Jobs shows match badges, sortable; open a job → detail panel
   shows skill-match, keyword-group hits, and LLM rationale.
4. **Full gate before merge**: complete `pytest` green, app imports, a manual
   profile→scrape→analyze→suggestions pass; then merge the worktree to `main` and re-run the gate.
