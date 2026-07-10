# Implementation Plan — Agentic Documents (Foundation Phase)

**Scope of this plan:** the *foundation* of the Agentic Document System designed in
[`agentic-documents-system.md`](agentic-documents-system.md) — build-order **§8.1 (data layer)**
and **§8.2 (ingestion agent + Profile & Documents sidebar)** only. The two LangGraph-style agent
graphs (§8.3 cover letter, §8.4 résumé) and **Application Mode (§4 / §8.5) are intentionally
deferred** — Application Mode is dropped from scope entirely for now per the user's direction.

**Branch:** `agentic-documents-foundation` (git worktree under `.claude/worktrees/`).
**Orchestration decision:** a **lightweight in-house orchestrator** (plain Python), *not* LangGraph.
LangGraph was verified to install cleanly but adds ~19 transitive deps to a single-user local app,
and with no LLM endpoint in this environment the agents can only be exercised against a mocked
client either way. The in-house approach preserves the plan's node structure and its
checkpoint/interrupt semantics via the existing DB columns (`generated_documents.checkpoint_state`)
and the app's proven async-task + poll pattern, with **zero new dependencies**.

---

## 1. Introduction

Magnification already turns a résumé into a scored `Profile` and ranks scraped jobs against it. This
plan lays the **data + ingestion foundation** for the larger agentic-document system: DB-backed,
editable *supporting-document* records (behavioral profile, writing style, templates, per-job
evaluations, generated-document outputs) plus a raw-upload store, and a small **ingestion agent**
that generalizes the existing résumé→profile flow to *every* supporting document type
(drag-drop a PDF/tex/md/txt → an LLM summarizes it into the structured record the pipeline needs →
the user reviews/edits → Save).

The approach mirrors Magnification's existing conventions exactly: new SQLAlchemy models in
`models.py` (created by `Base.metadata.create_all`, which adds brand-new tables to fresh *and*
existing DBs, so no column migration is required), a dedicated CRUD module to keep files under the
800-line cap, an idempotent **seed-if-empty** step for the §1.4 starter records, a new blueprint
that reuses the résumé-upload/`OpenAIClient` machinery, and a reorganized Profile slide-over turned
into a tabbed **Profile & Documents** sidebar in the single `index.html` dc-runtime file. Every
piece is validated with the repo's in-memory-DB test-isolation pattern before the app ever touches
the real shared database.

---

## 2. Gaps & Unanswered Questions

- **Orchestration framework** — *Resolved (user):* in-house orchestrator, no LangGraph.
- **Session scope** — *Resolved (user):* foundation only (§8.1 + §8.2); Application Mode dropped;
  check in before building the cover-letter/résumé graphs.
- **Company-research source (§9)** — deferred with the cover-letter graph. *Assumption when built:*
  LLM-only, with a seam for a future web node.
- **Résumé output format (§9)** — deferred with the résumé graph. *Assumption:* Markdown/docx first
  (`document_templates.format` defaults to `markdown`).
- **Writing-style bootstrap (§9)** — *Assumption:* infer style from `resume_text` when no sample is
  uploaded; a real uploaded sample overrides it.
- **Ingestion doc types (§9)** — *Assumption:* a fixed set (`resume | behavioral | writing | reference`)
  **plus** a free `other → summary-only` bucket for anything else.
- **Single vs. multi profile (§9)** — *Assumption:* behavioral / writing-style stay **single-active**
  (mirroring `Profile`); templates are multi-row with a per-kind `is_default`.
- **Job-evaluation rubric (§1.4)** — there is no dedicated rubric table; the seeded rubric is stored
  as a `document_templates` row with `kind="job_evaluation"` so it stays editable in the UI. Per-job
  fit results live in the `job_evaluations` table (1 row per job, upserted, like `JobAnalysis`).
- **`generated_documents` / `application_sessions` tables** — `generated_documents` **is** created now
  (dormant substrate for the deferred graphs, harmless empty table). `application_sessions` is **not**
  created (Application Mode dropped).
- **`cover-letter-agent-design.md` (repo root)** — a superseded earlier cover-letter-only draft, now
  folded into System A of the design doc. Flag for removal/fold when the cover-letter graph is built
  (cleanup rule: no competing sources of truth).

---

## 3. Hierarchical Step-by-Step Instructions

> Per repo convention each phase is committed (not pushed) with the message
> `Agentic Documents Foundation (<n>/<N>) Complete: <summary>`.

### Step 1: Worktree + plans

