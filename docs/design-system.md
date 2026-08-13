# Design System — Magnification

The design-quality brief required by `docs/skills/website-architecture/SKILL.md`. The live tokens
live in two places inside `utils/frontend/templates/index.html`, and there are no external
stylesheets:

| Token family | Where | Pinned by |
| --- | --- | --- |
| Color + shape (per theme) | the `Component.THEMES` maps | `tests/frontend/test_theme_tokens.py` |
| Motion, focus, fluid type (theme-independent) | the `:root` block in the `<helmet>` `<style>` | `tests/frontend/test_loading_states.py` |

Keep this file in sync with both. `docs/frontend-polish-spec.md` is the standing contract for
motion, loading, and responsiveness; the sections below record how this app satisfies it.

## Visual Motif

A job board that wears the brand mascot's colors — a personal cockpit for hunting and tracking jobs, not a generic SaaS dashboard. Both themes derive from the penguin logo's four color families (deep navy, beak orange, handle gray, belly off-white), so the UI and the mark read as one brand. Playful but focused; spring-like hover lift on interactive cards. Avoid generic AI-site patterns (vague productivity copy, glowing gradients, abstract orbs, fake metrics, repeated identical feature-card grids).

## Brand Mark

The logo is a penguin peering through a magnifying glass — the app's "look closer at every
listing" idea, drawn playfully rather than as a generic search glyph. Source of truth:
`images/magnify.svg` (with a raster twin, `images/magnify.png`). The browser-served copy is
`utils/frontend/static/img/magnify.svg`.

Where it appears:

- **Favicon** — `<link rel="icon" type="image/svg+xml">` on the SVG, with `favicon-32.png` and
  `apple-touch-icon.png` (both generated from `images/magnify.png`) as fallbacks.
