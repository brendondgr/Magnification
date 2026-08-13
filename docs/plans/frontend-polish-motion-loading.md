# Plan — Frontend Polish: Motion, Loading, and Responsiveness

Apply `docs/frontend-polish-spec.md` (the contract) to the served page,
`utils/frontend/templates/index.html`, plus the one supporting patch to
`utils/frontend/static/js/dc-runtime.js`. The headline requirement from the user is
**loading items on the page**; everything else in the spec is an overhaul pass on top of it.

## Starting point

- The whole UI is one `<x-dc>` template plus one inline `class Component extends DCLogic`.
  All styling is inline `style=` strings; pseudo-states come from `style-hover` / `style-active` /
  `style-focus` attributes, which the runtime compiles into a real stylesheet
  (`createPseudoSheet` in `dc-runtime.js`).
- **There is no loading state anywhere.** `state.loading` is set to `true` in the constructor and
  flipped by `loadJobs()`, but nothing reads it: while the first `GET /api/jobs` is in flight the
  New Jobs grid renders `gridEmpty` — the "No new jobs to show / Find Jobs" empty state. The user
  sees a false "you have nothing" screen on every load, then a hard cut to a full grid. Same for
  Saved (`savedEmpty`), the Tracker ("Drop here" in every column), and the sidebar pipeline counts.
- A failed `loadJobs()` is a 2.4s toast and the same empty state — indistinguishable from success
  with zero rows, and there is no retry.
- The Profile, Options, and Guidance panels fetch on open and render empty fields until the
  response lands.
- Motion is hardcoded: `.15s ease` on ~200 elements, `.3s` / `.32s` / `.35s` / `.38s` on entrances.
  No tokens, no `prefers-reduced-motion` handling, no exits (overlays unmount instantly).
- Responsiveness: `100vh` (not `dvh`), `minmax(330px,1fr)` grid tracks (overflow below 362px),
  no container queries, fixed px type, 34px icon buttons (below the 44px touch floor).
- Accessibility: no `aria-busy`, no `aria-live`, no skip link, no `Esc`, no focus trap or restore,
  focus rings only on text inputs.

## Gaps and decisions

| Question | Decision |
| --- | --- |
| Where do motion tokens live? Theme maps or a stylesheet? | A `:root` block in the existing `<style>` in `<helmet>`. Durations/easings are theme-independent; `Component.THEMES` stays color+shape only, which is what `tests/frontend/test_theme_tokens.py` pins. |
| Spec §4 (streaming LLM text) | **Not applicable.** No endpoint streams tokens to the browser; the agent/scrape feeds are polled event lists. The applicable parts (status line that changes, `aria-live`, reserved container height) are implemented on those feeds. |
| Spec §6 scroll-driven reveals in an app shell | Applied where there is real scroll travel — the job-detail panel's long body and the Tracker column cards — behind `@supports (animation-timeline: view())` + `prefers-reduced-motion`, base = revealed. Not applied to the New Jobs / Saved cards, which own the one signature moment (below) and would double-animate. |
| The one signature motion moment (§11) | The **skeleton → cards handoff**: skeleton cards cross-fade out, real cards rise in with a 45ms stagger capped at 8. It is the moment the app's actual content arrives, so it is the moment worth choreographing. |
| Hover on touch (§5) | Patch `createPseudoSheet` in the vendored runtime to wrap every generated `:hover` rule in `@media (hover:hover) and (pointer:fine)`. One change fixes all ~200 hover states; doing it per-attribute in the template is not possible. |
| Animated overlay exits (§13) with no unmount hook | Add a generic `closeWithExit(key, commit)` helper + a `closing` state key. Overlays render an exit animation for `--dur-fast`, then commit the state change. Under reduced motion the delay is skipped. |

## Phases

Each phase ends with `uv run pytest` (the relevant subset), a served-HTML check, and a commit.

### Phase 1 — Foundation: tokens, base layer, hover gating

1. Add the motion token block (`--dur-*`, `--ease-*`, `--lift-*`) and a `--focus` token to `:root`
   in the `<style>` block of `index.html`.
2. Add the base layer: `prefers-reduced-motion` reset, global `:focus-visible` ring,
   `@media (pointer:coarse)` 44px floor for the 34px icon buttons, `text-wrap`, skeleton +
   `content-in` + stagger + reveal utilities.
3. Add a skip-to-content link as the first focusable node; give `<main>` an id.
4. Patch `createPseudoSheet` in `utils/frontend/static/js/dc-runtime.js` to gate `:hover` rules
   behind `@media (hover:hover) and (pointer:fine)`.

**Validate:** page still serves and hydrates (`test_frontend_wiring.py`, `test_theme_tokens.py`);
grep the served HTML for the tokens and the reduced-motion block.
**Commit:** "Frontend: motion tokens, base a11y layer, touch-safe hover gating".

### Phase 2 — The loading state ladder (the headline)

1. Replace `state.loading` with an explicit feed machine: `jobsState: 'loading'|'ready'|'error'`,
   plus `jobsSkeleton` (the 300ms delay gate) and a 15s timeout that moves to `error`.
   Add `_delayedFlag(key, ms)` and `_clearDelayed(key)` helpers, cleared in `componentWillUnmount`.
2. Render the ladder in all three feeds:
   - **New Jobs / Saved** — a skeleton `<article>` that traces the real 7-row card (same rows,
     same clamp heights, same button block, last text line at 60%), 6 of them, `aria-busy` on the
     grid, `aria-hidden` on the bars.
   - **Tracker** — skeleton cards inside each column.
   - Empty states only render once `jobsState === 'ready'`.
