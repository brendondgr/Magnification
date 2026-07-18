# Plan — Agentic Document System + Application Mode

> **Superseded in part (2026-07):** the Behavioral / Writing-Style / Document-Template subsystems
> and the upload-ingestion agent described below were **removed** in favor of a single editable
> **Document Guidance** document that steers both generation graphs. See
> `docs/plans/documents-sidebar-simplify.md`. The cover-letter/résumé graphs and Application Mode
> shipped and remain current.

**Status:** Design only — no implementation. This document is an actionable plan, not code.
**Stack:** Python + LangGraph, riding on Magnification's existing Flask/SQLite/OpenAI-compatible-LLM stack.
**Autonomy model:** Semi-automatic (runs end-to-end, pauses at a small number of checkpoints when confidence is low or the user opts in).

This plan adds four capabilities to Magnification, in dependency order:

1. **A document-upload sidebar + ingestion agent** — the reorganized Profile becomes a place to upload source documents (résumé, behavioral assessment, writing samples, etc.), which an agent summarizes/normalizes into the structured records the pipeline needs.
2. **A Cover Letter generator** (layered LangGraph agent).
3. **A Résumé fine-tuner** (layered LangGraph agent).
4. **Application Mode** — an interactive per-job flow, triggered by an **Apply** button, that asks whether the user wants a tailored résumé and/or an altered cover letter, runs the relevant agents, and is architected so a future browser-control agent can auto-submit applications.

It is inspired by the ingestion → research → strategize flow of [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search), but rebuilt around Magnification's data model instead of static markdown files.

---

## 0. The core insight — ingestion is already done

The ai-job-search framework has to *fetch and parse* a job posting every time (`/apply <url>`). **Magnification does not.** By the time a user is looking at a job, the scrape + analyze pipeline has already stored, per job:

| Already in the DB | Source |
| --- | --- |
| Full job description (the JD) | `Job.description` |
| Company, location, compensation | `Job.company`, `Job.location`, `Job.compensation` |
| Board / source / link | `Job.site`, `Job.link` |
| Skills the JD wants | `JobAnalysis.extracted_skills` |
| Matched vs. missing skills | `JobAnalysis.skill_match {matched, missing}` |
| Keyword-group hits | `JobAnalysis.keyword_group_hits` |
| LLM fit verdict + rationale | `JobAnalysis.llm_score`, `JobAnalysis.llm_rationale` |
| Hybrid match score + sub-signals | `JobAnalysis.rag_score`, `semantic/bm25/keyword/skill` |
| The candidate's résumé + profile | `Profile.resume_text`, `skills`, `job_titles`, `keyword_groups`, `interests_paragraph` |

So the agent graphs' **Ingestion layer is a database read**, not a scrape. The expensive context-gathering is free and already scored. Both generators key off a `job_id` and the active `Profile`.

---

## 1. Data layer — supporting documents + uploads

ai-job-search stores its supporting material as flat files (`01-candidate-profile.md` … `07-…`). In Magnification these become **DB-backed, editable records** so they fit the panels and can be versioned. The existing `Profile` table already *is* the Candidate Profile; we add siblings, plus a raw-upload store and an application-session store.

### 1.1 Reuse / extend
- **Candidate Profile** → the existing `Profile` table. Possibly add `full_name` / `contact` blob for letter headers. Already holds `resume_text`, `skills`, `job_titles`, `interests_paragraph`, `keyword_groups`.

### 1.2 New tables (mirror `Profile`'s single-active-row pattern)

