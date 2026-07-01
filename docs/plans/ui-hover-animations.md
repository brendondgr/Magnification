# UI Hover & Movement Animations

## 1. Introduction

The app's entire frontend is one dc-runtime template (`utils/frontend/templates/index.html`,
~1595 lines: an `<x-dc>` HTML template + an inline `class Component extends DCLogic`). Entrance
animations exist (`jf-fade`, `jf-slide`, `jf-pop`, `jf-pulse`, `jf-rise` keyframes) and exactly one
element — the Tracker kanban job card — has a working hover treatment
(`transition:transform .15s,box-shadow .15s` + `style-hover="transform:translateY(-2px);box-shadow:var(--shadow)"`).
Every other interactive surface — header buttons, sidebar controls, New Jobs cards and their
action buttons, the job-detail timeline, the Find Jobs modal (chips, toggles, pill buttons,
sliders), the Profile panel, and the Options panel (tabs, toggle rows, sliders) — has no
`transition` and no hover/active feedback. The page reads as static despite being fully
interactive.

The runtime supports this natively: any HTML attribute named `style-<pseudo>` (e.g.
`style-hover`, `style-active`, `style-focus`) is compiled into a real inserted stylesheet rule
(`.scpN:<pseudo>{...}`) and merged onto the element's `className`
(`utils/frontend/static/js/dc-runtime.js:384-412` `collectProps`, `:1351-1369`
`createPseudoSheet`). No runtime changes are needed — this is a template-only content change.
The approach is to (a) add `transition:` to every interactive element's base `style` (either the
literal HTML attribute or the JS string that builds it), and (b) add a `style-hover` (and
`style-active` where it reads well) attribute with a small, consistent motion vocabulary reusing
the existing design tokens (`var(--accent)`, `var(--shadow)`, `var(--surface2)`, `var(--border2)`,
the `jf-*` keyframes) — no new colors, radii, or fonts.

Motion vocabulary (kept small and reused everywhere, matching the existing kanban-card hover):
- **Primary/accent buttons** (Applied, Find Jobs, Start Search, Save…, Analyze matches, View New
  Jobs): `translateY(-1px)` + `filter:brightness(1.06)`, `.15s` ease, plus `active` gives a slight
  press (`translateY(0);filter:brightness(.97)`).
- **Secondary/bordered buttons** (Details, Cancel, Close, Test connection, Prev/Next, header
  Profile/Options): border/background tint to `var(--surface2)`/`var(--border2)`.
- **Icon-only square buttons** (panel close ✕, ignore, kanban-column remove, match-info “?”):
  `background:var(--surface2)` + slight `scale(1.06)`.
- **Cards** (New Jobs article): extend the exact kanban-card treatment
  (`translateY(-2px)` + `box-shadow:var(--shadow)`) for consistency.
- **Pills/tabs/toggle rows** (nav tabs, Options tabs, site/job-type pills, toggle rows, mobile
  nav): background tint on hover, no movement (these already move via selected-state color, so
  hover only needs a subtle unselected-state cue).
- **Chip remove “×” buttons**: `opacity` 0.7/0.8 → 1 + slight `scale(1.1)`.
- **Range sliders**: `filter:brightness(1.1)` on hover (native thumb; no custom track styling).
- **Clickable rows** (timeline steps): background tint on hover, no movement.

## 2. Gaps & Unanswered Questions

- **`docs/design-system.md` is stale** — it documents an older color-token set
  (`--color-primary`, `.hover-lift`) that no longer exists in the shipped template (the live
  tokens are `--accent`, `--bg`, `--surface`, `--r-sm`, etc., defined per-theme in
  `Component.THEMES`). *Assumption*: update the Motion section of `docs/design-system.md` to
  describe the real token names and the `style-hover` mechanism, without doing a full doc
  rewrite (out of scope for this change).
