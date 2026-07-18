# Cover-Letter Flow Smoothing — the forced-fit (tell-not-show) fix

**Status: complete** · Branch `letter-flow` (worktree `.claude/worktrees/letter-flow`) · 2026-07-18

## Problem (user report)

Generated letters connect the candidate to the company in a way that reads forced, pandering, and
copy-pasted. Canonical example from a real output:

> "Ensemble's deployment of thousands of models show a clear commitment to putting AI into real
> world practice."

Nobody writes like that to a hiring manager — it *tells* the reader the company is great and
*asserts* fit instead of *showing* it. The user wants the letter to marinate: "I build/read/do X →
your team works on Y → that overlap is why I'd fit," expressed smoothly in one flow, not spliced
keyword claims ("I'm interested because of this and this and this").

Requested fix, in the user's priority order:

1. **A multi-stage process** — a step after writing that goes through the draft, finds the forced
   claims, and rewrites them; looping ("writes and relates it constantly") until they're gone.
2. **Prevention** — make the first shot less likely to produce them in the first place.

## Design

### 1. New `refine_flow` node (audit → rewrite loop) — the multi-stage step

Runs **after `style_letter`, before `critique_letter`**, inside the existing revision loop:

```
write → style → refine_flow (audit ⇄ rewrite, ≤ MAX_FLOW_PASSES) → critique ∥ truthfulness → decide
```

Per pass:

* **Audit** (`AUDIT_FLOW_PROMPT`, JSON): scan the letter sentence-by-sentence for *forced-fit*
  writing — (a) company flattery / tell-not-show ("shows a clear commitment", "is impressive",
  "aligns perfectly"), (b) asserted rather than demonstrated fit ("I would be a great match
  because…" with no shown work), (c) spliced/pasted connective tissue (keyword lists posing as
  motivation, abrupt topic jumps). Returns `{"flags": [{"quote", "problem", "fix"}]}`.
* If no flags → done. Otherwise **Rewrite** (`REWRITE_FLOW_PROMPT`, text): rewrite the letter fixing
  exactly the flagged sentences — replace each *claim about the company* / *assertion of fit* with a
  **shown** connection grounded in the candidate's real work and stated interests, keeping length,
  facts, structure, and everything unflagged intact.
* Loop, cap `MAX_FLOW_PASSES = 2` rewrites per revision (audit, rewrite, audit, rewrite worst case).

State: `smoothed_draft` (falls back to `styled_draft`), `flow = {"passes", "flags"}` for
observability. `current_document` (critique/truthfulness/final input) becomes the smoothed draft.
Offline / node failure → pass-through (project's no-LLM contract).

### 2. Prevention — first-shot + gate

* `WRITE_LETTER_PROMPT`: new hard rule — never compliment the company or narrate what its work
  "shows/demonstrates/reflects"; never assert fit ("I would be a great fit because…"); *show* the
  overlap: state what you actually build/do/read, then connect it to what the team works on, in one
  flowing sentence or two — the reader concludes the fit themselves.
* `CRITIQUE_PROMPT`: heavily penalize company-flattery / tell-not-show / asserted-fit sentences, so
  a letter that still carries them fails the accept gate and triggers a full revision.
* `DEFAULT_GUIDANCE` (Document Guidance → WRITING RULES): the same show-don't-tell rule, so it
  steers every node (guidance is injected into strategist, writer, style, critic, and the new flow
  node) and the user can tune it. (No user override is stored, so the improved default is live.)

## Phases

1. Plan doc + worktree. *(this commit)*
2. Prevention layer: prompts (`WRITE_LETTER_PROMPT`, `CRITIQUE_PROMPT`) + `DEFAULT_GUIDANCE` +
   new `AUDIT_FLOW_PROMPT` / `REWRITE_FLOW_PROMPT` / `normalize_flow_audit` + prompt tests.
3. `refine_flow` node + graph wiring + `MAX_FLOW_PASSES` + node/graph tests
   (`tests/agents/test_cover_letter_flow.py`).
4. Docs (`workflow.md`, `documentation.md`, `checklist.md`) + full-suite validation.
5. Merge to main (no push).

## Validation

* Unit: audit-with-flags → rewrite → clean-audit converges; clean first audit leaves the letter
  untouched; offline pass-through; audit exception pass-through; capped at `MAX_FLOW_PASSES`.
* Graph: `refine_flow` runs between style and critique; `current_document`/`final_text` carry the
  smoothed draft; guidance sentinel reaches the flow node's messages.
* Prompt assertions for the new rules; existing `tests/agents` suite stays green.
