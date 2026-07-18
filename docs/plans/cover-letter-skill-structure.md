# Cover-Letter Skill: Structured Output

Plan owner: agent · Branch: `cover-letter-skill` (worktree
`.claude/worktrees/cover-letter-skill`) · Design source: the attached "cover-letter" Office
Skill (a house-style guide: the *Winning Formula*, quantify-achievements rule, opening lines,
mistakes-to-avoid). Related: `docs/plans/agentic-documents-graphs.md` (§2, the cover-letter graph).

## 1. Introduction

The cover-letter graph (`utils/backend/agents/cover_letter.py` + `nodes_cover_letter.py`) already
runs a strategize → write → style → critique → truthfulness pipeline, but its prose guidance is a
loose set of "don't parrot the JD / don't sound like AI" rules scattered in
`utils/backend/agents/prompts.py`. The output is structurally flat and, in the user's words,
"lackluster." The attached skill supplies a concrete, proven **structure** — an Opening Hook, a
two-paragraph Value Proposition with quantified accomplishments matched to the role's requirements,
a Why-This-Company paragraph grounded in research, and a Strong Close with a call to action — plus
explicit writing rules (quantify achievements, strong openers, avoid the classic mistakes).

The approach is to **distill that skill into a single runtime source of truth** — a new
`utils/backend/agents/cover_letter_skill.py` module — and **inject it into every LLM node that
shapes the letter** (strategize, write, critique). Because both first-time generation and
Application-Mode *refine/regenerate* re-runs go through the same `cover_letter.run()` pipeline and
the same system prompts, wiring the skill into those prompts guarantees it is **always referenced**,
regardless of which template the user has selected or whether they are refreshing an existing draft.
The seeded default template is also reordered to the Winning Formula so new installs match the
structure the prompts describe.

This is a sequential, dependent change (prompts depend on the skill module; the template and tests
depend on both; docs depend on all of it), so it is implemented directly rather than fanned out to
parallel subagents.

## 2. Gaps & Unanswered Questions

- **Where the skill lives (code vs. `docs/skills/`).** The repo's `docs/skills/` folder holds
  *agent-workflow* skills with tri-tool pointer files; this cover-letter skill is *generation-time
  prose guidance* consumed by the LLM prompts. *Assumption:* keep the authoritative, distilled
  guidance as a Python constant module (`agents/cover_letter_skill.py`) — the runtime source of
  truth — and document its existence in `docs/`. This avoids a second competing copy and the
  pointer-file machinery that does not apply to a prompt fragment.
- **The original `~/Documents/CoverLetterSkill.md`.** It lives outside the repo and is not
  committed, so there is no in-repo competing source of truth to clean up. *Assumption:* we migrate
  its useful content into the module and do not vendor the raw file.
- **Reshaping seeded templates is idempotent-guarded.** `seed_documents_if_empty()` only seeds when
  no templates exist, so reordering the `Classic` body helps **new** installs only; existing installs
  keep their current template. *Assumption:* that is acceptable because the prompt-injected guidance
  (which is template-independent) is what actually enforces the structure on every run — the template
  reorder is alignment, not the enforcement mechanism.
- **Length/one-page target.** The skill says "standard 350 words, 3–4 paragraphs, one page"; the
  existing pipeline already targets 300–400 words (`COVER_MIN_WORDS`, the revision loop). These are
  compatible; no change to the length machinery is needed.
