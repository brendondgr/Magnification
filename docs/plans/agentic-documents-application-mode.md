# Plan — Application Mode (the interactive Apply flow)

**Status:** Implementation plan (branch `agentic-documents-foundation`, worktree).
**Scope:** design §4 — turn the passive "Applied" click into an **Apply** action that opens an
interactive, agent-assisted flow to generate + iteratively refine a tailored résumé and/or cover
letter for a specific job. Moves generation **out of the Profile side-panel** (the user disliked it
there) into a dedicated centered modal that mirrors the Find Jobs modal shell.

**Explicitly out of scope (still deferred):** the browser-automation submission adapter (§4.3) and a
persisted `application_sessions` table — the session is ephemeral frontend state; the generated
documents persist (in `generated_documents`).

---

## What the user asked for
1. **Two buttons** where there is one "Applied" today: **Applied** (quick mark-as-applied, unchanged
   `markApplied`) and **Apply** (opens the flow).
2. **Apply** walks through creating a tailor-made **résumé / cover letter**: start the process, watch
   the **stages step-by-step**, and see the **final results**.
3. **Trigger manual changes** and have it **continuously go through the process until the user deems
   it worthy** — i.e. an iterate/refine loop (edit the text directly, or steer a fresh guided re-run).

## Design

### Backend — steer + refine (small additions to the existing graphs)
The graphs already run to completion; they gain optional **guidance** so a re-run is steerable:
- `context.load_context(..., instructions="", prior_content="")` → `state["instructions"]`,
  `state["prior_content"]`.
- Cover letter: `strategize` + `write_letter` fold `instructions` (high-priority) and, when present,
  the `prior_content` (the current draft to build on) into their prompts.
- Résumé: `plan_edits` + `rewrite_resume` do the same (rewrite is already holistic).
- `service.start_generation(kind, job_id, template_id, interactive, instructions, prior_content,
  revise_from)`. When `revise_from` (a doc id) is set, `_persist` **updates that row in place**
  (bumping `revision`) instead of creating a new one — so a job keeps one evolving draft per kind
  rather than accumulating rows.
- Routes `/api/documents/{cover-letter,resume}/start` accept `{instructions?, revise_from?}`. When
  `revise_from` is set the route loads that document's content as `prior_content`.
- Every prompt change is additive and keeps the no-LLM fallback intact.

### Frontend — Apply button + Application Mode modal
- **Cards + detail:** replace the single **Applied** button with **Apply** (primary, opens the flow)
  + a compact **Applied** (secondary, `markApplied`). New Jobs card, Saved card, and the job-detail
  panel. Remove the **Documents** section (and its `docView` modal) from the side panel.
- **Application Mode** = one centered modal (mirrors the Find Jobs shell: overlay → card → header →
  screen `sc-if`s), driven by an `app` state object with `stage ∈ intake | generating | review`:
  - **Intake:** "Apply to {company} — {title}". Toggles *Tailor my résumé* / *Write a cover letter*
    (both default on), an optional **guidance** textarea, and actions **Start**, **Just mark
    Applied** (skip → `markApplied` + close), **Cancel**. If the job already has drafts, offer
    *Review existing*.
  - **Generating:** one progress panel per selected kind — percent bar + current node **stage** +
    a live **stage feed** (the node events). Both kinds run in parallel, each with its own poller.
  - **Review:** per document — status chip, résumé **match-lift** badge (recommendation color
    grading), the content inline, and actions **Edit** (inline textarea → PATCH save), **Refine**
    (feedback textarea + quick chips: *Warmer tone / More concise / Different angle / Stronger
    opening* → guided re-run via `revise_from`), **Approve**, **Download**. A footer **Mark as
    Applied & Done** (→ `markApplied` + close) and **Close**. Refine keeps the same doc id and
    re-shows that card's progress until the user approves — the "continuously go through the
    process" loop.
- Reuses: `formatStage` labels, `matchColorFor` grading, `showToast`, the modal shell + animations.

---

## Steps
1. **Plan doc** (this file). Commit.
2. **Backend refine:** `instructions`/`prior_content` through context + cover/résumé nodes +
   prompts; `service.start_generation` + `_persist` `revise_from`; routes accept `instructions`/
   `revise_from`. Tests: guided run threads instructions; `revise_from` updates in place. Commit.
3. **Frontend — Apply entry points + teardown:** Apply/Applied buttons on cards + detail; remove the
   side-panel Documents section + `docView` modal; migrate the doc methods into the `app`-scoped
   ones. Commit.
4. **Frontend — Application Mode modal:** intake → generating → review markup + state + methods +
   renderVals; the refine loop. Wiring test. Commit.
5. **Live verify in-app** (Apply → intake → parallel generate w/ live stages → review → edit →
   refine → approve → mark Applied); fix issues. Then docs + adversarial review + validation. Commit.