- **Two themes exist** (`editorial` default, `neon`) — hover values must work for both since they
  only reference theme variables (`var(--accent)`, `var(--surface2)`, etc.), never literal colors.
  *Assumption*: verify visually in the default `editorial` theme only; the token-only approach
  makes `neon` correct by construction.
- **Native `<input type="range">` thumbs** can't be pseudo-selected cross-browser without a real
  stylesheet (`::-webkit-slider-thumb` isn't reachable via inline `style-hover`, which only
  targets the host element). *Assumption*: apply a whole-element `filter:brightness(1.1)` hover
  instead of thumb-specific styling — a reasonable, low-risk substitute.
- **No automated test exists for hover CSS.** *Assumption*: verification is manual/in-browser via
  the preview tools (dispatch `mouseenter`/computed-style checks), not a new pytest file — this is
  a pure CSS/markup change with no Python behavior to unit test.

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Worktree + plan doc
- **Locations**: `.claude/worktrees/ui-hover-animations` (new worktree/branch), this plan file.
- **Rationale**: Matches the repo's established pattern (every prior UI feature shipped from an
  isolated worktree, committed per phase, merged to `main`) and gives a clean diff to review.
- **Action**: Undergo the verification/tests/validation process for this phase (worktree created,
  plan committed, `git status` clean). Once validated, commit stating: UI Hover Animations (1/7)
  Complete: Added the plan doc and set up the worktree.

#### Step 2: Header, sidebar, mobile nav
- **Locations**: `utils/frontend/templates/index.html` — `<header>` block (sidebar-toggle icon
  button, nav tabs, Profile/Find Jobs/Options buttons), `<aside data-desk>` sidebar (search input
  focus state, Clear Database button), mobile `<nav data-mob>` tabs; JS builders `navTabs`,
  `mkMobTab`, `secBtn` inside `renderVals()`.
- **Rationale**: These are the first interactive elements on every screen and share the fewest
  variants — a good, low-risk first pass to validate the `style-hover` pattern reads well before
  scaling it to the rest of the page.
- **Action**: Undergo the verification/tests/validation process for this phase (start the app,
  hover each header/sidebar/mobile-nav control, confirm smooth transitions, no layout shift, no
  console errors). Once validated, commit stating: UI Hover Animations (2/7) Complete: Added hover
  and focus animations to the header, sidebar, and mobile nav.

#### Step 3: New Jobs grid — cards, action buttons, pager
- **Locations**: `index.html` `<sc-if value="{{ isNewJobs }}">` section (sort/analyze/show-ignored
  buttons, article card, ignore button, match-info “?”, Applied/Details/Link buttons, empty-state
  CTA, pager); JS `decorate()` (`cardStyle`, `ignoreBtn`) and `renderVals()`
  (`showIgnoredStyle`, `analyzeStyle`, `sortStyle`).
- **Rationale**: The highest-traffic surface (main job-browsing view) and currently the most
  static — cards don't lift on hover the way Tracker cards already do.
- **Action**: Undergo the verification/tests/validation process for this phase (hover a job card,
  its buttons, the header action buttons, and the pager; confirm the card lift matches the
  existing Tracker-card feel). Once validated, commit stating: UI Hover Animations (3/7) Complete:
  Added hover animations to the New Jobs grid, its cards, and their action buttons.

#### Step 4: Tracker kanban polish + Job Detail panel
- **Locations**: `index.html` Tracker `<sc-if value="{{ isTracker }}">` section (column header,
  "Drop here" affordance — kanban job card already animated), Job Detail `<aside>` (ignore button,
  timeline step rows, Close/Visit Job Post buttons); JS timeline builder in `renderVals()`
  (`selectedJob.timeline` mapping, `d.line`/`d.dot`/`d.label`).
- **Rationale**: Completes the two job-centric views; the timeline rows are clickable but give no
  feedback today.
