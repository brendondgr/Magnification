# Frontend Polish Spec — Motion, Loading, and Responsiveness

> **Status in Magnification:** adopted. This is the standing contract for any change to
> `utils/frontend/templates/index.html`. It was applied wholesale in
> `docs/plans/frontend-polish-motion-loading.md`, which also records the three places this
> repo deliberately deviates and why. The live tokens, the loading ladder, and the one
> signature motion moment are described in `docs/design-system.md`;
> `tests/frontend/test_loading_states.py` pins them. §4 (streaming LLM text) does not apply
> here — no endpoint streams tokens to the browser.

**Purpose:** This document is a *contract*, not inspiration. It is written to be pasted into the context of a coding agent (Claude Code, Cursor, an autonomous build agent) so that any UI it produces feels like a production-grade product rather than a scaffolded prototype.

**How to use it:**

- Paste the whole file into the agent's context, or drop it in the repo at `docs/frontend-polish-spec.md` and reference it in `CLAUDE.md` / `AGENTS.md` / your system prompt.
- Then give the agent a task like: *"Build/refactor `<component>` following `frontend-polish-spec.md`. Before you finish, run the Acceptance Checklist in §14 and report each line as pass/fail."*
- The agent should treat §1 (Quality Floor) as non-negotiable and everything else as the default it deviates from only with a stated reason.

**Assumed stack:** modern CSS (Baseline 2025–2026), any framework. React/Next-specific notes are marked. Nothing here requires an animation library; §12 says when to reach for one anyway.

---

## 1. The Quality Floor (non-negotiable)

An agent following this spec must never ship UI that violates these. If a requirement conflicts with a design request, surface the conflict rather than silently dropping the requirement.

1. **Every asynchronous operation has four rendered states:** `idle → loading → success → error`. A component that only renders the success state is incomplete. `empty` is a fifth state whenever the success payload can be a zero-length list.
2. **No layout shift on load.** Placeholders occupy the same box the real content will occupy. Reserve space for images (`width`/`height` attributes or `aspect-ratio`), fonts (`font-display: swap` + size-adjusted fallback), and async blocks. Target Cumulative Layout Shift < 0.1.
3. **Every interactive element has visible `:hover`, `:focus-visible`, `:active`, and `:disabled` states.** Focus rings are never removed without a replacement of equal or greater visibility.
4. **All motion respects `prefers-reduced-motion: reduce`.** Under reduce, transforms and parallax are removed; opacity cross-fades ≤ 100ms may remain. Content never becomes invisible or unreachable because motion was disabled.
5. **Animate only compositor-friendly properties:** `transform`, `opacity`, `filter`, `clip-path`. Never animate `width`, `height`, `top`, `left`, `margin`, or `padding` in a loop or on scroll.
6. **Responsive means fluid, not "has breakpoints."** Layout must survive any viewport from 320px to 2560px and any container width, with no horizontal overflow and no text smaller than 14px on mobile.
7. **Feedback within 100ms.** Any user action (click, tap, keypress) produces a visible change within 100ms even if the underlying work takes seconds. This is what "responsive to the user messing around with it" actually means.
8. **The revealed state is the default state.** Scroll and entrance animations are progressive enhancements layered *on top of* visible content. If JS fails or CSS is unsupported, everything is still visible and readable. Never write `opacity: 0` as a base style without a guaranteed mechanism to undo it.

---

## 2. Motion Token System

Define these once, globally, and reference them everywhere. Hard-coded durations scattered across components are the single most common cause of a UI feeling "off" — inconsistent timing reads as amateur even when each individual animation looks fine.