| Table | Purpose | Key fields |
| --- | --- | --- |
| `uploaded_documents` | Raw source files the user drops into the sidebar, before/after summarization | `filename`, `doc_type`, `raw_text`, `summary`, `derived_table`, `derived_id`, `status`, `uploaded_at` |
| `behavioral_profiles` | DISC/PI-style work-style traits that shape *tone and framing* | `traits` (JSON), `strengths`, `work_style_paragraph`, `is_active` |
| `writing_style_profiles` | Tone, structure, do's/don'ts, a real writing sample to imitate | `tone`, `formality`, `sample_text`, `dos` (JSON), `donts` (JSON), `sentence_length` |
| `document_templates` | Reusable cover-letter / résumé skeletons | `kind` ("cover_letter"\|"resume"), `name`, `body`, `format` ("markdown"\|"latex"\|"docx"), `is_default` |
| `job_evaluations` | Per-job **application-fit** evaluation (distinct from recommendation scoring) | `job_id`, `profile_id`, `verdict`, `fit_score`, `emphasize` (JSON), `gaps` (JSON), `risks`, `talking_points` (JSON) |
| `generated_documents` | The outputs, linked to a job | `job_id`, `kind`, `content`, `format`, `status` ("draft"\|"approved"), `match_before`, `match_after`, `revision`, `checkpoint_state` (JSON) |
| `application_sessions` | One interactive Application Mode run per job (see §5) | `job_id`, `stage`, `wants_resume`, `wants_cover_letter`, `document_ids` (JSON), `submission_method`, `submission_state`, `created_at` |

Notes:
- `job_evaluations` is the **"job evaluation system"** the user asked for — a richer, application-oriented read than `JobAnalysis` (which is recommendation ranking). It is *seeded* from `JobAnalysis` so it starts half-filled and cheap.
- `uploaded_documents.derived_table`/`derived_id` link a raw upload to the structured record the ingestion agent produced from it, so the user can always trace "this writing-style profile came from that PDF."
- All "profile-like" tables keep one `is_active` row, matching how `Profile` works today.

### 1.3 Document upload + ingestion agent (the sidebar's engine)

This generalizes the résumé→profile flow the app already has (`/api/profile/upload` → `profile_builder.extract_resume_text` → LLM draft → `normalize_profile` → user edits → save) to **every** supporting document type. The reorganized Profile sidebar (§6.1) exposes upload zones; each upload runs a small **Ingestion / Summarization agent**:

```
 upload file (pdf/tex/md/txt/docx)
      │  store raw in uploaded_documents
      ▼
 extract_text        pypdf / light parsing (reuse profile_builder.extract_resume_text)
      ▼
 classify            infer doc_type if not given (résumé | behavioral | writing sample | reference | other)
      ▼
 summarize/normalize LLM turns raw text into the structured record for its target table:
      │                • résumé          → Profile fields (existing builder)
      │                • behavioral doc  → behavioral_profiles {traits, work_style_paragraph, strengths}
      │                • writing sample  → writing_style_profiles {tone, dos, donts, sample_text}
      │                • reference/other → summary text attached for later agent context
      ▼
   ◇ user reviews the drafted record (nothing persisted until Save) ◇
      ▼
 save → the target table; link uploaded_documents.derived_* back to it
```

Design points:
- **Reuses `OpenAIClient.from_config()`** — no new LLM plumbing. Same "upload → LLM draft → edit → save" contract users already know from the résumé flow, so it's familiar and each field stays user-editable.
- **Nothing is persisted until the user approves the draft**, exactly like the current résumé builder.
- Multiple writing samples can be uploaded; the agent can merge them into one writing-style profile (union of dos/donts, representative sample).

### 1.4 Seeded example documents (so it works on day one)
Ship starter records and let uploads overwrite them: an example **Behavioral Profile**, **Writing Style**, a **Job Evaluation rubric**, and 2–3 **cover-letter templates** (classic, narrative, referral) with slots like `{{hook}}`, `{{why_them}}`, `{{why_you}}`, `{{close}}`. Candidate Profile is produced by the existing résumé upload.

---

## 2. System A — Cover Letter Generator (LangGraph)

Design bet: **separate strategy from prose from voice.** Decoupling the Strategist from the Writer is what kills generic letters — the "what to say" is decided (and optionally approved) before a word is written.

