# Plan — Agentic Documents, Part 2: the per-job generation graphs

**Status:** Implementation plan (executes against the `agentic-documents-foundation` branch).
**Scope:** Build-order steps **§8.3 (Cover Letter graph)** and **§8.4 (Résumé fine-tuner graph)**
of [agentic-documents-system.md](agentic-documents-system.md) — the two per-job "Agentic Processes".
**Out of scope (deferred):** Application Mode (§4 / build-step 5) and the browser-automation adapter
(§4.3 / build-step 6). Those remain the "Goliath" the user flagged for a later session.

**Orchestration:** an **in-house, plain-Python orchestrator** (no LangGraph — a standing decision from
Part 1). Node structure and checkpoint/interrupt semantics from the design are preserved with an
explicit node pipeline, an in-memory task store (mirroring `recommend_routes.analyze_tasks`), a
`threading.Event`-based checkpoint pause/resume, and a persisted `generated_documents.checkpoint_state`
snapshot. Zero new dependencies.

---

## Introduction

Part 1 (the foundation) landed the data layer, the ingestion agent, and the Profile & Documents sidebar.
This part adds the two generation graphs that turn a `job_id` + the active Profile/Behavioral/WritingStyle
records into a tailored **cover letter** and a **fine-tuned résumé**, persisting each to
`generated_documents`. Both key off data already in the DB (the "ingestion is a DB read" insight, §0):
the scrape+analyze pipeline has already stored the JD, `JobAnalysis.skill_match`, keyword hits, and the
LLM fit rationale, so context-gathering is free.

The differentiated piece is the résumé Critic: it builds a **throwaway profile** from the tailored résumé
text and reuses Magnification's own recommender (`recommend/ranker.py`) against the single target job to
produce an objective **match-lift** (before → after) that is both the stop criterion and the headline UI
metric. This works offline: `bm25 + keyword + skill` are pure-Python, and the combine step renormalizes
over whichever signals are present, so a real (lexical/skill) lift is measurable even when the embedding
model is uncached; when embeddings are available, the semantic signal folds in too. Both before and after
use the same available signal set, so the lift is apples-to-apples.

Every node degrades gracefully when no LLM endpoint is configured (the same contract as the ingestion
agent and résumé builder): it produces a deterministic, user-editable fallback and sets `llm_used=False`,
so the whole graph always completes and the offline test-suite exercises it end-to-end.

## Gaps & unanswered questions (resolved for this build)

- **Company research source** (open-Q §9): **LLM-only** for now (no web node). Fallback derives an angle
  from the JD text + company name. A web-search node is a clean drop-in later.
- **Résumé output format** (open-Q §9): **Markdown first**, into the seeded `ATS Skeleton` template. LaTeX/PDF
  compile-loop deferred.
- **Writing-style bootstrap** (open-Q §9): use the active `writing_style_profiles` row (seeded on day one);
  if absent, infer light defaults — never hard-fail.
- **Checkpoints:** implemented but **opt-in** via an `interactive` flag (default `false` → runs end-to-end,
  auto-approving the angle/plan). Checkpoint 2 (safety) surfaces as a `needs_review` flag on the finished
  draft rather than a hard block, so the happy path and the tests never hang. When `interactive=true`,
  Checkpoint 1 pauses the background thread until the `/resume` route delivers a decision.
- **Match-lift signal set:** the LLM fit *verdict* is intentionally **excluded** from the match-lift score
  (it is expensive and noisy to re-issue per revision); the lift is computed over `{semantic?, bm25,
  keyword, skill}`. Documented in `scoring.py`.

---

## Steps

### Step 1 — Plan doc + worktree check-in (this file)
- Write this plan; confirm we are on the `agentic-documents-foundation` branch continuing the feature.
- **Validation:** `git status` clean after commit; plan committed.
- **Commit:** `Agentic Graphs (1/6): plan for the per-job cover-letter + résumé graphs`.

### Step 2 — Orchestrator + shared context loader + match-lift scoring
- `agents/orchestrator.py` — `Orchestrator` (progress `report`, `checkpoint(name, payload)` →
  auto-approve when no `resume_fn`), `Checkpoint` dataclass, `MAX_REVISIONS`, thresholds.
- `agents/context.py` — `load_context(job_id, kind, template_id)` → the initial `state` dict
  (job, analysis w/ embedding, active profile/behavioral/writing, chosen template, candidate name/contact).
- `agents/scoring.py` — `score_text_against_job(...)` and `match_lift(...)`: build a throwaway profile from
  résumé text and reuse `ranker.rank_batch` on the one job. Offline-safe.
- `agents/prompts.py` — system prompts + fallback normalizers for every generation node.
- **Validation:** new `tests/agents/test_scoring.py` (throwaway-profile scoring; lift is monotone when JD
  terms are added; offline path returns a float in [0,1]) + `tests/agents/test_orchestrator.py`
  (node order, auto-approve checkpoint, interactive pause/resume via a stub `resume_fn`). Green offline.