```css
:root {
  /* Durations — four steps, no improvising between them */
  --dur-instant: 80ms;   /* state flips: checkbox, toggle knob, tab underline  */
  --dur-fast:   140ms;   /* hover, focus, press, tooltip                        */
  --dur-base:   220ms;   /* dropdowns, accordions, small reveals                */
  --dur-slow:   340ms;   /* modals, drawers, page-level entrances               */
  --dur-ambient: 1200ms; /* shimmer loops, breathing indicators                 */

  /* Easing — the emotional register of the motion */
  --ease-out:  cubic-bezier(0.16, 1, 0.30, 1);   /* DEFAULT. enters, reveals   */
  --ease-in:   cubic-bezier(0.45, 0, 0.55, 1);   /* exits, dismissals          */
  --ease-soft: cubic-bezier(0.33, 1, 0.68, 1);   /* hover, small state changes */
  --ease-spring: linear(0, 0.42 12%, 0.87 24%, 1.05 36%, 1.01 60%, 1);
                                                  /* one overshoot, use sparingly */

  /* Distance — small. Big travel reads as cheap. */
  --lift-sm: 2px;
  --lift-md: 6px;
  --lift-lg: 14px;
}
```

### Timing rules

| Situation | Duration | Easing |
|---|---|---|
| Hover / focus / press | `--dur-fast` | `--ease-soft` |
| Element entering the viewport | `--dur-base` → `--dur-slow` | `--ease-out` |
| Element leaving / being dismissed | `--dur-fast` (≈60% of its entrance) | `--ease-in` |
| Modal, drawer, sheet | `--dur-slow` | `--ease-out` |
| Layout reflow (list reorder, filter) | `--dur-base` | `--ease-out` |

**Exits are always faster than entrances.** A dismissal that takes as long as an entrance feels like the interface is arguing with the user.

**Distance scales inversely with size.** A 40px button lifts 2px. A full-width card lifts 6px. A modal enters from 14px. Large elements moving large distances read as sluggish.

### Stagger (choreography)

When a group of items enters together, offset them by **40–60ms each, capped at ~8 items** (after that, everything remaining enters at the cap). Longer staggers on longer lists make the page feel slow, not elegant.

```css
.stagger > * {
  animation: rise var(--dur-base) var(--ease-out) backwards;
  animation-delay: calc(var(--i, 0) * 50ms);
}
@keyframes rise {
  from { opacity: 0; transform: translateY(var(--lift-md)); }
}
```

Set `--i` inline from the index. `backwards` fill mode means the element holds its start state during the delay instead of flashing at full opacity first — this detail is frequently missed and is exactly what makes a stagger look broken.

---

## 3. The Loading State Ladder

Do not use one loading pattern everywhere. Match the pattern to the *expected wait*, because the mismatch is what users read as unpolished. Recent UX guidance converges on roughly this staircase:

| Elapsed | Pattern | Rationale |
|---|---|---|
| 0–300ms | **Nothing.** Do not render an indicator. | A flashed-and-gone spinner is worse than no spinner. |
| 300ms–1s | Inline spinner **on the element that was acted on**, or a top progress bar for navigation. | Confirms the tap registered. |
| 1s–10s | **Skeleton** that mirrors the incoming layout. | Skeletons reduce *perceived* wait; spinners increase it. |
| >10s | **Determinate progress + status text** ("Indexing 3 of 12 documents…"). | Uncertainty, not duration, is what breaks tolerance. |
| Any duration, known outcome | **Optimistic UI** — render the result immediately, reconcile or roll back on response. | The fastest loading state is the one that never appears. |

### The 300ms delay gate (implement this; it is the highest-leverage single change)

```jsx
// React — only shows the indicator if the wait is actually perceptible
function useDelayedFlag(active, delay = 300) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!active) { setShow(false); return; }
    const t = setTimeout(() => setShow(true), delay);
    return () => clearTimeout(t);
  }, [active, delay]);
  return show;
}
```

### Skeleton rules

