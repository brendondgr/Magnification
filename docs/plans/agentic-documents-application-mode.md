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
