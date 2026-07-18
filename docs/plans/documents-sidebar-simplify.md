# Profile Sidebar Simplification + Editable Document Guidance

Plan owner: agent · Branch: `docs-sidebar-simplify` (worktree
`.claude/worktrees/docs-sidebar-simplify`). Builds on the just-merged cover-letter skill
(`docs/plans/cover-letter-skill-structure.md`).

## 1. Introduction

The "Profile & Documents" sidebar currently has four tabs — **Candidate**, **Behavioral**,
**Writing**, **Templates**. Now that a structured cover-letter skill drives generation, the three
document tabs add complexity without carrying their weight: Behavioral fed the strategist, Writing
fed the voice pass, and Templates supplied the letter/résumé slot skeletons — all of which the
skill + built-in defaults now cover. The user wants these three collapsed into a **single, cleaner
tab** whose job is to **edit the one guidance document** that steers both cover-letter and résumé
generation.

The approach: (a) turn the previously hard-coded skill into a **single, editable, persisted
"Document Guidance" document** (one shared doc for both kinds) that is injected into every
generation and every refine at call time; (b) **fully remove** the Behavioral, Writing, and
Templates subsystems — UI tabs, backend routes, DB models/CRUD, seeding, the now-orphaned ingestion
upload pipeline, and the graph plumbing that consumed them; (c) replace the three tabs with one
**Guidance** tab (a textarea + Save + Reset-to-default). Both generation graphs already fall back to
built-in document bodies (`_DEFAULT_LETTER_BODY`, `_DEFAULT_RESUME_BODY`) and treat behavioral/
writing as optional, so removing the subsystems does not break generation.

The phases are ordered so the app stays importable and the offline test subset stays green after
each one. Steps are interdependent (frontend depends on the new route; graph rewiring depends on the
guidance store; the removal touches shared files), so this is implemented sequentially rather than
fanned out to parallel subagents; a read-only Explore subagent already produced the full reference
map this plan is built on.

## 2. Gaps & Unanswered Questions

- **Removal depth** — *Resolved by the user:* **full removal** (UI + backend + DB models/CRUD +
  seeding + graph usage), not a UI-only hide.
- **Guidance scope** — *Resolved by the user:* **one shared editable document** injected into both
  the cover-letter and résumé graphs.
- **Ingestion / uploaded-documents pipeline.** The `/api/documents/ingest`, `/ingest/save`, and
  `/uploaded` routes + the `utils/backend/agents/ingestion` agent + the `uploaded_documents` table
  exist **only** to turn an uploaded file into a Behavioral/Writing draft; their only UI callers are
  the Behavioral/Writing panels (the Candidate tab uses the separate résumé→profile builder).
  *Assumption:* removing the three tabs orphans this pipeline, so under "full removal" it is removed
  too (routes, agent package, model, CRUD, and the "Recent uploads" trace). Called out explicitly in
  the Phase-4 commit so it is easy to see and revert if unwanted.
- **Physical SQLite tables.** Removing the ORM models stops new installs from creating
  `behavioral_profiles` / `writing_style_profiles` / `document_templates` / `uploaded_documents`,
  but existing DB files keep those tables as harmless orphans. *Assumption:* we do **not** add a
  destructive `DROP TABLE` migration — the feature is gone from the app; leaving inert tables avoids
  irreversible data loss and is non-destructive.
- **Job-evaluation seed.** The `_EVAL_RUBRIC` seed lives in `seed_documents.py` (deleted here), but
  it is never read by the graph (`evaluate_fit` uses `EVALUATE_FIT_PROMPT`, and the `JobEvaluation`
  table is written per-job at run time). *Assumption:* safe to drop the seed; the `JobEvaluation`
  table and its ops stay.
- **Guidance persistence location.** Stored as a gitignored `config/document_guidance.json` resolved
  through `utils/backend/paths.get_project_root()` (the same shared-root rule as the other
  `config/*.json`). The hard-coded default is the reset baseline.
- **Verification hazard.** Per the shared-config rule, verification must not clobber the user's real
  guidance: unit tests use an isolated temp config path, and any live PUT during preview verification
  is snapshot/restored (or avoided).
- **Commit, not push.** Each phase is committed to git and **not** pushed.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Plan doc + worktree
- **Locations**: `docs/plans/documents-sidebar-simplify.md`; worktree
  `.claude/worktrees/docs-sidebar-simplify` on branch `docs-sidebar-simplify`.