3. Add the **error state**: what failed, in the app's voice, plus a Retry button calling
   `loadJobs()` again. Same `content-in` entrance as success content.
4. Panel-level loaders: Profile (`pfLoading`), Options (`optLoading`), Guidance (`guidanceLoading`)
   get skeleton field blocks behind the same 300ms gate.
5. Button `loading` variants that do not change width: Analyze matches, Save Profile, Save
   Guidance, Test connection, Build Profile — a spinner replaces the label inside a fixed min-width.
6. `aria-live="polite"` on the toast, the scrape feed, the analyze feed, and the agent feed;
   `aria-busy` on every loading container.

**Validate:** new `tests/frontend/test_loading_states.py` asserts the served page contains the
skeleton markup, the delay-gate constant, the timeout, the retry control, and the aria attributes,
and that the empty state is gated on the ready state. Manual: `/api/jobs` shape unchanged.
**Commit:** "Frontend: full loading ladder for the job feeds and panels".

### Phase 3 — Motion pass

1. Mechanically replace hardcoded durations with tokens across the template
   (`.15s ease` → `var(--dur-fast) var(--ease-soft)`; entrances → `--dur-base` / `--dur-slow`
   with `--ease-out`).
2. Retime the keyframes: entrances `--dur-base`/`--dur-slow`, new exit keyframes at `--dur-fast`.
3. Implement `closeWithExit` and wire the detail panel, Profile, Options, Find Jobs, Application
   Mode, the match popup, and the analyze popup so they animate out.
4. Stagger the card entrance (`--i` inline, 45ms, capped at 8) — the signature moment.
5. Scroll-driven `.jf-reveal` on the detail-panel body sections and Tracker cards.
6. `document.startViewTransition` around tab changes in `goTab`, feature-detected.

**Validate:** grep the served HTML for any remaining `\.\d+s ease` literal; confirm every
`animation:` reference resolves to a defined keyframe.
**Commit:** "Frontend: tokenized motion, animated exits, one signature entrance".

### Phase 4 — Responsiveness

1. `100vh` → `100dvh` everywhere; `90vh` → `90dvh` on modal max-heights.
2. Grid tracks → `repeat(auto-fill,minmax(min(330px,100%),1fr))`; same for the Saved grid.
3. `container-type: inline-size` on the card and a `@container` rule that stacks the primary
   action row below ~300px, so the card reacts to its column and not the viewport.
4. Fluid type: `clamp()` for the page `h1`s, panel `h2`s, and the `--gutter` used by section
   padding.
5. Touch: `@media (pointer:coarse)` floor already added in Phase 1 — verify every icon control
   picks it up; `overflow-wrap:anywhere` on job description / company text.

**Validate:** grep for `100vh` and bare `minmax(330px`; check no element sets a width larger than
`100%` at 320px.
**Commit:** "Frontend: fluid layout, container-aware cards, dvh, touch targets".

### Phase 5 — Accessibility and performance

1. `Esc` closes the topmost overlay; focus is stored on open and restored on close; `Tab` is
   trapped inside the topmost `[data-overlay]`.
2. `content-visibility:auto` + `contain-intrinsic-size: auto 420px` on grid cards.
3. `will-change` audited — only on the card and the slide-over, and not left on idle elements.
4. Contrast spot-check of the hover and disabled states introduced in this pass.

**Validate:** `tests/frontend/test_loading_states.py` grows assertions for the overlay/focus
wiring; re-run the accessibility-mobile checklist in `docs/skills/accessibility-mobile/SKILL.md`.
**Commit:** "Frontend: overlay focus management and render-cost guardrails".

### Phase 6 — Docs and the acceptance checklist

1. Add `docs/frontend-polish-spec.md` (the contract itself, so the repo owns it).
2. Update `docs/design-system.md` (motion tokens, the loading ladder, the signature moment),
   `docs/component-map.md` (new state keys and helpers), `docs/structure.md` (the new doc + test),
   `docs/checklist.md` (ledger row + any deferred item), and this plan with the outcome.
3. Report every line of spec §14 as pass / fail / N-A with the file and line that satisfies it.

**Commit:** "Docs: record the frontend polish pass". Then merge to `main` (no push).

## Deliverables

| File | Change |
| --- | --- |
| `utils/frontend/templates/index.html` | Motion tokens, base a11y layer, loading ladder, skeletons, error + retry, tokenized motion, animated exits, fluid/container-aware layout, focus management |
| `utils/frontend/static/js/dc-runtime.js` | `createPseudoSheet` gates `:hover` behind `@media (hover:hover) and (pointer:fine)` |
| `tests/frontend/test_loading_states.py` | New — pins the loading ladder, motion tokens, reduced motion, and overlay a11y wiring |
| `docs/frontend-polish-spec.md` | New — the contract |
| `docs/design-system.md`, `docs/component-map.md`, `docs/structure.md`, `docs/checklist.md` | Kept in sync in the same change |
| `docs/plans/frontend-polish-motion-loading.md` | This plan |

## Known baseline (not caused by this work)

`tests/docs/test_doc_links.py` fails 7 parametrizations in a fresh worktree because docs reference
gitignored runtime files (`config/*.json`, `data/daily_search_state.json`) that only exist after the
app has run. Unrelated to this change; left as-is.
