# Plan — Cover-Letter Quality + LaTeX Export

> **Superseded (2026-08).** Both halves shipped elsewhere: the quality work under
> `cover-letter-skill-structure.md` and `cover-letter-flow-smoothing.md`, and the LaTeX/PDF export
> under `agentic-documents-application-mode.md`. Kept as a record of the original analysis.

## 1. Introduction

The cover-letter generator produces letters that are too short (roughly half the
target length) and that invent the candidate's interests and motivations instead
of grounding them in the profile the user actually wrote. The user's real
interests already live in the active Profile's `interests_paragraph` field (the
"A paragraph describing your interests, background, and the work you want…" box),
but that text is never surfaced to the strategy/writing nodes — so the model
fills the "why you want this" prose from thin air. The target is a **300–400 word**
letter that argues from the candidate's *stated* interests and real background.

The approach: (1) surface the profile's `interests_paragraph` (and a compact
candidate-facts block) explicitly to the strategize and write nodes; (2) add an
explicit 300–400 word target and an anti-fabrication instruction about
interests/motivations to the cover-letter prompts; (3) enforce a minimum length
in the revision loop so a too-short first draft triggers another pass. Separately,
add a **LaTeX (`.tex`) export** control alongside the existing "Download PDF" in
the two-column workspace (the `GET /api/documents/<id>/tex` route already exists —
this is a frontend button + handler).

## 2. Gaps & Unanswered Questions

- **Exact length band.** The user said "like 300-400 words." *Assumption*: aim
  for 300–400 words; enforce a floor of ~280 words in the acceptance check (a hard
  400 ceiling is left to the prompt, not enforced, to avoid endless loops).
- **Offline (no-LLM) path length.** The deterministic fallback letter is template-
  filled and will not reach 300 words. *Assumption*: length grounding is an
  LLM-path quality goal; the offline path must still produce a valid, compilable
  letter (it does) — we do not pad it artificially.
- **Where interests come from.** *Assumption*: `profile["interests_paragraph"]`
  is the single source of the candidate's stated interests/goals (confirmed: it
  is the field the profile UI writes and `build_profile_query` reads).
- **Export format.** *Assumption*: export the raw `.tex` source via the existing
  `/tex` route (attachment), matching "LaTeX file exports."

## 3. Hierarchical Step-by-Step Instructions

> Note: per this repo's rules and the session directive, "push" below means
> **commit only — do NOT push to the remote.**

### Step 1: Surface the candidate's real interests + facts to the writer

- **Locations**: `utils/backend/agents/nodes_shared.py` (new `candidate_facts`
  helper); `utils/backend/agents/nodes_cover_letter.py` (`strategize`,
  `write_letter` — include the interests/facts block in their user messages).
- **Rationale**: The model hallucinates interests because the profile's
  `interests_paragraph` is never given to the strategy/writer. Passing it (plus a
  short résumé/skills fact block) grounds the "why you / what you want" prose in
  the user's own words.
- **Action**: Undergo the verification/tests/validation process for this phase.
  Once validated, commit (do NOT push) stating: Cover Letter Quality + LaTeX
  Export (1/4) Complete: interests_paragraph + candidate facts surfaced to the
  strategy and writer nodes.

### Step 2: Retarget the cover-letter prompts (length + no invented interests)

- **Locations**: `utils/backend/agents/prompts.py` — `STRATEGIZE_PROMPT`,
  `WRITE_LETTER_PROMPT`, `STYLE_PROMPT`.
- **Rationale**: The prompts must state the 300–400 word target and forbid
  inventing interests/motivations, telling the model to draw them from the
  candidate's stated interests only. The style pass must preserve length (not
  compress the letter back down).
- **Action**: Undergo the verification/tests/validation process for this phase.
  Once validated, commit (do NOT push) stating: Cover Letter Quality + LaTeX
  Export (2/4) Complete: prompts retargeted to 300–400 words grounded in stated
  interests.

### Step 3: Enforce minimum length in the revision loop

- **Locations**: `utils/backend/agents/cover_letter.py` (`run` — add a length
  gate to the accept condition and a "expand" note into the next revision's
  guidance); `utils/backend/agents/nodes_cover_letter.py`
  (`_heuristic_critique` — count words, penalize under-length so the offline
  critic reflects the same intent); a small `letter_word_count` helper.
- **Rationale**: Prompts alone don't guarantee length. Gating acceptance on a
  word floor makes a short first draft trigger a second pass (up to
  `MAX_REVISIONS`) instead of shipping a half-length letter.
- **Action**: Undergo the verification/tests/validation process for this phase.
  Once validated, commit (do NOT push) stating: Cover Letter Quality + LaTeX
  Export (3/4) Complete: revision loop enforces a minimum letter length.

### Step 4: LaTeX (.tex) export control in the workspace

- **Locations**: `utils/frontend/templates/index.html` — new `downloadAppTex`
  method, `onDownloadTex` in `appCard`, and an "Export .tex" button next to
  "Download PDF". Docs: `docs/api-contract.md` / `docs/component-map.md` already
  list `/tex`; note the new UI control.
- **Rationale**: The user wants the LaTeX source, not just the rendered PDF. The
  `/tex` route exists; this exposes it in the UI.
- **Action**: Undergo the verification/tests/validation process for this phase.
  Once validated, commit (do NOT push) stating: Cover Letter Quality + LaTeX
  Export (4/4) Complete: added a .tex export control to the workspace.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Candidate-facts helper | Surfaces `interests_paragraph` + résumé/skills facts to prompts | `utils/backend/agents/nodes_shared.py` |
| Node wiring | strategize/write include interests+facts | `utils/backend/agents/nodes_cover_letter.py` |
| Retargeted prompts | 300–400 words, no invented interests | `utils/backend/agents/prompts.py` |
| Length gate | Word-floor acceptance + heuristic critic | `utils/backend/agents/cover_letter.py`, `nodes_cover_letter.py` |
| .tex export UI | Export button + handler | `utils/frontend/templates/index.html` |
| Cover-letter tests | interests surfaced, prompt tokens, length helper/gate | `tests/agents/test_cover_letter_quality.py` |
| Frontend wiring test | asserts `Export` + `downloadAppTex` present | `tests/test_frontend_wiring.py` |