- **Locations:** git worktree `.claude/worktrees/agentic-documents-foundation` (branch
  `agentic-documents-foundation`); `docs/plans/agentic-documents-system.md` (design, tracked here);
  `docs/plans/agentic-documents-foundation.md` (this plan).
- **Rationale:** isolate the work on a branch and record the actionable, validated build sequence
  before writing code, matching how every prior feature in `docs/checklist.md` was delivered.
- **Action:** Undergo the verification/validation process for this phase (`git status` clean tree,
  plan docs present). Once validated, commit stating:
  `Agentic Documents Foundation (1/6) Complete: worktree + design/implementation plan docs`.

### Step 2: Data layer — models, CRUD, seed

- **Locations:**
  - `utils/backend/database/models.py` — new models `UploadedDocument`, `BehavioralProfile`,
    `WritingStyleProfile`, `DocumentTemplate`, `JobEvaluation`, `GeneratedDocument` (FKs to `jobs.id`
    with `ondelete='CASCADE'` for job-linked tables, single-active `is_active` on the two profile-like
    tables, unique `job_id` index on `job_evaluations`).
  - `utils/backend/database/documents_ops.py` (**new**) — CRUD + `_*_to_dict` serializers + field
    whitelists + single-active `_deactivate_*` helpers, mirroring `operations.py` (kept separate to
    stay under the 800-line cap).
  - `utils/backend/database/seed_documents.py` (**new**) — `seed_documents_if_empty()` inserting the
    §1.4 starters (example behavioral profile, writing style, job-evaluation rubric, 3 cover-letter
    templates + 1 résumé skeleton) only when the target tables/active rows are empty.
  - `utils/backend/database/init_db.py` — call `seed_documents_if_empty()` inside `init_database()`
    after `_run_migrations()`.
  - `utils/backend/database/__init__.py` — export the new models + CRUD functions.
  - `tests/database/test_agentic_documents.py` (**new**) — in-memory `StaticPool` isolation;
    round-trip each table, assert the single-active invariant, template default-per-kind, the
    `job_evaluations` upsert, and seed idempotency (running the seed twice adds nothing).
- **Rationale:** the data layer "unblocks everything" (§8.1). New tables come from `create_all`
  (fresh + existing DBs), so no column migration is needed; an idempotent seed makes the feature work
  on day one while letting user uploads overwrite the starters.
- **Action:** Undergo the verification/validation process for this phase (`pytest tests/database`
  green; new-schema round-trips + seed idempotency pass in-memory; `import app` clean). Once validated,
  commit stating:
  `Agentic Documents Foundation (2/6) Complete: supporting-document models + CRUD + idempotent seed + tests`.

### Step 3: Ingestion agent (in-house)