- **Header lockup** — replaces the former `J` chip to the left of the "Magnification /
  Track · Apply · Land" wordmark. The mark keeps its own **36px, 9px-radius, `#F7F6F5`** chip
  rather than sitting on `var(--surface)`: the penguin's body is near-black navy, which would
  lose its outline on the dark `midnight` theme. The fixed near-white chip (the logo's own
  white, which is also `arctic`'s surface color) plus a `var(--border)` hairline keeps contrast
  identical in both themes.
- **README** — centered above the title.

The mark's artboard is 1081 × 1170 (taller than wide), so scale it by **height** with
`width:auto`; never set both dimensions to the same value.

## Color Tokens

The live palette is the two theme maps in **Live Themes** below. Every color in the UI comes from
one of those tokens or from the two fixed palettes described here.

**Source palette** (`Component.SITE_COLORS`): one brand color per job board for the source badge —
LinkedIn `#0A66C2`, Indeed `#2557A7`, Glassdoor `#0CAA41`, ZipRecruiter `#3A7D34`, Google `#EA4335`.

**Industry palette** (`Component.INDUSTRY_COLORS` in `index.html`): one fixed, distinct color per
industry label so the job-card industry pill reads consistently everywhere (all "Health" pills
share one color, etc.) — Tech `#00C2FF`, Health `#00E5A0`, Finance `#FFC53D`, Business `#B57BFF`,
Industrial `#FF8A3D`, Science `#4DD4FF`, Education `#FF5DA2`, Government `#7C9CFF`, Retail
`#FF4D6A`, Media `#FF6AD5`, Legal `#C0A16B`, Energy `#7CFC5A`, Other `#9AA0A6` (fallback for
unknown/unclassified). The pill uses the color as border + text over a 12%-tinted fill (a colored
variant of the location-chip style); labels must match the backend `INDUSTRIES` taxonomy. The
pill sits **right-justified in the card's first row**, opposite the source badge. These vivid
values are tuned for dark surfaces; on the light `arctic` theme, `decorate()` mixes each with
navy (`color-mix(… 58%, #132433)`) for pill text/border so contrast holds, while the small
color dot keeps the vivid original on both themes.

**Job-card row rhythm.** The card reads as five information rows before its two action rows:
source ‖ industry · title · company + `(YYYY-MM-DD)` ‖ match % · location ‖ compensation ·
description. Each paired row is a flex row where the left item takes the remaining width
(`flex:1;min-width:0`, ellipsized) and the right item is intrinsic (`flex:0 0 auto`), so long
titles, company names, and locations truncate instead of pushing their counterpart off the
card. Text is clamped, never allowed to reflow the grid: the title at **2 lines** and the
description at **4** (`-webkit-line-clamp`). A job with no usable pay shows **"Not Specified"**
in `--muted` rather than the pay-green `--c-offer-text`, so an absent salary never reads as a
value.

## Typography

Fonts are theme tokens, not classes — every rule sets `font:` with one of them inline.

- Headings (`--font-head`): **Space Grotesk** on `midnight`, **Newsreader** on `arctic`
- Body (`--font-body`): **Archivo**, both themes
- Numeric / label / metadata (`--font-mono`): **JetBrains Mono**, both themes
- Body text ≥ 16px on mobile (per `docs/skills/accessibility-mobile/SKILL.md`).

## Surfaces, Radius, Shadow, Motion

### Live Themes (logo-derived)

Two themes, both built from the logo's palette, replace the former `editorial`/`neon` pair.
`tests/frontend/test_theme_tokens.py` pins this contract.

| Token | `arctic` (light, default) | `midnight` (dark) |
| --- | --- | --- |
| `--bg` | `#E9EDF1` | `#0C1826` |
| `--surface` / `--surface2` | `#F7F6F5` / `#FFFFFF` | `#132433` / `#1B3145` |
| `--card` | `#FCFBFA` | `#172B3C` |
| `--text` / `--muted` | `#132433` / `#5B6B7A` | `#F7F6F5` / `#8CA0B3` |
| `--border` / `--border2` | `#D7DEE5` / `#B7C3CE` | `#24394E` / `#35506A` |
| `--accent` (beak orange) | `#F4A226` | `#F4A226` |
| `--accent-ink` | `#132433` | `#132433` |
| `--accent-text` | `#985C07` (darkened for contrast on light) | `#F4A226` |
| `--danger` | `#B23B36` | `#F26D6D` |

Rules encoded in the tokens:

- **Orange is the shared accent.** `--accent` is the logo's beak orange in both themes; text on
  an accent fill is always navy (`--accent-ink`), never white — white-on-orange fails contrast.
  Orange used *as text* on the light theme goes through the darkened `--accent-text`.
- **Midnight lives inside the logo.** Its surfaces are the penguin's own navy (`#132433`), its
  text the belly off-white.
- **Destructive red is a token.** All destructive/error styling (Clear/Block buttons, ignored
  cards, failure chips, low-match text) uses `var(--danger)` (hover tints via
  `color-mix(… 12%, transparent)`); the old hardcoded `#E5484D` is retired. Solid `--danger`
  chips pair with `color:var(--surface)` so the text works in both themes.
- **The header and sidebar are always midnight.** The sticky header and the desktop sidebar
  re-declare the theme custom properties inline (`--surface:#132433`, `--text:#F7F6F5`, …) plus
  `color:var(--text)` so the app chrome wears the logo's navy in both themes — on `arctic` the
  dark banner and rail frame the light content; on `midnight` they match the page. Because the
  override re-scopes the `var()` lookups (and re-resolves inherited text color) for the whole
  subtree, the nav tabs, header buttons, theme switch, pipeline counts, and Clear Database
  button restyle automatically; the accent stays the shared beak orange. The header also pins
  `--font-head` to Space Grotesk so the wordmark keeps one typeface across themes (`--font-head`
  is otherwise per-theme: Newsreader serif on `arctic`). `color:var(--text)`
  on the scoping element is load-bearing: text without an explicit color otherwise inherits
  the page theme's computed color from the root, not the scoped navy palette.
- **Only colors differ between themes.** The shape tokens are identical in both themes —
  `--radius:12px`, `--r-sm:8px`, `--bw:1px` — and the header pins its heading font, so toggling
  never morphs corners, border weights, or chrome typography, it only recolors. (Content
  headings still switch `--font-head` — Newsreader on `arctic`, Space Grotesk on `midnight` —
  the one deliberate non-color difference.) Pinned by
  `test_shape_tokens_identical_across_themes`.
- **Theme toggle.** A `role="switch"` pill (sun/moon knob) sits right of the **Options** button
  in the header (desktop-only, `data-desk`, 62×38px). It flips `arctic`⇄`midnight` and persists
  to `localStorage['magnify.theme']`; the Component constructor restores the saved value
  (unknown/legacy names fall back to `arctic`).

### Motion tokens

Durations and easings are **never** hardcoded in an inline style — every one references a token
from the `:root` block. Four duration steps, no improvising between them:

| Token | Value | Used for |
| --- | --- | --- |
| `--dur-instant` | 80ms | state flips (check marks, toggle knobs) |
| `--dur-fast` | 140ms | hover, focus, press — and **every exit** |
| `--dur-base` | 220ms | small reveals, the skeleton→content handoff, scrims |
| `--dur-slow` | 340ms | modals, slide-over panels |
| `--dur-ambient` | 1200ms | the skeleton shimmer and the live-status pulse (the spinner runs at 60% of it) |
| `--ease-out` / `--ease-in` / `--ease-soft` | — | entrances / exits / hover |
| `--lift-sm` `--lift-md` `--lift-lg` | 2 / 6 / 14px | travel distance, scaled inversely to element size |
| `--stagger-step` | 45ms | per-item entrance offset, capped at 8 items |
| `--focus` | `#F4A226` | the focus ring, readable on both themes and on the navy chrome |
| `--gutter` `--step-h1` `--step-h2` | `clamp()` | fluid spacing and headings |

**Exits are always faster than entrances.** `closeWithExit(key, commit)` sets `state.closing`,
the overlay renders its mirrored `-out` keyframes for `--dur-fast`, and only then does the state
change that unmounts it commit. Under `prefers-reduced-motion` the delay is skipped entirely.

### The loading ladder

Every async region renders **idle → loading → success → error**, plus **empty** where the payload
can be a zero-length list. The rules, all enforced in the component:

- **Nothing renders for the first 300ms** (`Component.SKELETON_DELAY`). A flashed-and-gone
  placeholder reads worse than no placeholder at all.
- **Skeletons trace the real layout** — the job-card skeleton has the same seven rows at the same
  widths, gaps, and radii, with a short final description line. Built once in
  `skeletonJobCard()` / `skeletonTrackerCards()` / `skeletonFields()` so the call sites cannot
  drift from each other.
- **Skeletons time out** (`Component.LOAD_TIMEOUT`, 15s) into the error state, so a shimmer can
  never loop forever over a dead request.
- **A skeleton only stands in for absent content.** A refetch over data already on screen keeps
  the data.
- **Empty states are gated on `jobsState === 'ready'`**, never inferred from a zero count, and
  split into "no results for that search" (offering *Clear search*) and "nothing yet" (offering
  *Find Jobs*).
- **Errors say what failed and offer the retry inline.** Never a bare toast.
- `aria-busy` on every loading container, `aria-hidden` on the bars themselves, `aria-live="polite"`
  on the status region and all three activity feeds.
- The three genuinely slow buttons (Analyze matches, Build Profile, Test connection) have a
  fixed-`min-width` loading variant where a spinner replaces the icon. Fast saves get **no**
  indicator — they finish inside the 300ms gate.

### The signature motion moment

One per page: the **skeleton → cards handoff**. The skeleton grid cross-fades out and the real
cards rise in on `.jf-in` with a 45ms stagger capped at 8 items (`--i` set from the render index).
It is the moment the app's actual content arrives, so it is the one worth choreographing.
Everything else is quiet: hover tints, 2px lifts, 140ms exits.

### Scroll and route

- `.jf-reveal` (Tracker cards, the detail panel's long sections) uses
  `animation-timeline: view()` behind `@supports` and `prefers-reduced-motion`. **The base style is
  the revealed state**, so unsupported browsers simply show the content.
- Tab changes run through `document.startViewTransition` (with `ReactDOM.flushSync`) where the API
  exists, styled by `::view-transition-old/new(root)` on the same exit-faster-than-entrance rule.

### Keyframes and the hover vocabulary

- **Entrance keyframes** (defined once in `index.html`'s `<style>`): `jf-fade` (opacity),
  `jf-slide` (slide-in from the right, used by slide-over panels), `jf-pop` (scale+rise, used by
  modals and chips), `jf-pulse` (used by the live-status dot), `jf-rise` (rise+fade, used by the
  toast). Each has a mirrored exit — `jf-fade-out`, `jf-slide-out`, `jf-pop-out` — plus
  `jf-skeleton-sweep`, `jf-content-in`, `jf-spin`, and `jf-reveal-in` for the loading and reveal
  utilities.
- **Hover/active/focus:** the dc-runtime template compiles any `style-<pseudo>` attribute
  (`style-hover`, `style-active`, `style-focus`, …) on an element into a real inserted stylesheet
  rule and merges the generated class onto that element — see `collectProps`/`createPseudoSheet`
  in `utils/frontend/static/js/dc-runtime.js`. **Local patch:** `createPseudoSheet` wraps every
  generated `:hover` rule in `@media (hover:hover) and (pointer:fine)`, so a tap on a touch device
  can never leave a hover state stuck on. The `[data-tip]` tooltip is gated the same way. Every interactive element pairs a `transition:`
  in its base `style` with a `style-hover` (and `style-active`/`style-focus` where relevant)
  attribute; identical hover CSS across elements is deduped into one shared class automatically.
- **Motion vocabulary** (small, reused everywhere, all values expressed via the theme tokens
  above so both themes stay correct by construction):
  - **Primary/accent buttons** (Applied, Find Jobs, Start Search, Save…, Analyze matches):
    `translateY(calc(-1 * var(--lift-sm)))` + `filter:brightness(1.06)` on hover, `translateY(0)` +
    `brightness(.97)` on active/press — `var(--dur-fast) var(--ease-soft)`.
  - **Secondary/bordered buttons**: hover tints `background`/`border-color` toward
    `var(--surface2)`/`var(--border2)`.
  - **Icon-only square buttons** (panel close, ignore, remove): `background:var(--surface2)` +
    a slight `scale(1.06)` press on active.
  - **Cards** (New Jobs grid article, Tracker kanban job card): `translateY(calc(-1 * var(--lift-sm)))`
    + `box-shadow:var(--shadow)` on hover — the same treatment on both card types.
  - **Pills/tabs/toggle rows** (nav tabs, Options tabs, site/job-type pills, toggle rows, mobile
    nav): background/border tint on hover, no movement — the selected state already carries the
    color change.
  - **Chip remove "×" buttons**: `opacity` 0.7/0.8 → 1 + `scale(1.1)`.
  - **Range sliders**: `filter:brightness(1.1)` on hover (native thumb; no custom track styling).
  - **Text inputs** (search, Options endpoint fields, number fields): `border-color:var(--accent)`
    + a soft `box-shadow` ring on focus.
  - **Clickable rows** (job-detail timeline steps): background tint (`var(--bg)`) on hover, no
    movement.
- **Hover tool-descriptor** (job-card icon action row): a custom tooltip via a pure-CSS
  `[data-tip]` rule in the `<head>` `<style>` block — `::after` renders `attr(data-tip)` as a
  small `var(--text)`-on-`var(--card)` bubble above the control on `:hover`/`:focus-visible`, with
  a matching `::before` caret. Both are `pointer-events:none` so they never intercept the click
  (the button stays fully selectable); each button also carries an `aria-label` for screen readers.
- Radius follows the `--radius`/`--r-sm` tokens (now identical across themes); standardizing
  further shared spacing tokens is a follow-up.

## Iconography

No icon library is loaded. Every icon is an inline SVG built with `React.createElement` — 24×24
viewBox, `fill:none`, `stroke:currentColor`, `strokeWidth:2` — so icons inherit the surrounding
token color in both themes. Keep new icons to that same shape and stroke weight.

## Domain Vocabulary (UI copy)

Use concrete job-hunt terms: *New Jobs*, *Tracker*, *Applied / Interviewing / Offers / Rejected / Ghosted*, *Find Jobs*, *Ignore*, *job detail*, *compensation*, *location*, *source/board*. Avoid generic phrases like "boost productivity" or "all-in-one platform."

## Required UI States

Every view must design: **loading, empty, partial-data, error, success,** and **permission** (n/a — single user) states. Concrete states are enumerated per view in `docs/routes.md`, and the mechanics are **The loading ladder** above. A view that only renders its success state is incomplete.

## Mobile-Specific Decisions

- Bottom tab nav (built inline by `mkMobTab` in `index.html`) on small screens; top tabs + sidebar
  on desktop.
- **Container queries, not viewport queries, for components.** The job card sets
  `container-type:inline-size`, so it reshapes for the column it lands in (its action row stacks
  under 320px, its icon row wraps under 260px) rather than guessing from the window. Viewport
  media queries are reserved for page-level layout: the `data-desk`/`data-mob` chrome swap at
  880px and the Application-Mode pane switch at 920px.
- Fluid over stepped: grid tracks are `minmax(min(330px,100%),1fr)` (a bare 330px track overflows
  below ~362px), headings use the `clamp()` type tokens, and full-height sections use `dvh`.
- Reading text (card title and description) holds a 14px floor on phones. The mono badges, chips,
  and dates keep their designed size — growing them would break the card's row rhythm pinned
  above; that is a deliberate deviation from §1.6 of `docs/frontend-polish-spec.md`.
- Touch controls reach 44×44px through a `@media (pointer:coarse)` floor rather than by inflating
  the desktop density.
- Single-column card flow on mobile; multi-column grid / kanban on wider viewports.
- Tap targets ≥ 44×44px; the job-detail slide-over and modals must not trap focus or hide the active input behind the mobile keyboard.

## Recommendation Match Surfaces

- **Match badge** (New Jobs cards): `NN% match`, color-graded — offer green (≥66%),
  accent orange (≥40%), danger red (<40%), all via theme tokens. Shown only when a job has
  been analyzed.
- **Profile Match panel** (job detail): the score, per-signal bars (semantic/keyword/BM25/skill),
  matched skills (offer-tinted chips) vs missing skills (muted chips), matched keyword groups,
  and the LLM rationale when present.
- States: **not-analyzed** (no badge; "Analyze matches" CTA), **analyzing** (toast + disabled
  button), **analyzed** (badges + sortable by match), **no-profile** (analyze prompts to create one).

## Anti-Generic Checklist

- Show real job data (title, company, comp, location, source) prominently — not placeholder marketing.
- Use the categorization palette meaningfully (tags/status), not as decoration.
- Keep copy specific to job hunting.
