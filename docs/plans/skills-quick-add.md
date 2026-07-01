# Skills Quick-Add — Implementation Plan

## 1. Introduction

The job detail panel already lists **"Skills the job wants you lack"** (`selectedJob.skillMissing`,
derived from `JobAnalysis.skill_match.missing`). Today those are inert tags. This plan makes each
one clickable: clicking adds the skill to the active profile's `skills` list. This does two
things: (1) the skill immediately becomes part of what the recommender matches against on future
`/api/recommend/analyze` runs, and (2) because a "Rebuild" from the résumé already **unions**
`blocked_companies` instead of overwriting it, extending that same union treatment to `skills`
means a manually-added skill survives a future LLM rebuild instead of being silently dropped.

Because the profile's `skills` tag list can now grow past what a résumé alone would produce, the
Profile panel's Skills field also gets a 20-item cap with a "Show all" expander, matching the
"otherwise it will get too long" requirement.

## 2. Gaps & Unanswered Questions

- **Where does "add skill" persist?** *Assumption*: a new `POST /api/profile/add-skill` endpoint,
  mirroring the existing `POST /api/profile/block-company` (case-insensitive de-dupe, creates a
  default profile if none exists, returns the updated list). Reusing generic `POST /api/profile`
  would require the client to already hold the full current skills array, which races against a
  concurrent profile edit in the Profile panel; a dedicated additive endpoint avoids that.
- **Does adding a skill re-score the job immediately?** *Assumption*: no — it optimistically moves
  the clicked skill from `skill_match.missing` to `skill_match.matched` on the affected job(s) in
  local state (cosmetic, immediate feedback) but does **not** call `/api/recommend/analyze`. Real
  re-scoring already has a dedicated, user-triggered "Analyze matches" action; auto-triggering a
  potentially-slow LLM re-rank as a side effect of one click is out of scope.
- **Show-all threshold** — *Assumption*: 20, matching the user's "first 20 or so" wording. Applies
  only to the Profile panel's **Skills** tag list (the field this change grows); other tag lists
  (job titles, keyword groups, blocklists) are unaffected.
- **Scope of the clickable affordance** — *Assumption*: apply it everywhere `skillMissing` chips
  render (the job detail panel section named in the request, and the card's match-breakdown
  popup, since both are built from the same `buildBreakdown()` helper) rather than forking the
  helper.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Backend — `POST /api/profile/add-skill`
- **Locations**: `utils/backend/routes/profile_routes.py` (new `add_skill()` view, modeled on
  `block_company()`: body `{"skill": "<name>"}`, 400 on blank, case-insensitive de-dupe against
  the active profile's `skills`, creates a default profile via `db_ops.upsert_active_profile` if
  none exists, returns `{success, skills}`); `tests/profile/test_profile_skill_api.py` (new file,
  isolated in-memory-DB fixture copied from `tests/profile/test_profile_block_api.py`): add
  appends, idempotent re-add, blank skill → 400; `docs/api-contract.md` and `docs/routes.md`
  (document the new endpoint next to `block-company`).
- **Rationale**: the frontend needs a single atomic call that adds-and-dedupes server-side, same
  shape as the existing company-block flow, before any UI can wire into it.
- **Action**: Undergo the verification/tests/validation process for this phase (`uv run pytest
  tests/profile/`, `uv run python -c "import app"`). Once validated, commit stating: Skills
  Quick-Add (1/3) Complete: POST /api/profile/add-skill endpoint + tests + docs.