- **Rationale**: Isolated branch + a written plan before touching shared files.
- **Action**: Confirm the plan reads cleanly and the existing agent/document tests run green in the
  worktree. Commit: `Docs Sidebar Simplify (1/7) Complete: plan doc + worktree + resolved forks`.

### Step 2: Editable guidance store + API (additive)
- **Locations**: new `utils/backend/agents/document_guidance.py` (`DEFAULT_GUIDANCE` — one shared doc
  with a COVER LETTER section = the Winning Formula + writing rules, and a RÉSUMÉ section = truth-
  preserving tailoring principles; `default_guidance()`, `get_guidance()`, `set_guidance()`,
  `reset_guidance()`, `is_default()`; config at `config/document_guidance.json` via `paths`); new
  `utils/backend/routes/guidance_routes.py` (`GET`/`PUT /api/document-guidance`,
  `POST /api/document-guidance/reset`) registered in `app.py`; tests
  `tests/agents/test_document_guidance.py` + a guidance-route test in `tests/documents/`.
- **Rationale**: Stand up the new single source of truth and its API first, without removing
  anything, so the graph and UI can adopt it in later phases.
- **Action**: Unit-test default/override/reset against an isolated temp config; route GET/PUT/reset
  round-trip on the test client. `import app` clean. Commit: `Docs Sidebar Simplify (2/7) Complete:
  editable shared Document Guidance store + /api/document-guidance API + tests`.

### Step 3: Rewire both graphs to the editable guidance; drop behavioral/writing/template plumbing
- **Locations**: `utils/backend/agents/prompts.py` (remove the `cover_letter_skill` import + baked
  `_HOUSE_STYLE`; keep base anti-parrot/stated-interests rules); delete
  `utils/backend/agents/cover_letter_skill.py`; `utils/backend/agents/context.py` (drop
  behavioral/writing/template loads + `_TEMPLATE_KIND` + `template_id`; add
  `state["guidance"]=document_guidance.get_guidance()`); `utils/backend/agents/nodes_shared.py`
  (add a `with_guidance(system, state)` helper); `utils/backend/agents/nodes_cover_letter.py`
  (strategize drops behavioral, write always uses `_DEFAULT_LETTER_BODY`, style drops writing → default
  voice, all LLM nodes prepend the guidance); `utils/backend/agents/nodes_resume.py` (ats_format always
  `_DEFAULT_RESUME_BODY`; plan/rewrite prepend guidance); `utils/backend/agents/service.py` +
  `utils/backend/routes/document_generation_routes.py` (drop `template_id`); update
  `tests/agents/test_cover_letter_graph.py`, `test_cover_letter_quality.py`, `test_resume_graph.py`,
  `test_refine.py` to stop seeding/relying on behavioral/writing/templates and to assert the guidance
  reaches the writer on a first pass **and** a refine.
- **Rationale**: The editable guidance must be injected at call time (not baked at import) so a user
  edit takes effect immediately; both graphs then need no template/behavioral/writing state.
- **Action**: Run `tests/agents`; both first-pass and refine route the guidance into the writer.
  `import app` clean. Commit: `Docs Sidebar Simplify (3/7) Complete: graphs consume the editable
  guidance; behavioral/writing/template graph plumbing removed`.

### Step 4: Remove the backend subsystems (routes, DB, seeding, ingestion)
- **Locations**: `utils/backend/routes/documents_routes.py` (remove behavioral/writing/template +
  ingest/ingest-save/uploaded routes; keep job-evaluation + generated-documents list);
  `utils/backend/database/models.py` (delete `BehavioralProfile`, `WritingStyleProfile`,
  `DocumentTemplate`, `UploadedDocument`); `utils/backend/database/documents_ops.py` (delete their CRUD
  + serializers + helpers); `utils/backend/database/__init__.py` (drop the exports);
  delete `utils/backend/database/seed_documents.py` + remove `_seed_documents()` from
  `utils/backend/database/init_db.py`; delete `utils/backend/agents/ingestion/`; trim
  `tests/documents/test_documents_api.py` + `tests/agents/test_ingestion.py` (delete) +
  `tests/database/test_agentic_documents.py` (trim to surviving tables).
- **Rationale**: With the graph and UI no longer using them, the subsystems are dead code; the
  cleanup rule requires removing them rather than leaving competing/orphaned surfaces.