1. **A skeleton is a tracing of the real layout, not grey boxes.** Same number of lines, same widths, same gaps, same border radii. If the skeleton shows 3 cards and 7 arrive, you have broken the user's model of the page.
2. **Last line of a text block is shorter** (55–70%). Uniform-width bars read as fake.
3. **Shimmer must be a background-position or transform animation**, never a `width` animation.
4. **Skeletons must time out.** A shimmer that loops forever hides a failed request. Pair every skeleton with a timeout (10–15s) that swaps in an error state with a retry affordance.
5. `aria-busy="true"` on the container; the skeleton bars themselves are `aria-hidden="true"`.

```css
.skeleton {
  --skeleton-base: color-mix(in oklch, currentColor 8%, transparent);
  --skeleton-hi:   color-mix(in oklch, currentColor 16%, transparent);
  border-radius: 6px;
  background:
    linear-gradient(90deg, var(--skeleton-base) 0 40%, var(--skeleton-hi) 50%, var(--skeleton-base) 60% 100%)
    0 0 / 300% 100%;
  animation: skeleton-sweep var(--dur-ambient) linear infinite;
}
@keyframes skeleton-sweep { to { background-position: -150% 0; } }

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; background: var(--skeleton-base); }
}
```

Using `color-mix` against `currentColor` means the skeleton automatically works in light and dark mode with no second theme definition.

### Skeleton → content handoff

The swap is where polish is won or lost. Never hard-cut. Cross-fade the skeleton out while the content fades in over `--dur-base`, and keep the container height locked so nothing jumps.

```css
.content-enter {
  animation: content-in var(--dur-base) var(--ease-out) backwards;
}
@keyframes content-in {
  from { opacity: 0; transform: translateY(4px); }
}
```

### Images

Images are the most common source of jank. Required treatment:

```css
img { aspect-ratio: attr(width) / attr(height); }  /* or an explicit ratio */
.media { background: var(--skeleton-base); overflow: clip; }
.media img {
  opacity: 0;
  transition: opacity var(--dur-base) var(--ease-out);
}
.media img[data-loaded="true"] { opacity: 1; }
```

Set `data-loaded` on the `load` event (and check `img.complete` on mount, for cached images — otherwise cached images stay invisible, a very common bug). Use `loading="lazy"` and `decoding="async"` for below-fold media, and **never** for the LCP image.

### Error and empty states

- **Error:** state what failed, in the interface's voice, plus a retry control. Never a bare "Something went wrong."
- **Empty:** an invitation to act, with the primary action inline. Never a blank panel.
- Both should enter with the same `content-in` animation as success content, so failure feels like part of the system rather than a crash.

---

## 4. Streaming LLM Text

This is its own discipline; standard loading patterns do not apply well.

**State sequence:** `submitted → thinking → streaming → complete`, each visually distinct.

1. **Thinking phase (pre-first-token).** Show a lightweight indicator immediately — three pulsing dots or a shimmering placeholder line. Do not show a full skeleton; you do not know the length. If the model exposes intermediate status (tool calls, retrieval), stream *that* text; a status line that changes is far more tolerable than a static indicator.
2. **Chunk at the word or sentence boundary, not the character.** Character-by-character `setState` on a React tree causes a re-render per character and will drop frames on long responses. Buffer incoming deltas and flush on a rAF tick or every ~30–50ms.
3. **Fade in new text; never animate the container's height directly.** Wrap each newly-arrived chunk in a span with a short fade:
   ```css
   .tok { animation: tok-in 220ms var(--ease-out) backwards; }
   @keyframes tok-in { from { opacity: 0; filter: blur(2px); } }
   ```
   The blur-to-sharp transition is what makes streaming text feel deliberate rather than mechanical.