### Step 2: Frontend — clickable "skills you lack" chips
- **Locations**: `utils/frontend/templates/index.html` — `buildBreakdown(an, match, jobId)`
  (~line 1029) gains a `jobId` param and adds `onAdd:()=>this.addSkillToProfile(x, jobId)` to each
  `skillMissing` entry; the two call sites (`selectedJob` detail-panel breakdown ~line 1509, and
  the card `matchPopup` ~line 1518) pass `sj.id` / `mj.id` respectively; a new
  `addSkillToProfile(skill, jobId)` method (near `blockCompany`, ~line 1100) optimistically (a)
  adds the skill to `state.profile.skills` (de-duped) and (b) moves it from that job's
  `analysis.skill_match.missing` to `.matched` via `patchJob`, then POSTs `/api/profile/add-skill`
  and reverts both on failure (same capture-prior/revert-on-error shape as `blockCompany`); the
  "Skills the job wants you lack" chip markup (~line 338-347) becomes a `<button onclick="{{
  sk.onAdd }}">` with a small "+"/add affordance and a hover state, keeping the existing muted
  styling otherwise.
- **Rationale**: wires the UI action the user asked for — click a missing skill, it becomes one of
  your skills — using the app's existing optimistic-update + revert-on-failure pattern instead of
  inventing a new one.
- **Action**: Undergo the verification/tests/validation process for this phase (`uv run pytest`,
  `import app` clean; preview-verify in-browser: open a job with missing skills, click one, confirm
  it moves to "Your matching skills" and appears in the Profile panel's Skills list after opening
  Profile). Once validated, commit stating: Skills Quick-Add (2/3) Complete: clickable missing-skill
  chips add to the profile with optimistic UI + revert-on-failure.

### Step 3: Rebuild-safe union + Profile panel 20-item cap + docs + merge
- **Locations**: `utils/frontend/templates/index.html` — `rebuildProfile()` (~line 1339): extend
  the existing `blocked_companies` union pattern to `skills` (union existing + LLM-regenerated,
  case-insensitive de-dupe) so a manually-added skill is never dropped by a résumé rebuild;
  `renderVals()` profile-panel section (~line 1567-1570): cap the rendered `pfSkills` list to the
  first 20 (`Component.SKILLS_SHOW_LIMIT = 20` or an inline const), add
  `pfSkillsExpanded`/`onTogglePfSkills` state + a `pfSkillsHasMore`/`pfSkillsToggleLabel` computed
  pair; template (~line 449-460): a "Show all (N)" / "Show less" text button under the skills tag
  list, gated by `<sc-if value="{{ pfSkillsHasMore }}">`; docs — `docs/profile.md` (document the
  quick-add affordance + skills union-on-rebuild), `docs/api-contract.md`/`docs/routes.md` (already
  updated in Step 1, verify), `docs/component-map.md` (new state keys/method), `docs/checklist.md`
  (new Definition-of-Done section); merge the worktree branch to `main`.
- **Rationale**: closes the loop the user described — added skills survive future LLM rewrites,
  and the now-potentially-longer skills list stays readable.
- **Action**: Undergo the verification/tests/validation process for this phase (`uv run pytest`,
  `import app` clean; preview-verify: add >20 skills, confirm only 20 render + "Show all (N)"
  expands the list; trigger a résumé rebuild with a manually-added skill present and confirm it
  survives). Once validated, commit stating: Skills Quick-Add (3/3) Complete: rebuild-safe skills
  union, Profile panel 20-item cap with Show all, docs, and merge to main.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| `add-skill` endpoint | Additive, de-duped skill endpoint mirroring block-company | `utils/backend/routes/profile_routes.py` |
| Endpoint tests | Add / idempotent / blank-name coverage on an isolated in-memory DB | `tests/profile/test_profile_skill_api.py` |
| Clickable missing-skill chips | `addSkillToProfile`, `buildBreakdown(jobId)`, chip markup | `utils/frontend/templates/index.html` |
| Rebuild-safe skills union | `rebuildProfile()` unions `skills` like `blocked_companies` | `utils/frontend/templates/index.html` |
| Profile panel skills cap | 20-item cap + Show all/Show less toggle | `utils/frontend/templates/index.html` |
| Docs | Quick-add + union behavior + new endpoint + state/method ownership | `docs/profile.md`, `docs/api-contract.md`, `docs/routes.md`, `docs/component-map.md`, `docs/checklist.md` |