- **Commit, not push.** Per the session instruction, each phase is **committed** to git but **not
  pushed**. (The planner template's stock wording says "push"; it is overridden here.)

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Plan doc + worktree (this document)
- **Locations**: `docs/plans/cover-letter-skill-structure.md`; worktree
  `.claude/worktrees/cover-letter-skill` on branch `cover-letter-skill`.
- **Rationale**: Establish the isolated branch and a written, reviewable plan before touching code,
  per the global rules and the planner skill.
- **Action**: Confirm the plan reads cleanly and the worktree runs the existing cover-letter tests
  green against the shared venv. Once validated, **commit** stating: `Cover Letter Skill (1/5)
  Complete: plan doc + worktree + resolved design forks`.

### Step 2: The distilled skill module
- **Locations**: new `utils/backend/agents/cover_letter_skill.py` — constants `WINNING_FORMULA`
  (the four-part structure with the two-paragraph value proposition), `WRITING_RULES` (quantify
  achievements, strong openers, the mistakes-to-avoid list), and a `skill_guidance()` helper that
  composes them into one compact prompt block; new `tests/agents/test_cover_letter_skill.py`.
- **Rationale**: One authoritative, importable source for the structure means every consumer
  (prompts now, any future node later) references the same guidance — the "always referenced"
  requirement is satisfied at the source, not per-call-site.
- **Action**: Unit-test that the module exposes the four formula sections and the writing rules and
  that `skill_guidance()` returns a non-empty block containing them. Once validated, **commit**
  stating: `Cover Letter Skill (2/5) Complete: distilled house-style module + unit tests`.

### Step 3: Wire the skill into the generation prompts + default template
- **Locations**: `utils/backend/agents/prompts.py` — compose `skill_guidance()` into
  `STRATEGIZE_PROMPT` (angle must serve the formula), `WRITE_LETTER_PROMPT` (write to the formula,
  quantify, strong opener, avoid the mistakes — retaining the existing anti-parrot/anti-AI rules the
  quality tests assert), and `CRITIQUE_PROMPT` (score presence + strength of each formula section);
  `utils/backend/database/seed_documents.py` — reorder `_CLASSIC` to hook → value proposition →
  why-company → close; update `tests/agents/test_cover_letter_quality.py` for the new prompt markers.
- **Rationale**: The system prompts run on **every** generation and every refine (the guidance_block
  only *prepends* user feedback; the skill lives in the always-present system prompt), so injecting
  here is what makes the skill inescapable. The template reorder aligns new installs with the prompts.
- **Action**: Run the cover-letter graph + quality + refine tests; confirm both the first-pass and a
  refine (instructions + prior_content) route a writer system prompt that contains the formula.
  Once validated, **commit** stating: `Cover Letter Skill (3/5) Complete: skill wired into
  strategize/write/critique prompts + formula-ordered default template`.

### Step 4: Documentation + full offline validation
- **Locations**: `docs/structure.md` (new `cover_letter_skill.py` in the agents tree),
  `docs/plans/agentic-documents-graphs.md` or `docs/data-flow.md` (note the always-on skill
  reference), `docs/checklist.md` (new Definition-of-Done section for this change).
- **Rationale**: The global rules require docs to move with the code in the same change; the
  checklist is the definition of done.
- **Action**: Run the offline agent/document test subset (`tests/agents`, `tests/documents`,
  `tests/test_frontend_wiring.py`) + `import app`; all green. Once validated, **commit** stating:
  `Cover Letter Skill (4/5) Complete: docs + full offline validation`.

### Step 5: Merge to main
- **Locations**: branch `cover-letter-skill` → `main`; remove the worktree.
- **Rationale**: Deliver the change on the main line per the git workflow (no push).
- **Action**: Fast-forward/merge to `main`, re-run the offline subset + `import app` on `main`,
  resolve any conflicts. Once validated, **commit** the merge stating: `Cover Letter Skill (5/5)
  Complete: merged to main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan document | This staged plan | `docs/plans/cover-letter-skill-structure.md` |
| Skill module | Distilled Winning-Formula + writing-rules guidance, single runtime source of truth | `utils/backend/agents/cover_letter_skill.py` |
| Prompt wiring | Skill guidance composed into strategize/write/critique system prompts | `utils/backend/agents/prompts.py` |
| Template alignment | `Classic` cover-letter template reordered to the formula | `utils/backend/database/seed_documents.py` |
| Skill unit tests | Module exposes the formula + rules; `skill_guidance()` composes them | `tests/agents/test_cover_letter_skill.py` |
| Prompt/graph tests | Prompts embed the formula; first-pass **and** refine reference it | `tests/agents/test_cover_letter_quality.py` |
| Docs update | Structure, data-flow/plan note, checklist DoD | `docs/structure.md`, `docs/data-flow.md`, `docs/checklist.md` |