4. **Caret.** A 2px block caret at the tail during streaming, removed on completion. Blink at ~1s, and disable the blink under reduced motion.
5. **Sticky-bottom autoscroll with an escape hatch.** Auto-scroll to the bottom as tokens arrive *only while the user is already at the bottom*. The moment they scroll up, stop, and show a "Jump to latest" pill. Auto-scrolling a user who is reading earlier output is one of the most disliked behaviors in chat UIs. Modern CSS gives you most of this free:
   ```css
   .stream-viewport {
     overflow-anchor: none;          /* prevents fighting the browser's anchoring */
     scroll-behavior: smooth;
   }
   ```
   Detect "at bottom" with a tolerance of ~64px, not exact equality.
6. **Progressive markdown rendering.** Parse and render incrementally, but hold unterminated constructs (an open code fence, a half-written table) in a raw state until they close — otherwise the layout thrashes as the parser changes its mind. Render code blocks unhighlighted while streaming and syntax-highlight once on completion.
7. **Stop / regenerate controls appear the moment streaming starts,** not after it ends.
8. **Reserve the message box.** Give the assistant message container a `min-height` equal to a few lines so the composer does not jump the instant the first token lands.

---

## 5. Hover, Focus, and Press Micro-interactions

The goal is that every surface acknowledges the cursor. Cheap sites are static under the mouse.

**Layering:** a hover state usually changes *two* properties, not one — e.g. elevation + background, or translate + border color. One property reads as unfinished; four reads as noisy.

```css
.card {
  transition:
    transform  var(--dur-fast) var(--ease-soft),
    box-shadow var(--dur-fast) var(--ease-soft),
    border-color var(--dur-fast) var(--ease-soft);
  will-change: transform;   /* only on elements that actually animate often */
}

@media (hover: hover) and (pointer: fine) {
  .card:hover {
    transform: translateY(calc(-1 * var(--lift-sm)));
    box-shadow: 0 6px 24px -8px rgb(0 0 0 / 0.18);
  }
}

.card:active { transform: translateY(0) scale(0.995); transition-duration: var(--dur-instant); }

.card:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 3px;
}
```

**`@media (hover: hover)` is mandatory.** Without it, touch devices apply the hover state on tap and it sticks until the user taps elsewhere — a persistent, obviously-broken-looking artifact.

**Press feedback matters more than hover** because it is the only one that exists on touch. Every button gets a scale-down of 0.97–0.99 on `:active` at `--dur-instant`.

### Patterns worth implementing

- **Pointer-tracked highlight.** A radial gradient following the cursor within a card. Update CSS custom properties from a throttled `pointermove`, never inline styles on a re-render.
  ```css
  .glow::before {
    content: ""; position: absolute; inset: 0; opacity: 0;
    background: radial-gradient(240px circle at var(--mx) var(--my),
                rgb(255 255 255 / 0.08), transparent 70%);
    transition: opacity var(--dur-base) var(--ease-soft);
  }
  .glow:hover::before { opacity: 1; }
  ```
- **Magnetic buttons** (element translates slightly toward the cursor within a radius). Use on ≤2 elements per page; more is a gimmick.
- **Underline that grows from the origin**, using `scaleX` on a pseudo-element with `transform-origin: left`, reversing to `right` on exit.
- **Icon micro-motion** — arrow slides 2px on hover, chevron rotates 180° on expand. Cheap, and among the highest perceived-quality-per-line changes available.
- **Optimistic toggles** — the switch knob moves instantly; the network call reconciles afterward.

### Cursor-adjacent details

- `cursor: pointer` on anything clickable that is not a link or button element.
- `user-select: none` on button labels so double-clicks don't select text.
- Disabled states get `cursor: not-allowed`, reduced opacity, and **no** hover transform.

---

## 6. Scroll Behavior

Use **CSS scroll-driven animations** as the default. As of 2026 they are supported in Chrome/Edge, Safari 18+/26, and are an Interop priority for Firefox, with roughly mid-80s to 90% global support depending on the measure. They run on the compositor rather than the main thread, so they do not jank when the page is busy — which is the exact failure mode of `IntersectionObserver` + JS scroll listeners on a heavy page.

**The failure mode is "no animation," not "broken page"** — which is why the base style must be the revealed state.

