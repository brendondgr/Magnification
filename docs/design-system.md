# Design System — Magnification

Captured from `utils/frontend/static/css/variables.css` and the inline Tailwind config in `index.html`. This is the design-quality brief required by `docs/skills/website-architecture/SKILL.md`. Keep tokens here in sync with `variables.css`.

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

| Token | Value | Use |
| --- | --- | --- |
| `--color-primary` | `#FF6B6B` Electric Coral | Primary actions, accents |
| `--color-secondary` | `#4C3BCF` Deep Indigo | Secondary emphasis |
| `--color-tertiary` | `#00D9C0` Vivid Teal | Tertiary highlights |
| `--color-bg-base` | `#FEFBF6` Warm Off-White | Page background |
| `--color-bg-surface` | `#FFF8F0` Soft Cream | Surfaces / panels |
| `--color-bg-elevated` | `#FFFFFF` | Elevated cards |
| `--color-text-main` | `#1f2937` | Primary text |
| `--color-text-muted` | `#64748b` | Secondary text |

Plus a large **categorization palette** (`--color-cat-*`: yellow-orange, yellow, orange, red, blue, purple, teal, green, black, gray, brown, pink, kiwi, rose) — each with `bg` / `border` / `text` triplets used for job tags and status chips.

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

- Headings: **Space Grotesk** (`.font-heading`)
- Body: **DM Sans** (`.font-body`)
- Mono / metadata: **JetBrains Mono** (`.font-mono-custom`)
- Body text ≥ 16px on mobile (per `docs/skills/accessibility-mobile/SKILL.md`).

## Surfaces, Radius, Shadow, Motion

> **Note:** the color tokens above (`--color-*`, `.glass`, `.hover-lift`, Tailwind config,
> FontAwesome/Lucide) describe an earlier design export. The shipped `index.html` is a
> dc-runtime template whose live tokens are defined per-theme in `Component.THEMES`
> (`--bg`, `--surface`, `--surface2`, `--card`, `--text`, `--muted`, `--border`, `--border2`,
> `--accent`, `--accent2`, `--accent-ink`, `--accent-text`, `--danger`, `--c-applied`/`--c-interview`/
> `--c-offer`/`--c-reject`/`--c-archive`, `--radius`, `--r-sm`, `--font-head`/`--font-body`/`--font-mono`,
> `--shadow`) — see **Live Themes** below. Reconciling the legacy `--color-*` export above
> with the live tokens end-to-end is a follow-up (`docs/checklist.md`); the Motion notes below
> reflect the current template.

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
  button restyle automatically; the accent stays the shared beak orange. `color:var(--text)`
  on the scoping element is load-bearing: text without an explicit color otherwise inherits
  the page theme's computed color from the root, not the scoped navy palette.
- **Theme toggle.** A `role="switch"` pill (sun/moon knob) sits right of the **Options** button
  in the header (desktop-only, `data-desk`, 62×38px). It flips `arctic`⇄`midnight` and persists
  to `localStorage['magnify.theme']`; the Component constructor restores the saved value
  (unknown/legacy names fall back to `arctic`).

- **Entrance keyframes** (defined once in `index.html`'s `<style>`): `jf-fade` (opacity),
  `jf-slide` (slide-in from the right, used by slide-over panels), `jf-pop` (scale+rise, used by
  modals and chips), `jf-pulse` (used by the live-status dot), `jf-rise` (rise+fade, used by cards
  and toasts).
- **Hover/active/focus:** the dc-runtime template compiles any `style-<pseudo>` attribute
  (`style-hover`, `style-active`, `style-focus`, …) on an element into a real inserted stylesheet
  rule and merges the generated class onto that element — see `collectProps`/`createPseudoSheet`
  in `utils/frontend/static/js/dc-runtime.js`. Every interactive element pairs a `transition:`
  in its base `style` with a `style-hover` (and `style-active`/`style-focus` where relevant)
  attribute; identical hover CSS across elements is deduped into one shared class automatically.
- **Motion vocabulary** (small, reused everywhere, all values expressed via the theme tokens
  above so both themes stay correct by construction):
  - **Primary/accent buttons** (Applied, Find Jobs, Start Search, Save…, Analyze matches):
    `translateY(-1px)` + `filter:brightness(1.06)` on hover, `translateY(0)` +
    `brightness(.97)` on active/press — `.15s ease`.
  - **Secondary/bordered buttons**: hover tints `background`/`border-color` toward
    `var(--surface2)`/`var(--border2)`.
  - **Icon-only square buttons** (panel close, ignore, remove): `background:var(--surface2)` +
    a slight `scale(1.06)` press on active.
  - **Cards** (New Jobs grid article, Tracker kanban job card): `translateY(-2px)` +
    `box-shadow:var(--shadow)` on hover — the same treatment on both card types.
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
- Radius/spacing follow the per-theme `--radius`/`--r-sm` tokens; standardizing further shared
  spacing tokens is a follow-up.

## Iconography

FontAwesome + Lucide. Prefer one library per surface for consistency.

## Domain Vocabulary (UI copy)

Use concrete job-hunt terms: *New Jobs*, *Tracker*, *Applied / Interviewing / Offers / Rejected / Ghosted*, *Find Jobs*, *Ignore*, *job detail*, *compensation*, *location*, *source/board*. Avoid generic phrases like "boost productivity" or "all-in-one platform."

## Required UI States

Every view must design: **loading, empty, partial-data, error, success,** and **permission** (n/a — single user) states. Concrete states are enumerated per view in `docs/routes.md`.

## Mobile-Specific Decisions

- Bottom tab nav (`parts/mobile-nav.html`) on small screens; top tabs + sidebar on desktop.
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