- **Commit:** `Agentic Graphs (2/6): in-house orchestrator + context loader + recommender-reuse scoring`.

### Step 3 — Cover Letter graph (System A)
- `agents/nodes_shared.py` — `research_company`, `evaluate_fit` (persists `job_evaluations`, seeded from
  `JobAnalysis.skill_match` + `llm_rationale`), `truthfulness_check`.
- `agents/nodes_cover_letter.py` — `strategize`, `write_letter` (fills template slots), `style_letter`,
  `critique_letter`.
- `agents/cover_letter.py` — the ordered pipeline + revision loop + `needs_review`.
- **Validation:** `tests/agents/test_cover_letter_graph.py` — offline path produces a filled letter and a
  persisted `job_evaluations` row; with a `FakeClient` the LLM path fills slots + loops; interactive
  checkpoint pauses/resumes. Green.
- **Commit:** `Agentic Graphs (3/6): cover-letter graph (research → evaluate → strategize → write → style → critique)`.

### Step 4 — Résumé fine-tuner graph (System B)
- `agents/nodes_resume.py` — `evaluate_gap`, `plan_edits`, `rewrite_resume`, `ats_format`.
- `agents/resume.py` — the ordered pipeline + `score` (match-lift via `scoring.py`) + `truthfulness` +
  revision loop; persists `match_before`/`match_after`.
- **Validation:** `tests/agents/test_resume_graph.py` — offline path fills the ATS skeleton, computes a
  numeric `match_before`/`match_after`, and never fabricates skills absent from the source; the Critic's
  score comes from the real `ranker` on a fixture job. Green.
- **Commit:** `Agentic Graphs (4/6): résumé fine-tuner graph + recommender match-lift`.

### Step 5 — Service + blueprint routes (async task + poll + checkpoint resume)
- `agents/service.py` — the generation task store (`generation_tasks`), `start_generation(kind, ...)`
  (spawns a daemon thread), `get_task`, `resume_task(task_id, decision, edits)`, persistence of the
  finished doc, progress-event streaming. Mirrors `recommend_routes` exactly.
- `routes/document_generation_routes.py` — `generation_bp`:
  `POST /api/documents/cover-letter/start`, `POST /api/documents/resume/start`,
  `GET /api/documents/status/<task_id>`, `POST /api/documents/<task_id>/resume`,
  `GET/PATCH /api/documents/<int:doc_id>`. Register in `app.py`.
- **Validation:** `tests/documents/test_generation_api.py` — start→poll→completed returns a document id;
  résumé result carries `match_before`/`match_after`; PATCH flips `status=approved`; interactive
  start→paused→resume→completed. Green.
- **Commit:** `Agentic Graphs (5/6): generation service + async routes (start/status/resume/approve)`.

### Step 6 — Job-detail "Documents" surface + docs + full validation
- `index.html`: a **Documents** section on the job-detail panel — "Cover Letter" / "Tailor Résumé"
  buttons → start endpoints, reuse the progress-popup pattern, show the result (résumé shows the
  match-lift badge with the recommendation color grading), list prior `generated_documents` with
  view / approve / download. (This is the per-agent surface from §6; the Apply-button Application Mode
  wizard stays deferred.)
- Update `docs/routes.md`, `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`,
  `docs/structure.md`, and `docs/checklist.md` (new "Agentic Documents — Graphs — Definition of Done").
- **Validation:** `tests/test_frontend_wiring.py` (+ generation-surface tokens); full offline suite green;
  `import app` clean; live-verify the surface on the `agentic-docs-ui` preview.
- **Commit:** `Agentic Graphs (6/6): job-detail generation surface + docs + validation`.

---

## Deliverables

| Area | Files |
| --- | --- |
| Orchestrator + shared | `agents/orchestrator.py`, `agents/context.py`, `agents/scoring.py`, `agents/prompts.py` |
| Cover letter | `agents/nodes_shared.py`, `agents/nodes_cover_letter.py`, `agents/cover_letter.py` |
| Résumé | `agents/nodes_resume.py`, `agents/resume.py` |
| Service + routes | `agents/service.py`, `routes/document_generation_routes.py`, `app.py` (register) |
| Frontend | `utils/frontend/templates/index.html` (job-detail Documents surface) |
| Tests | `tests/agents/test_scoring.py`, `test_orchestrator.py`, `test_cover_letter_graph.py`, `test_resume_graph.py`; `tests/documents/test_generation_api.py`; `tests/test_frontend_wiring.py` (+tokens) |
| Docs | `routes.md`, `api-contract.md`, `data-flow.md`, `component-map.md`, `structure.md`, `checklist.md` |

## Non-goals (explicitly deferred)
- Application Mode intake wizard, `application_sessions`, the Apply-button intent/status split (§4).
- Browser-automation / Playwright submission adapter (§4.3).
- Web-search company-research node, LaTeX/PDF résumé compile loop.