### Reveal on scroll (zero JS)

```css
.reveal { /* base = final state. Always visible without support. */ }

@supports (animation-timeline: view()) {
  @media (prefers-reduced-motion: no-preference) {
    .reveal {
      animation: reveal-in linear both;
      animation-timeline: view();
      animation-range: entry 10% cover 32%;
    }
  }
}
@keyframes reveal-in {
  from { opacity: 0; transform: translateY(var(--lift-lg)); }
  to   { opacity: 1; transform: none; }
}
```

- `view()` = a timeline driven by the element's own progress through the viewport.
- `animation-range: entry 10% cover 32%` = start when the element is 10% into entering, finish by the time it is 32% through covering the viewport. Tune these two numbers rather than adding delays.
- When `animation-timeline` is set, `animation-duration` is **ignored** — scroll position drives the whole timeline. This trips people up constantly.

### Scroll progress bar

```css
.progress {
  position: fixed; inset-block-start: 0; inset-inline: 0; height: 3px;
  transform-origin: left; transform: scaleX(0);
  background: var(--accent);
  animation: grow linear both;
  animation-timeline: scroll(root block);
}
@keyframes grow { to { transform: scaleX(1); } }
```

### Parallax

```css
.parallax-layer {
  animation: drift linear both;
  animation-timeline: view();
  animation-range: cover;
}
@keyframes drift { from { translate: 0 -8%; } to { translate: 0 8%; } }
```

Keep parallax travel under ~10% of the element height. Anything more reads as a 2014 landing page.

### Sticky headers that respond to scroll state

Use scroll-state container queries where available, or a single `IntersectionObserver` on a 1px sentinel element (not a scroll listener) to toggle a `data-stuck` attribute, then transition padding/backdrop off that attribute.

### When to still use JS

Reach for `IntersectionObserver` or GSAP ScrollTrigger only for: pinned sections with scrubbed timelines, physics-based motion, complex multi-element choreography, or when you must support the long tail of older browsers as the *primary* experience rather than a fallback.

### Section transitions

- `scroll-behavior: smooth` on `:root`, wrapped in `prefers-reduced-motion: no-preference`.
- `scroll-margin-block-start` on anchor targets equal to sticky header height, so deep links don't land under the header.
- Consider `scroll-snap-type: y proximity` (not `mandatory` — mandatory traps users on long sections).

---

## 7. Page and Route Transitions

### Multi-page / server-rendered

```css
@view-transition { navigation: auto; }

::view-transition-old(root) { animation: fade-out var(--dur-fast) var(--ease-in) both; }
::view-transition-new(root) { animation: fade-in  var(--dur-base) var(--ease-out) both; }
```

Same-document view transitions reached Baseline in 2025; cross-document (MPA) support is still filling in, so treat it as enhancement. Persist a shared element across routes by giving it a matching `view-transition-name` on both pages.

### Single-page apps

```js
if (!document.startViewTransition) { update(); return; }
document.startViewTransition(() => update());
```

### Entrance animations from `display: none`

`@starting-style` removes the old JS timing hacks (the double-rAF dance) for animating an element in as it is added to the DOM:

```css
dialog[open] {
  opacity: 1; transform: scale(1) translateY(0);
  transition: opacity var(--dur-base) var(--ease-out),
              transform var(--dur-base) var(--ease-out),
              overlay var(--dur-base) allow-discrete,
              display var(--dur-base) allow-discrete;
}
@starting-style {
  dialog[open] { opacity: 0; transform: scale(0.97) translateY(8px); }
}
```

`allow-discrete` on `display` and `overlay` is what lets the *exit* animate too — without it the dialog vanishes instantly on close.

### First-paint sequence

The page-load choreography should be short and hierarchical: header → hero headline → hero sub/CTA → first content band. Total under ~600ms. Anything longer and the user is waiting on decoration. Never animate in content that is already above the fold and already loaded — that is self-inflicted latency.