- **Action**: Offline `tests/agents`, `tests/documents`, `tests/database` green; `import app` clean;
  no route collisions. Commit: `Docs Sidebar Simplify (4/7) Complete: removed behavioral/writing/
  template + orphaned ingestion backend (models, CRUD, routes, seeding)`.

### Step 5: Frontend — collapse to Candidate | Guidance
- **Locations**: `utils/frontend/templates/index.html` — remove the Behavioral/Writing/Templates tab
  buttons (526–528), their three `sc-if` panels (660–800), the JS methods (`loadDocuments` fetches,
  `loadTemplates`, `loadUploadedDocs`, `behSet`/`wriSet`, `onBehFile`/`onWriFile`, `ingestDoc`,
  `saveBehavioral`, `saveWriting`, `tplSet`/`addTemplate`/`saveTemplate`/`deleteTemplate`), the
  related state keys (1512–1517), and the render getters (2539–2544, 2711–2746); add a **Guidance**
  tab (textarea bound to the guidance doc + Save + Reset-to-default + status) with
  `loadGuidance`/`saveGuidance`/`resetGuidance` and its state/getters; update
  `tests/test_frontend_wiring.py` tokens.
- **Rationale**: Deliver the cleaner two-tab sidebar the user asked for and expose the editable
  guidance.
- **Action**: Verify live on the preview (tabs render as Candidate | Guidance; the guidance loads,
  edits save + persist, Reset restores the default; no console errors) — snapshot/restore the real
  guidance config around any live save. `import app` clean; wiring test green. Commit: `Docs Sidebar
  Simplify (5/7) Complete: sidebar collapsed to Candidate | Guidance with an editable guidance doc`.

### Step 6: Documentation + full offline validation
- **Locations**: `docs/routes.md`, `docs/api-contract.md`, `docs/component-map.md`,
  `docs/database.md`, `docs/data-flow.md`, `docs/documentation.md`, `docs/structure.md`,
  `docs/checklist.md` (new DoD), and the affected `docs/plans/agentic-documents-*.md` notes.
- **Rationale**: Docs move with the code in the same change (global rules).
- **Action**: Offline `tests/agents` + `tests/documents` + `tests/database` +
  `tests/test_frontend_wiring.py` + `tests/docs` green; `import app` clean. Commit: `Docs Sidebar
  Simplify (6/7) Complete: docs updated + full offline validation`.

### Step 7: Merge to main
- **Locations**: branch `docs-sidebar-simplify` → `main`; remove the worktree.
- **Rationale**: Deliver on the main line (no push).
- **Action**: Merge, re-run the offline subset + `import app` on `main`, resolve conflicts. Commit
  the merge: `Docs Sidebar Simplify (7/7) Complete: merged to main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan document | This staged plan | `docs/plans/documents-sidebar-simplify.md` |
| Guidance store | Editable, persisted single shared guidance doc + default/reset | `utils/backend/agents/document_guidance.py` |
| Guidance API | GET/PUT/reset endpoints | `utils/backend/routes/guidance_routes.py`, `app.py` |
| Graph rewiring | Both graphs inject the editable guidance; template/behavioral/writing dropped | `agents/context.py`, `nodes_shared.py`, `nodes_cover_letter.py`, `nodes_resume.py`, `prompts.py`, `service.py` |
| Backend removal | Routes, models, CRUD, seeding, ingestion package removed | `routes/documents_routes.py`, `database/models.py`, `database/documents_ops.py`, `database/__init__.py`, `database/init_db.py`, delete `database/seed_documents.py`, delete `agents/ingestion/` |
| Frontend | Sidebar collapsed to Candidate \| Guidance with an editable guidance textarea | `utils/frontend/templates/index.html` |
| Guidance tests | Store + API round-trip; guidance reaches writer on first pass + refine | `tests/agents/test_document_guidance.py`, `tests/documents/`, `tests/agents/test_cover_letter_quality.py` |
| Test trims | Remove behavioral/writing/template/ingestion tests; update wiring tokens | `tests/documents/test_documents_api.py`, delete `tests/agents/test_ingestion.py`, `tests/database/test_agentic_documents.py`, `tests/test_frontend_wiring.py` |
| Docs update | Routes, API, component-map, database, data-flow, documentation, structure, checklist | `docs/*.md` |
