# Profile Model Instructions — Implementation Plan

## 1. Introduction

The résumé→profile builder currently derives the `interests_paragraph`, `skills`, `job_titles`,
and `keyword_groups` purely from the résumé text. This adds an optional **Model Instructions**
field to the profile: free-text guidance the user types to steer what the LLM produces (e.g.
"I only want research roles in NLP, avoid management titles, emphasize Python/PyTorch"). The
instructions are stored on the profile and injected into the build prompt so the generated
sections reflect the user's intent, not just the résumé.

The field renders in the Profile panel **directly above the "Résumé → Profile" section**.

## 2. Gaps & Unanswered Questions

- **Field name / type** — *Assumption*: a nullable `Text` column `llm_instructions` on `profiles`
  (freeform prose, not a list).
- **How instructions reach the LLM** — *Assumption*: passed to `build_profile_from_text` and
  injected into the build messages as an explicitly-labeled, high-priority user instruction block
  ahead of the résumé text; the system prompt notes user instructions take precedence.
- **Source of truth on build** — *Assumption*: `POST /api/profile/build` reads `instructions`
  from the request body, falling back to the saved profile's `llm_instructions` when omitted.
- **Persistence vs. LLM output** — *Assumption*: `llm_instructions` is user input, not LLM
  output, so `normalize_profile` never overwrites it; it round-trips via save/load and is
  preserved across a rebuild (the build response only patches the four generated sections).

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Backend — column, migration, build wiring
- **Locations**: `utils/backend/database/models.py` (`Profile.llm_instructions` Text col);
  `utils/backend/database/migrate_profile_llm_instructions.py` (idempotent ALTER TABLE ADD
  COLUMN) wired into `init_db._run_migrations`; `operations.py` (`_PROFILE_FIELDS`,
  `_profile_to_dict`); `recommend/profile_builder.py` (`EMPTY_PROFILE`,
  `build_profile_from_text(text, client, instructions="")` injects the guidance);
  `routes/profile_routes.py` (`_build_draft` + `/api/profile/build` accept `instructions`,
  falling back to the saved profile; `save_profile` already whitelists fields — add
  `llm_instructions`).
- **Rationale**: the field must exist and flow into the LLM build before the UI can use it.
- **Action**: Undergo the verification/tests/validation process for this phase (CRUD round-trip
  of `llm_instructions`; a fake-client build test asserting the instructions appear in the
  prompt; `import app` clean). Once validated, commit stating: Profile Model Instructions (1/2)
  Complete: llm_instructions column + build-prompt injection + migration + tests.

### Step 2: Frontend — panel field + docs + merge
- **Locations**: `utils/frontend/templates/index.html` — a **Model Instructions** textarea
  section inserted directly above the "Résumé → Profile" block; state `profile.llm_instructions`,
  `loadProfile`/`saveProfile` carry it, `rebuildProfile` sends it as `instructions`; `renderVals`
  exposes `pfLlmInstructions` + `onPfLlmInstructions`; update `docs/profile.md`,
  `docs/api-contract.md`, `docs/component-map.md`, `docs/checklist.md`; merge to `main`.
- **Rationale**: completes the user-facing control and documents it.
- **Action**: Undergo the verification/tests/validation process for this phase (full `pytest`
  green, `import app` clean, preview verification that the field renders above the résumé
  section and round-trips through save/load). Once validated, commit stating: Profile Model
  Instructions (2/2) Complete: Panel field above the résumé section, docs, and merge to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Profile column + migration | `llm_instructions` Text column, idempotent migration | `models.py`, `migrate_profile_llm_instructions.py`, `init_db.py` |
| Serialization | Field in dict + allowed-write set + empty skeleton | `operations.py`, `recommend/profile_builder.py` |
| Build injection | `build_profile_from_text` uses the instructions | `recommend/profile_builder.py` |
| Build API | `/api/profile/build` + save accept `instructions`/`llm_instructions` | `routes/profile_routes.py` |
| Frontend field | Model Instructions textarea above the résumé section | `utils/frontend/templates/index.html` |
| Tests | CRUD round-trip + build-prompt injection | `tests/database/test_profile_blocklists.py` (extend) or new, `tests/profile/` |
| Docs | Field + contract + component map + checklist | `docs/profile.md`, `docs/api-contract.md`, `docs/component-map.md`, `docs/checklist.md` |