---

## 8. Responsiveness

"Responsive" here means two separate things; implement both.

### 8a. Layout responsiveness

**Container queries are the default; media queries are for page-level layout only.** A card that changes shape based on the viewport is broken the moment you put it in a sidebar.

```css
.card-wrap { container-type: inline-size; container-name: card; }

@container card (min-width: 480px) {
  .card { grid-template-columns: 180px 1fr; }
}
```

**Fluid type and spacing instead of stepped breakpoints:**

```css
:root {
  --step-0: clamp(1rem, 0.95rem + 0.25vw, 1.125rem);
  --step-1: clamp(1.25rem, 1.1rem + 0.75vw, 1.75rem);
  --step-3: clamp(2rem, 1.4rem + 3vw, 4rem);
  --gutter: clamp(1rem, 4vw, 3rem);
}
```

**Intrinsic layouts that need no breakpoints at all:**

```css
.auto-grid {
  display: grid;
  gap: var(--gutter);
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
}
```

The `min(260px, 100%)` prevents overflow at 320px — a bare `minmax(260px, 1fr)` breaks on small phones.

**Required checks:** 320px width with no horizontal scroll; `dvh` not `vh` for full-height sections (mobile browser chrome); `overflow-wrap: anywhere` on user-generated text; tables either scroll in a container or restack; touch targets ≥ 44×44px.

### 8b. Interaction responsiveness (perceived)

- Visible feedback ≤ 100ms on every input (see §1.7).
- Keep INP (Interaction to Next Paint) under 200ms. The usual culprits: unthrottled scroll/resize handlers, re-rendering a large list on every keystroke, and synchronous work in an event handler that should be deferred.
- Debounce *input*, throttle *scroll/pointer*, and use `requestAnimationFrame` for anything that writes to the DOM.
- Show the result of a filter/search immediately over the already-loaded set, then reconcile with the server response.

---

## 9. Accessibility Floor

Motion and accessibility are not in tension; skipping this is what makes a site fail an audit despite looking good.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

Use this global reset as a safety net, but prefer per-component reduced-motion handling that keeps a short opacity fade — the blanket reset removes all continuity and can be more disorienting than a gentle cross-fade.

Also required:

- `:focus-visible` styles on every interactive element; a skip-to-content link as the first focusable node.
- `aria-busy="true"` on loading containers; `aria-live="polite"` on regions that update asynchronously (including streaming text — announce on completion, not per token, or the screen reader will be unusable).
- Focus trapped in modals, returned to the trigger on close, with `Esc` to dismiss.
- Contrast ≥ 4.5:1 for body text, ≥ 3:1 for UI boundaries and large text. Check the *hover* and *disabled* states too, which is where contrast usually fails.
- Nothing flashes more than 3 times per second.
- Animation never carries information that is not also available statically.

---

## 10. Performance Guardrails

Polish that costs frames is not polish.

- **Compositor-only properties** in anything that runs continuously (see §1.5).
- `will-change` only on elements that animate frequently, and remove it after. Applying it broadly creates layers that consume memory and can *reduce* performance.
- `content-visibility: auto` with `contain-intrinsic-size` on long off-screen sections.
- Limit simultaneous scroll-driven animations. Compositor animations are fast, not free — dozens on one page will still cost you.
- Fonts: `font-display: swap`, preload the one display face, and use `size-adjust`/`ascent-override` on the fallback so the swap doesn't shift layout.
- Test on a throttled CPU (4–6× slowdown) — this is where "looks fine on my M-series laptop" animations fall apart.
- Budget: LCP < 2.5s, CLS < 0.1, INP < 200ms.

---

## 11. Anti-patterns (reject these on sight)