## Deliverables
| Area | Files |
| --- | --- |
| Backend | `agents/context.py`, `nodes_shared.py`, `nodes_cover_letter.py`, `nodes_resume.py`, `prompts.py`, `service.py`, `routes/document_generation_routes.py` |
| Frontend | `utils/frontend/templates/index.html` |
| Tests | `tests/agents/test_refine.py`, `tests/documents/test_generation_api.py` (+refine), `tests/test_frontend_wiring.py` (+Apply/Application-Mode tokens) |
| Docs | `routes.md`, `api-contract.md`, `data-flow.md`, `component-map.md`, `checklist.md` |

---

## Iteration 2 — LaTeX documents + PDF preview workspace

**Status:** Delivered on top of the Apply flow above (branch `agentic-documents-foundation`, worktree).
**Scope:** the generation graphs now emit **LaTeX** instead of Markdown, a compile subsystem renders that
source to a **PDF**, and the Review screen becomes a **two-column workspace** — the live agent process
feed alongside the rendered PDF preview — with per-document tabs.

**Still out of scope (unchanged):** the browser-automation submission adapter (§4.3) and a persisted
`application_sessions` table.

### What changed and why
The refine loop above returned Markdown-ish plain text. The user wanted a **print-ready document** they can
actually see and download, so the output format becomes **LaTeX** (typeset quality, deterministic offline
assembly) and the Review screen shows the compiled **PDF** next to the live generation process instead of a
raw text blob.

### Backend — LaTeX output + PDF compile/serve
- **LaTeX assembly** (`utils/backend/agents/latex.py`, deterministic + offline): `escape_latex` (escapes
  TeX specials), `md_to_latex` (light Markdown → LaTeX for the model's prose), and `build_cover_letter_tex`
  / `build_resume_tex` (assemble a full `\documentclass{article}` document). The graphs' final node emits
  LaTeX; `generated_documents.content` is now a complete `.tex` document and the row persists
  `format="latex"`. The résumé **match-lift** is still scored on the plain tailored text (not the LaTeX),
  so the recommender-reuse scoring is unchanged.
- **PDF compile** (`utils/backend/pdf_compile.py`): `compile_pdf(...)` shells out to `pdflatex` and caches
  the result under `data/generated_pdfs/`, keyed by content (an unchanged document isn't recompiled). A
  missing toolchain or a source that fails to typeset raises `LatexCompileError`.
- **Serve routes:** `GET /api/documents/<id>/pdf` compiles (or reuses the cache) and streams the PDF
  inline, or as an attachment with `?download=1`; it returns 404 (unknown doc), 415 (a non-LaTeX
  document), or 422 (compile failure) — all logged. `GET /api/documents/<id>/tex` returns the raw LaTeX
  source (always available, even when no TeX toolchain is installed).

### Frontend — two-column tabbed workspace
- The Review stage becomes a two-column `data-appws` workspace:
  - **Left — Process:** the live step-by-step agent feed (rendered from the task `events`, including the
    revision loops), plus the refine controls — quick chips + a feedback box (**Regenerate**, re-runs in
    place via `revise_from`) and the **Edit LaTeX** / **Download PDF** / **Approve** actions.
  - **Right — Preview:** the compiled PDF in an `<iframe>` whose `src` is set through a React `ref` — so
    the raw template never fetches a literal `{{…}}` URL before hydration.
  - **Document tabs** switch between *Tailored Résumé* and *Cover Letter*; on narrow screens a
    **Process ∣ Preview** toggle swaps the two columns. The PDF recompiles (re-fetches `/pdf`) after each
    refine or LaTeX edit.
- Reuses the existing Application-Mode modal shell, pollers, `revise_from` refine loop, and `matchColorFor`
  grading — this iteration reshapes the Review stage rather than adding a new flow.

### Steps
1. **LaTeX assembly:** `agents/latex.py` helpers; the cover-letter/résumé final nodes emit a full
   `\documentclass{article}` document; persist `format="latex"`. Tests (`tests/agents/test_latex.py`).
   Commit.
2. **PDF compile + serve:** `pdf_compile.compile_pdf` (pdflatex, on-disk cache, `LatexCompileError`);
   `/api/documents/<id>/pdf` + `/tex` routes. Tests (`tests/documents/test_pdf_route.py`). Commit.
3. **Two-column workspace:** the `data-appws` Process ∣ Preview Review layout, document tabs, ref-driven
   `<iframe>` PDF preview, recompile-on-refine. Wiring test
   (`test_index_has_two_column_latex_workspace`). Commit.
4. **Docs + validation:** this section + the checklist; full suite green. Commit.

### Deliverables
| Area | Files |
| --- | --- |
| Backend | `utils/backend/agents/latex.py` (new), `utils/backend/pdf_compile.py` (new), `routes/document_generation_routes.py` (pdf/tex routes), the cover-letter/résumé graph nodes (LaTeX output) |
| Frontend | `utils/frontend/templates/index.html` |
| Tests | `tests/agents/test_latex.py`, `tests/documents/test_pdf_route.py`, `tests/test_frontend_wiring.py::test_index_has_two_column_latex_workspace` |
| Docs | `checklist.md`, this plan |