### 2.1 Node graph
```
 load_context      read Job + JobAnalysis + Profile + Behavioral + WritingStyle from DB
       ▼           (Ingestion = DB read; no scrape)
 research_company  enrich beyond the DB: mission, values, recent news (LLM + optional web)
       ▼
 evaluate_fit      Job Evaluator → verdict, emphasize[], gaps[], talking_points[]
       ▼           (seeded from JobAnalysis.skill_match + llm_rationale)
 strategize        pick 2–3 strongest candidate↔role hooks → thesis
       ▼
   ◇ CHECKPOINT 1 ◇  approve/edit the angle (auto-skip when confidence high)
       ▼
 write             Narrative Writer → draft, using chosen template slots
       ▼
 style             Voice agent → apply WritingStyle (tone, dos/donts, sample)
       ▼
 critique          Critic (score + genericness flags) ‖ Truthfulness (grounding) — parallel
       ▼
   ◇ decision ◇  score ≥ threshold && truthful?  yes → finalize │ no → loop to write (cap 2–3, then CHECKPOINT 2)
       ▼
 finalize          persist generated_documents(kind="cover_letter"); render to template format
```

### 2.2 Worker agents
| Node | Job | Reads | Writes |
| --- | --- | --- | --- |
| `research_company` | Mission, values, recent news, role emphasis | `Job.company`, JD | `job_evaluations.talking_points` |
| `evaluate_fit` | Application-fit verdict + what to emphasize | `JobAnalysis`, Profile | `job_evaluations` |
| `strategize` | Rank 2–3 connection points | eval + Behavioral | `thesis` (state) |
| `write` | Draft around the thesis + template | template, Candidate Profile | `draft` |
| `style` | Match tone/voice/length | Writing Style | `styled_draft` |
| `critique` | Score vs JD, flag generic sentences | JD, draft | `score`, `critiques[]` |
| `truthfulness` | Reject any claim not traceable to `resume_text`/profile | Candidate Profile | `pass/fail` |

---

## 3. System B — Résumé Fine-Tuner (LangGraph)

Separate graph, separate outputs. Résumés need *analysis → rewrite → score → loop*. The standout feature: the **Critic reuses Magnification's own recommender** to measure improvement objectively.

### 3.1 Node graph
```
 load_context     Job + JobAnalysis + Profile.resume_text (missing/matched skills already computed)
       ▼
 evaluate_gap     which JD keywords/skills are missing or under-weighted
       ▼          (seed from JobAnalysis.skill_match.missing + keyword_group_hits)
 plan_edits       relevance-weighted plan: which bullets to rewrite, reorder, cut
       ▼          (score each line by JD-relevance × uniqueness; cut lowest first)
   ◇ CHECKPOINT 1 ◇  approve the rewrite/cut plan (opt-in, or when cuts are large)
       ▼
 rewrite          rewrite/reorder bullets to mirror JD language (truth-preserving)
       ▼
 ats_format       machine-readable structure; keyword coverage without stuffing
       ▼
 score            ★ reuse the recommender: treat the tailored résumé as a transient profile and
       ▼            run ranker/service against THIS job → fresh rag_score (match_after)
 truthfulness     grounding check vs original resume_text
       ▼
   ◇ decision ◇  match_after ≥ match_before + Δ && truthful?  yes → finalize │ no → loop (cap 2–3, then CHECKPOINT 2)
       ▼
 finalize         persist generated_documents(kind="resume", match_before, match_after)
```

### 3.2 Why the recommender reuse matters
Magnification already computes a hybrid `rag_score` per job×profile. The Critic builds a **throwaway profile** from the tailored résumé text and runs it through `utils/backend/recommend/ranker.py`/`service.py` against the single target job — a real **match-lift** (e.g. 62% → 81%) that serves as both stop criterion and headline UI metric. No static tool can produce this.

### 3.3 Worker agents
| Node | Job | Reuses |
| --- | --- | --- |
| `evaluate_gap` | Missing/under-weighted JD keywords & skills | `JobAnalysis.skill_match`, `keyword_group_hits` |
| `plan_edits` | Relevance-weighted rewrite/reorder/cut plan | — |
| `rewrite` | Truth-preserving bullet rewrites mirroring JD | Candidate Profile |
| `ats_format` | ATS-safe structure + keyword coverage | template (`kind="resume"`) |
| `score` | Objective match-lift | **recommender (`ranker`/`service`)** |
| `truthfulness` | No fabricated experience | `Profile.resume_text` |