| Anti-pattern | Why it fails |
|---|---|
| Full-page spinner blocking the whole route | Hides layout information the user could already be reading |
| Skeleton whose shape ≠ real content | Breaks trust the instant real content lands |
| Infinite shimmer with no timeout | Hides errors indefinitely |
| Spinner for a 150ms request | Flashes; feels *slower* than showing nothing |
| Animating `width`/`height`/`top`/`left` | Layout thrash, dropped frames |
| Hover effects without `@media (hover: hover)` | Sticky states on touch devices |
| `opacity: 0` base with JS-only reveal | Blank page if the script fails |
| Stagger delays > 500ms cumulative | Reads as slow, not choreographed |
| Removing `outline` with no replacement | Keyboard users lose their place |
| Auto-scrolling while the user is reading above | Actively hostile |
| Custom scroll-jacking / smooth-scroll libraries | Breaks find-in-page, accessibility, and native scroll feel |
| Everything animating on every page | Noise; the eye has nowhere to rest |
| Parallax > 10% travel, or on mobile | Nausea trigger, and it looks dated |

**The restraint rule:** pick *one* signature motion moment per page. Everything else is quiet, fast, and functional. A page where everything moves reads as AI-generated; a page with one deliberate flourish and disciplined micro-interactions reads as designed.

---

## 12. When to Add a Library

Default to the platform. As of 2026, native View Transitions plus CSS scroll-driven animations cover most of what JS animation libraries were used for, at zero bundle cost — teams migrating off `framer-motion` for these specific use cases report meaningful bundle and LCP wins.

Add a library only for:

- **Motion/Framer Motion** — layout animations (`layoutId` shared-element transitions), gesture-driven drag, spring physics, orchestrated exit animations in React trees where `@starting-style` isn't enough.
- **GSAP + ScrollTrigger** — pinned scrubbed sections, complex multi-element timelines, broad legacy browser support as the primary path.
- **Lottie** — designer-authored vector animations. Watch the payload.
- **Tailwind** — if used, put the tokens from §2 in `@theme` and reference them; don't scatter `duration-[220ms]` arbitrary values.

Do not add a library for: fades, hover states, reveals on scroll, progress bars, accordions, or modals. All are one-to-ten lines of CSS now.

---

## 13. Component-by-Component Requirements

The agent should be able to answer "what does polish mean for X" without asking:

- **Buttons** — hover (2 properties), active scale, focus ring, disabled, and a `loading` variant where the spinner replaces the label *without changing the button's width*.
- **Inputs** — focus ring, label float or persistent label, inline validation on blur (never on every keystroke), error text that animates in without shifting the field below it.
- **Cards** — hover lift + shadow + border shift, whole-card click target, skeleton variant that matches exactly.
- **Modals/Drawers** — backdrop fade, content scale/slide via `@starting-style`, focus trap, `Esc`, scroll lock on body, animated exit.
- **Dropdowns/Menus** — origin-aware transform (`transform-origin` at the trigger corner), `--dur-base` in, `--dur-fast` out, keyboard navigation.
- **Toasts** — slide + fade in, auto-dismiss with a visible progress indicator, pause on hover, stack with position transitions.
- **Tabs** — an underline that *slides* between tabs rather than cutting; content cross-fades.
- **Accordions** — animate with `grid-template-rows: 0fr → 1fr` (or `interpolate-size: allow-keywords` + `height: auto` where supported), never a hardcoded max-height.
- **Tables** — row hover, sticky header, skeleton rows, empty state, horizontal scroll with a fade affordance at the edges.
- **Lists/feeds** — staggered entrance, animated reorder on filter, skeleton items, empty state, infinite-scroll sentinel with its own loading row.

---

## 14. Acceptance Checklist

The agent must self-verify each line and report pass/fail before declaring the task complete.

**States**
- [ ] Every async component renders idle / loading / success / error / empty
- [ ] No indicator appears for waits under 300ms
- [ ] Skeletons structurally mirror real content and time out into an error state
- [ ] Images reserve space and fade in, including from cache