- **Action**: Undergo the verification/tests/validation process for this phase (drag a card, open
  a job's detail panel, hover/click timeline steps and the footer buttons). Once validated, commit
  stating: UI Hover Animations (4/7) Complete: Polished Tracker kanban feedback and added hover
  animations to the Job Detail panel and timeline.

#### Step 5: Find Jobs modal + Match Breakdown popup
- **Locations**: `index.html` Find Jobs `<sc-if value="{{ findOpen }}">` (chip remove buttons,
  country add buttons, job-type pills, site pills, keyword-group controls, LLM refinement row,
  Cancel/Start Search, View New Jobs) and Match Breakdown popup (Close/Full details); JS
  `siteList`, `jobTypeList`, `llmRow`/`llmCheck`, `genKeywordsStyle` in `renderVals()`.
- **Rationale**: The densest interactive surface in the app (many pill toggles and chip inputs) —
  isolating it as its own phase keeps the diff reviewable.
- **Action**: Undergo the verification/tests/validation process for this phase (open Find Jobs,
  toggle sites/job-type/LLM refinement, add/remove a chip, hover Cancel/Start Search, open a match
  popup). Once validated, commit stating: UI Hover Animations (5/7) Complete: Added hover
  animations throughout the Find Jobs modal and the Match Breakdown popup.

#### Step 6: Profile panel + Options panel
- **Locations**: `index.html` Profile `<sc-if value="{{ profileOpen }}">` (dropzone, Build Profile
  button, skill/title/keyword chip controls, Close/Save Profile) and Options
  `<sc-if value="{{ optionsOpen }}">` (LLM/Runtime tabs, toggle rows, Test connection/Save
  Endpoint, weight sliders, Save Runtime Settings); JS `tabStyle`, `toggleRow`, `toggleChk`,
  `buildBtnStyle`, `dropzoneStyle`, `saveRuntimeStyle` in `renderVals()`.
- **Rationale**: The two slide-over settings panels share the same toggle-row/tab pattern, so
  doing them together keeps the hover treatment for that shared pattern consistent.
- **Action**: Undergo the verification/tests/validation process for this phase (open Profile and
  Options, hover every toggle row, tab, chip, and button; drag a résumé over the dropzone; move a
  weight slider). Once validated, commit stating: UI Hover Animations (6/7) Complete: Added hover
  animations to the Profile and Options panels.

#### Step 7: Docs + full pass + merge
- **Locations**: `docs/design-system.md` (Motion section), `docs/checklist.md` (mark this item
  done), the `ui-hover-animations` worktree branch → `main`.
- **Rationale**: Repo rules require visual/motion decisions to be reflected in
  `docs/design-system.md` in the same change, and the worktree must be merged back per the
  worktree/merge workflow described in `docs/skills/global-project-rules/SKILL.md`.
- **Action**: Undergo the verification/tests/validation process for this phase (click through
  every screen once more end-to-end, `uv run python -c "import app"` still clean, no regressions).
  Once validated, commit stating: UI Hover Animations (7/7) Complete: Documented the motion system
  and merged hover/movement animations across the app to main. Merge the worktree branch into
  `main`, resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Hover/active/focus CSS additions | `transition` + `style-hover` (and `style-active` where used) on every interactive element | `utils/frontend/templates/index.html` |
| Updated card/button style builders | `transition` added to JS-built style strings (`cardStyle`, `secBtn`, `tabStyle`, `toggleRow`, `ignoreBtn`, `showIgnoredStyle`, `analyzeStyle`, `sortStyle`, `siteList`/`jobTypeList` styles, `llmRow`, `buildBtnStyle`, `saveRuntimeStyle`, etc.) | `utils/frontend/templates/index.html` (`Component.renderVals`, `Component.decorate`) |
| Motion documentation update | Real token names + the `style-hover` mechanism documented in the Motion section | `docs/design-system.md` |
| Checklist update | Mark the hover/animation pass done | `docs/checklist.md` |
| Manual verification | In-browser hover/click pass per phase via preview tools (no new automated test — pure CSS/markup change) | N/A (verification only) |