---

## 4. Application Mode — the interactive apply flow

A new mode that turns a passive "mark as applied" click into an **interactive, agent-assisted application session**, and lays the groundwork for future automated (browser-controlled) applying.

### 4.1 The Apply-button change (the trigger)

Today the job card / detail panel has a button that immediately sets status to **Applied** (`markApplied`). We **split intent from status**:

- Rename the button **Applied → Apply**. Clicking **Apply** no longer just flips a status — it **opens Application Mode** for that job and creates an `application_sessions` row.
- The **"Applied"** status is now the *result* reached at the end of the flow (or when the user skips), via the existing `PATCH /api/jobs/<id>/status`.

This decoupling is the seam that makes future automated applying possible: "the user wants to apply" (a trigger/event) is now a distinct, capturable moment from "the application has been submitted" (a state).

### 4.2 The interactive flow (wizard)

```
 click Apply on a job
      │  create application_sessions(job_id, stage="intake")
      ▼
 INTAKE   "How do you want to apply to <Company> — <Title>?"
      │   ▸ Tailor my résumé?        (yes/no)   → wants_resume
      │   ▸ Write a cover letter?     (yes/no)   → wants_cover_letter
      │   ▸ "I applied elsewhere → mark Applied" (one-click skip: jumps straight to DONE,
      │      sets status Applied, generates no docs)
      ▼
 GENERATE run the chosen agent graph(s) — §2 and/or §3 — with their semi-auto checkpoints.
      │   progress shown via the reused Analyze-Matches popup (§6.2)
      ▼
 REVIEW   show final tailored résumé (with match-lift) and/or cover letter; user approves/edits.
      │   approved docs → generated_documents.status="approved", linked to the session
      ▼
 SUBMIT   submission_method ∈ { manual (now), browser_agent (future) }
      │   ▸ manual: user is handed the docs + Job.link to submit on the portal
      │   ▸ browser_agent: (future) a browser-control agent opens Job.link, fills the form,
      │     uploads the approved docs, and pauses for a final human confirm before submit
      ▼
 DONE     mark ApplicationStatus → "Applied"; store submission_state on the session
```

Application Mode is **orchestration**, not a third generator: it composes Systems A and B, plus the existing Tracker status transitions.

### 4.3 The browser-automation seam (future, but designed now)

The `SUBMIT` step is defined behind a small **submission-adapter** abstraction so today's manual path and tomorrow's automation share one contract:

- `submission_method="manual"` — the only adapter built now; presents approved docs + link.
- `submission_method="browser_agent"` — a *future* **Playwright**-based adapter that consumes the same approved `generated_documents` + `Job.link`, drives a headed browser to fill and submit the portal form (uploading the approved docs), and always ends on a **human-confirm checkpoint** before the final click. Playwright is the chosen target for its scripting control; the adapter contract stays generic so another tool could be swapped in.

`application_sessions.submission_state` records progress (`not_started → filling → awaiting_confirm → submitted → failed`), so the same UI works for both adapters. No automation is built in this plan — only the seam that makes it a drop-in later.

---

## 5. Backend integration

Follow Magnification's conventions — a new package under `utils/backend/`, new blueprints, and the **async task + poll** pattern already used by `/api/scrape/*` and `/api/recommend/analyze/*`.

### 5.1 New package
```
utils/backend/agents/
├── graph_state.py        # TypedDict shared state (job_id, profile snapshot, drafts, scores, checkpoint)
├── checkpointer.py       # LangGraph SqliteSaver → reuse data/*.db (survives HTTP + interrupts)
├── ingestion/            # §1.3 upload→summarize→normalize agent (generalizes profile_builder)
├── nodes/                # node functions (thin wrappers over OpenAIClient.chat / chat_many)
├── cover_letter/graph.py # cover-letter StateGraph
├── resume/graph.py       # résumé StateGraph
├── application/session.py# Application Mode orchestration + submission adapters (manual now)
└── service.py            # run/resume a graph, emit progress events, persist outputs
```
- **LLM calls** reuse `utils/backend/llm/OpenAIClient.from_config()` + `chat_many`. No new client.
- **Checkpointer** = LangGraph SQLite saver on the existing `data/` DB, so a paused graph survives reloads (fits local-first, single-user).
- **Progress events** reuse the existing `{status, progress:{stage,percent,details}, events:[{t,stage,percent,message}]}` shape so the frontend reuses its polling + activity-feed code.