**Motion**
- [ ] All durations/easings come from tokens; no hardcoded values
- [ ] Exits are faster than entrances
- [ ] Only `transform`/`opacity`/`filter`/`clip-path` are animated
- [ ] Cumulative stagger under 500ms
- [ ] Exactly one signature motion moment on the page

**Interaction**
- [ ] Hover, focus-visible, active, and disabled on every interactive element
- [ ] Hover effects gated behind `@media (hover: hover)`
- [ ] Visible feedback within 100ms of every input

**Scroll**
- [ ] Reveal animations use `animation-timeline: view()` behind `@supports`
- [ ] Base styles are the revealed state; content visible without JS/CSS support
- [ ] Anchor targets have `scroll-margin` clearing the sticky header

**Responsive**
- [ ] No horizontal overflow at 320px
- [ ] Components use container queries, not viewport queries
- [ ] Type and spacing are fluid (`clamp`)
- [ ] Touch targets ≥ 44×44px
- [ ] `dvh` used for full-height sections

**Accessibility**
- [ ] `prefers-reduced-motion` honored everywhere
- [ ] `aria-busy` on loaders, `aria-live` on async regions
- [ ] Focus visible, trapped in modals, restored on close
- [ ] Contrast passes in default, hover, and disabled states

**Performance**
- [ ] CLS < 0.1, INP < 200ms, LCP < 2.5s on a 4× throttled CPU
- [ ] No unthrottled scroll or pointer listeners
- [ ] `will-change` scoped and removed after use

---

## 15. Drop-in Prompt for the Agent

> Read `frontend-polish-spec.md` in full before writing code.
>
> Task: `<describe the page or component>`
>
> Requirements:
> 1. Implement the motion token system from §2 in the global stylesheet before anything else. Reuse it; do not hardcode durations.
> 2. Every async boundary gets the full state ladder from §3, including the 300ms delay gate.
> 3. Use CSS scroll-driven animations (§6) for reveals, behind `@supports` and `prefers-reduced-motion`, with the revealed state as the base style.
> 4. Components respond to their container (§8a), not the viewport.
> 5. Pick exactly one signature motion moment and justify it in one sentence. Everything else stays quiet.
> 6. Before finishing, run the §14 Acceptance Checklist and report each line as pass/fail with the file and line where it is satisfied. Do not claim a pass you have not verified.
>
> If any requirement conflicts with the design brief, stop and say so rather than silently dropping it.

---

## Appendix: Global Base Stylesheet

Paste this once per project.

```css
@layer reset, tokens, base, components, utilities;

@layer tokens {
  :root {
    --dur-instant: 80ms;  --dur-fast: 140ms;
    --dur-base: 220ms;    --dur-slow: 340ms;   --dur-ambient: 1200ms;
    --ease-out:  cubic-bezier(0.16, 1, 0.30, 1);
    --ease-in:   cubic-bezier(0.45, 0, 0.55, 1);
    --ease-soft: cubic-bezier(0.33, 1, 0.68, 1);
    --lift-sm: 2px; --lift-md: 6px; --lift-lg: 14px;
    --gutter: clamp(1rem, 4vw, 3rem);
  }
}

@layer base {
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }

  @media (prefers-reduced-motion: no-preference) {
    html { scroll-behavior: smooth; }
  }

  body { text-wrap: pretty; overflow-wrap: break-word; }
  h1, h2, h3 { text-wrap: balance; }

  :where(a, button, input, select, textarea, [tabindex]):focus-visible {
    outline: 2px solid var(--focus, currentColor);
    outline-offset: 3px;
    border-radius: 3px;
  }

  :where(img, video, svg) { max-width: 100%; height: auto; display: block; }

  [aria-busy="true"] { cursor: progress; }

  :where(section, [id]) { scroll-margin-block-start: var(--header-h, 5rem); }
}

@layer utilities {
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
}
```