- **Locations:**
  - `utils/backend/agents/__init__.py`, `utils/backend/agents/ingestion/__init__.py` (**new package**).
  - `utils/backend/agents/ingestion/agent.py` (**new**) — `ingest_document(filename, data,
    doc_type=None, client=None) -> dict` running the pipeline **extract → classify → summarize/normalize**
    (reuses `profile_builder.extract_resume_text`; classifies the doc type when unspecified; routes to a
    per-type normalizer: résumé→Profile fields via `build_profile_from_text`, behavioral→
    `behavioral_profiles` fields, writing→`writing_style_profiles` fields, reference/other→summary-only).
    Uses `OpenAIClient.from_config(require_enabled=False)` and degrades to an empty editable draft when
    no endpoint is configured, exactly like the résumé builder. Returns a **draft, not persisted**.
  - `utils/backend/agents/ingestion/prompts.py` (**new**) — per-doc-type system prompts + `normalize_*`
    helpers with safe defaults (mirrors `profile_builder`'s normalize pattern).
  - `tests/agents/test_ingestion.py` (**new**) — a fake `chat_json` client; assert classification,
    each normalizer's shape, and graceful degradation with no LLM.
- **Rationale:** generalizes the résumé→profile flow to every supporting document (§1.3) using the
  existing LLM plumbing — no new client. Keeping it plain-Python (the in-house orchestrator decision)
  makes it fully offline-testable.
- **Action:** Undergo the verification/validation process for this phase (`pytest tests/agents` green;
  `import app` clean). Once validated, commit stating:
  `Agentic Documents Foundation (3/6) Complete: in-house ingestion/summarization agent + tests`.

### Step 4: Backend routes — documents blueprint

- **Locations:**
  - `utils/backend/routes/documents_routes.py` (**new**, `documents_bp`): `POST /api/documents/ingest`
    (multipart → run ingestion → drafted record, not persisted), `POST /api/documents/ingest/save`
    (persist an approved record to its target table + create/link `uploaded_documents.derived_*`),
    supporting-doc CRUD `GET/POST /api/behavioral-profile`, `GET/POST /api/writing-style`,
    `GET/POST /api/templates` + `GET/PATCH/DELETE /api/templates/<id>`,
    `GET /api/job-evaluation/<job_id>`, and `GET /api/documents/uploaded` (raw-upload list).
  - `app.py` — register `documents_bp`.
  - `tests/documents/test_documents_api.py` (**new**) — Flask test client on an in-memory DB (patched
    `SessionLocal`), mocked ingestion client; assert ingest returns a draft, ingest/save persists +
    links `derived_*`, and the supporting-doc CRUD round-trips (400s where an active record/endpoint is
    required, mirroring `profile_routes`).
- **Rationale:** exposes the ingestion agent + supporting-doc records over the same
  upload→draft→edit→save contract users already know from the résumé flow (§5.2), reusing the
  blueprint/async conventions.
- **Action:** Undergo the verification/validation process for this phase (`pytest tests/documents`
  green; `import app` clean). Once validated, commit stating:
  `Agentic Documents Foundation (4/6) Complete: documents blueprint (ingest + supporting-doc CRUD) + tests`.

### Step 5: Frontend — Profile & Documents sidebar

- **Locations:** `utils/frontend/templates/index.html` (dc-runtime single file) — turn the Profile
  slide-over into a tabbed **Profile & Documents** sidebar: **Candidate** (existing fields),
  **Behavioral**, **Writing Style**, **Templates**, **Evaluation**. Each non-Candidate tab gets an
  upload zone (reusing the résumé drag-drop affordances) that POSTs to `/api/documents/ingest`, renders
  the agent's drafted record with per-field editing, then Saves via `/api/documents/ingest/save`; plus
  an **uploaded-documents list** (`/api/documents/uploaded`). Reuse the Analyze-Matches progress popup
  idiom for any long ingestion. `tests/test_frontend_wiring.py` — extend to assert the new tabs +
  endpoints are wired into the served page.
- **Rationale:** gives every supporting-document type a user-facing surface (§6.1) without new
  progress UI, using the panel/tab/upload idioms already in the file.
- **Action:** Undergo the verification/validation process for this phase (frontend-wiring test green;
  in-browser DOM verification of the tabs, upload → draft → edit → save round-trip, and the uploaded
  list, via the preview tools). Once validated, commit stating:
  `Agentic Documents Foundation (5/6) Complete: Profile & Documents tabbed sidebar + ingestion UI + wiring test`.

### Step 6: Docs + validation + check-in

- **Locations:** `docs/database.md`, `docs/structure.md`, `docs/routes.md`, `docs/api-contract.md`,
  `docs/component-map.md`, `docs/data-flow.md`, `docs/checklist.md` (new "Agentic Documents Foundation"
  Definition-of-Done section), and this plan.
- **Rationale:** documentation-maintenance rule — the same change that adds tables/routes/components
  updates the matching canonical docs.
- **Action:** Undergo the full verification/validation process (offline `pytest` subset green,
  `import app` clean, UI verified). Once validated, commit stating:
  `Agentic Documents Foundation (6/6) Complete: docs + checklist + validation`. **Then pause and check
  in with the user before building the cover-letter/résumé agent graphs; hold the merge to `main` for
  that check-in.**

---

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Supporting-document models | 6 SQLAlchemy tables (uploaded/behavioral/writing/templates/job-eval/generated) | `utils/backend/database/models.py` |
| Documents CRUD | CRUD + serializers + single-active helpers | `utils/backend/database/documents_ops.py` |
| Idempotent seed | Day-one starter records, insert-if-empty | `utils/backend/database/seed_documents.py` |
| Ingestion agent | In-house extract→classify→summarize→normalize pipeline | `utils/backend/agents/ingestion/agent.py`, `prompts.py` |
| Documents blueprint | Ingest + supporting-doc CRUD routes | `utils/backend/routes/documents_routes.py` |
| Profile & Documents sidebar | Tabbed upload→draft→edit→save UI + uploaded list | `utils/frontend/templates/index.html` |
| Data-layer tests | In-memory round-trips + single-active + seed idempotency | `tests/database/test_agentic_documents.py` |
| Ingestion tests | Mocked-LLM classify/normalize/degradation | `tests/agents/test_ingestion.py` |
| Route tests | Test-client ingest/save + CRUD round-trips | `tests/documents/test_documents_api.py` |
| Frontend-wiring test | Served-page tab/endpoint assertions | `tests/test_frontend_wiring.py` |