### 5.2 New blueprints

**`documents_bp` (`/api/documents`)** — generation + supporting docs:

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/documents/ingest` | POST | multipart upload → §1.3 summarize → drafted structured record (not persisted) |
| `/api/documents/ingest/save` | POST | persist an approved ingested record to its target table |
| `/api/documents/cover-letter/start` | POST | `{job_id}` → `{task_id}`; runs cover-letter graph in a thread |
| `/api/documents/resume/start` | POST | `{job_id}` → `{task_id}`; runs résumé graph |
| `/api/documents/status/<task_id>` | GET | Poll `{status, progress, events, results}` |
| `/api/documents/<task_id>/resume` | POST | `{decision, edits}` → resume a graph paused at a checkpoint (LangGraph `interrupt`) |
| `/api/documents?job_id=` | GET | List generated documents for a job |
| `/api/documents/<id>` | GET/PATCH | Fetch / edit-approve a generated document |

**Supporting-doc CRUD** (extend `profile_bp` or add `docs_config_bp`): `GET/POST /api/behavioral-profile`, `/api/writing-style`, `/api/templates`, `/api/job-evaluation/<job_id>` — same upsert-active-row pattern as `/api/profile`.

**`application_bp` (`/api/application`)** — Application Mode:

| Route | Method | Purpose |
| --- | --- | --- |
| `/api/application/start` | POST | `{job_id}` → create `application_sessions`, return session |
| `/api/application/<id>` | GET/PATCH | Read / update session (intake choices, stage) |
| `/api/application/<id>/submit` | POST | invoke the submission adapter (manual now); set status |

### 5.3 New models
Add §1.2 tables to `utils/backend/database/models.py` with idempotent migrations (repo already does `migrate_*`). `generated_documents`, `job_evaluations`, `application_sessions` FK to `jobs.id` with cascade delete, matching `JobAnalysis`.

---

## 6. Frontend / UI integration (dc-runtime)

Everything lives in the single `index.html` dc-runtime component, reusing existing patterns. **Every agent gets a user-facing surface.**

### 6.1 Reorganized Profile → a "Profile & Documents" sidebar
The current Profile slide-over becomes a tabbed sidebar:

- **Candidate** — the existing résumé/profile fields.
- **Behavioral**, **Writing Style**, **Templates**, **Evaluation** — each with an **upload zone** (drag-drop pdf/tex/md/txt/docx) that hits `/api/documents/ingest`, shows the agent's drafted summary, lets the user edit every field, then Save (`/api/documents/ingest/save`). This is the "upload documents → an agent summarizes them into something the pipeline can use" flow the user asked for. Reuses the existing résumé-upload affordances (`onResumeFile`, `pfSet`, `saveProfile`).
- An **uploaded-documents list** showing each raw file, its inferred type, and which record it produced (from `uploaded_documents.derived_*`).

### 6.2 Generation progress — reuse the Analyze-Matches popup
The app already has a background-task progress popup (`analyzing`, `aPercent`, `aStage`, `aEvents`, `pollAnalyze`). Reuse it verbatim for ingestion and document generation: percent ring + live activity feed of the node stages. No new progress UI to design.

### 6.3 Apply button → Application Mode menu
- On the job card and job-detail panel, relabel the status button **Applied → Apply**; its handler calls `/api/application/start` and opens **Application Mode** (a new centered modal/mode, mirroring the Find Jobs modal) for that job.
- **Application Mode screens:** Intake (résumé? cover letter? apply-as-is) → Generate (progress popup + the §2/§3 checkpoints: angle-approval card, edit-plan/diff view, match-lift badge) → Review (approve/edit final docs) → Submit (manual hand-off now; the same screen later hosts the browser-agent adapter with its human-confirm checkpoint) → Done (advances Tracker to "Applied").
- The résumé diff view (original vs. tailored, per-line accept/reject), genericness/truthfulness flags, provenance tooltips, and "re-run at any layer" buttons (`try a warmer tone`, `different angle`) all live in the Generate/Review screens and map 1:1 to the node graphs.

### 6.4 Tracker integration
Approved docs attach to the job's Tracker card and are downloadable; reaching "Applied" is now the *end* of Application Mode (or an explicit skip), via `PATCH /api/jobs/<id>/status`. `application_sessions.submission_state` drives a small status chip so a future browser-agent submission shows live progress in the same place.

### 6.5 Design-system fit
Reuse tokens/motifs: match-lift badge uses the recommendation match badge's color grading (teal ≥66 / coral ≥40 / muted <40); matched/missing chips reuse offer-tinted / muted chip styles; progress popup reuses the percent ring; Application Mode modal reuses the Find Jobs modal shell. Copy stays in the app's concrete job-hunt vocabulary.

---

## 7. Semi-auto checkpoints (summary)

| Flow | Checkpoint 1 (proactive) | Checkpoint 2 (safety) |
| --- | --- | --- |
| Ingestion | Review the summarized record before Save | — |
| Cover letter | Approve the **angle** before prose (auto-skipped when confidence high) | Critic loop hits cap, or Truthfulness flags a claim |
| Résumé | Approve the **rewrite/cut plan** (shown when cuts are large) | `match_after` not above `match_before`, or Truthfulness flags |
| Application Mode (future browser submit) | — | **Human-confirm before final submit**, always |

LangGraph's `interrupt()` + the SQLite checkpointer implement all pauses; the UI surfaces state, the user resumes via the relevant `resume`/`submit` route.

---

## 8. Build order (suggested)

1. **Data layer** — add §1.2 models + migrations + seed §1.4 examples. Unblocks everything.
2. **Ingestion agent + Profile & Documents sidebar** (§1.3, §6.1) — gives every downstream agent its inputs, and reuses the existing résumé-upload pattern.
3. **Cover Letter graph** (§2) — simpler, one clear checkpoint; validate end-to-end with the reused progress popup.
4. **Résumé graph** (§3) + the recommender-scoring reuse — the differentiated, higher-effort piece.
5. **Application Mode** (§4) — Apply-button change, intake wizard, manual submission adapter, Tracker "Applied" at the end.
6. **Browser-automation adapter** (§4.3) — *future*, drops into the existing submission seam.
7. **Verification:** unit-test the graphs offline with a mocked LLM (repo already mocks the LLM in `tests/`); assert the résumé Critic's match-lift comes from the real ranker on a fixture job; assert Apply creates a session without prematurely setting "Applied".

---

## 9. Open questions
- **Company research source:** LLM-only, a web-search node, or a connector? (Affects `research_company`.)
- **Résumé output format:** Markdown/docx first vs. LaTeX+PDF compile/inspect loop like ai-job-search. Recommend Markdown/docx first.
- **Writing-style bootstrap:** require an uploaded sample, or infer style from `resume_text` when none is uploaded?
- **Ingestion doc types:** fixed set (résumé/behavioral/writing/reference) or a free "other → summary-only" bucket for anything else?
- **Single vs. multi profile:** behavioral/writing-style/templates stay single-active like `Profile`, or become per-profile?
- **Browser-automation (Playwright):** how are portal logins/credentials handled, and how does the adapter cope with the wide variance in application-form layouts across boards?

---

## References
- ai-job-search framework: https://github.com/MadsLorentzen/ai-job-search
- Magnification internals: `docs/data-flow.md`, `docs/recommendation.md`, `docs/profile.md`, `docs/api-contract.md`, `docs/component-map.md`, `utils/backend/database/models.py`.
- Orchestrator-worker multi-agent pattern (2026): https://www.digitalapplied.com/blog/agent-architecture-patterns-taxonomy-2026
