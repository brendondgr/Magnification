# Logo-Derived Color Themes + Header Theme Toggle

## 1. Introduction

The app's two themes (`editorial` — warm cream with a rust accent, and `neon` — near-black
with lime green) share no colors with the brand logo ([images/magnify.svg](../../images/magnify.svg)),
a penguin drawn in exactly four families: deep navy `#132433`/`#223140`, beak orange
`#F4A226`, handle gray `#7C7E80`, and belly off-white `#F7F6F5`. This plan replaces both
themes with logo-derived ones — **`arctic`** (light: off-white surfaces, navy text, orange
accent) and **`midnight`** (dark: navy surfaces, off-white text, orange accent) — so the UI
and the mascot read as one brand.

Because all styling flows through the CSS custom properties defined in `Component.THEMES`
(single source in `utils/frontend/templates/index.html`), the recolor is a token-block swap
plus a handful of hardcoded-color touch-ups. The plan also adds a user-facing control that
did not exist before: a toggle switch in the header, immediately to the right of the
**Options** button, that flips between the two themes and persists the choice.

## 2. Gaps & Unanswered Questions

- **Default theme**: Which theme loads first for a fresh visitor? *Assumption*: `arctic`
  (light), matching the current light default (`editorial`).
- **Persistence**: Theme choice currently lives only in component state and resets on
  reload. *Assumption*: persist to `localStorage` (`magnify.theme`) and read it during
  construction; this is a pure-frontend concern and should not become a backend option.
- **Mobile visibility**: Header buttons marked `data-desk` are hidden under 880px.
  *Assumption*: the toggle is desktop-only for now (marked `data-desk`), consistent with
  Profile/Options; mobile users keep the default theme until a mobile placement is designed.
- **Pipeline status hues**: Exact values for `--c-applied`/`--c-interview`/`--c-offer`/
  `--c-reject`/`--c-archive` per theme are a design judgement. *Assumption*: keep the
  current semantic hues (blue/orange/green/red/gray) but retune lightness so each passes
  contrast on the new `--bg`/`--surface` values; interview reuses the brand orange.
- **Fonts, radii, shadows**: *Assumption*: unchanged — this is a color-only pass.
  (`--font-head` currently differs per theme; both new themes keep their predecessor's
  fonts: `arctic` inherits `editorial`'s Newsreader headings, `midnight` inherits
  `neon`'s Space Grotesk. If a single shared heading font is wanted, that is a follow-up.)

## 3. Hierarchical Step-by-Step Instructions

#### Step 1: Replace the theme token blocks

- **Locations**: `utils/frontend/templates/index.html` — `Component.THEMES` (~line 1396);
  `constructor` initial state `theme:'editorial'` (~line 1456).
- **Work**:
  - Replace the `editorial` entry with `arctic`:
    `--bg:#E9EDF1`, `--surface:#F7F6F5`, `--surface2:#FFFFFF`, `--card:#FCFBFA`,
    `--text:#132433`, `--muted:#5B6B7A`, `--border:#D7DEE5`, `--border2:#B7C3CE`,
    `--accent:#F4A226`, `--accent-ink:#132433`, `--accent-text:#B26E0E`,
    `--accent2:#223140`, retuned `--c-*` stage colors, navy-tinted `--shadow`.
  - Replace the `neon` entry with `midnight`:
    `--bg:#0C1826`, `--surface:#132433`, `--surface2:#1B3145`, `--card:#172B3C`,
    `--text:#F7F6F5`, `--muted:#8CA0B3`, `--border:#24394E`, `--border2:#35506A`,
    `--accent:#F4A226`, `--accent-ink:#132433`, `--accent-text:#F4A226`,
    `--accent2:#8CA0B3`, retuned `--c-*` stage colors.
  - Update the initial state to `theme:'arctic'`.
- **Rationale**: `renderVals()` merges `Component.THEMES[s.theme]` into the root style, so
  every `var(--*)` in the template recolors from this one block. Renaming the keys must
  happen first because Step 3's toggle flips between the two key names.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit stating: Logo Themes (1/4) Complete: Replaced editorial/neon token
  blocks with logo-derived arctic/midnight themes.

#### Step 2: Sweep hardcoded colors that no longer sit well

- **Locations**: `utils/frontend/templates/index.html` — the header logo chip
  (`background:#F7F6F5`, ~line 81); destructive-action red `#E5484D` usages (sidebar
  Clear buttons ~lines 132–142, ignored-card border in `decorate()` ~line 2380);
  `INDUSTRY_COLORS` / `SITE_COLORS` pill colors (~lines 1426–1433).
- **Work**: keep the logo chip's fixed `#F7F6F5` (it is the logo's own white and now
  matches `arctic`'s surface; on `midnight` it still needs the chip to stay legible) but
  confirm its `var(--border)` hairline still separates it on both themes. Verify
  `#E5484D` red and the industry/site pill palette read acceptably on the new light
  `--bg`/`--card` (they were tuned for dark `neon` and cream `editorial`); adjust only
  the ones that fail a visual/contrast check.
- **Rationale**: these are the only colors outside the token blocks; a token swap alone
  leaves them stranded against new backgrounds.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit stating: Logo Themes (2/4) Complete: Reconciled hardcoded chip,
  destructive, and pill colors with the new themes.

#### Step 3: Add the header theme toggle

- **Locations**: `utils/frontend/templates/index.html` — header actions `<div>`
  (~lines 96–109, new element after the Options button, ~line 108); `Component` class:
  constructor (theme init from `localStorage`), new `toggleTheme()` method near the other
  small state helpers (e.g. next to `openOptions()` ~line 2302), and `renderVals()`
  (~line 2680 area) to expose the toggle's `onClick`/style bindings.
- **Work**:
  - A `data-desk` switch-style button to the right of Options: a small pill track with a
    sliding knob (sun/moon or arctic/midnight glyphs), `aria-label="Toggle theme"`,
    `role="switch"` + `aria-checked`, styled entirely with theme tokens, reusing the
    existing hover/active micro-interaction vocabulary from `docs/design-system.md`.
  - `toggleTheme()` flips `state.theme` between `'arctic'` and `'midnight'` and writes the
    choice to `localStorage['magnify.theme']`; the constructor reads that key (guarded for
    unknown/legacy values) before falling back to the default.
- **Rationale**: the theme was previously state-only with no UI; the switch makes the
  second theme reachable, and persistence makes the choice survive reloads. Placement and
  `data-desk` follow the existing header-button conventions.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit stating: Logo Themes (3/4) Complete: Added persistent arctic/midnight
  toggle switch right of the Options button.

#### Step 4: Tests, docs, and final verification

- **Locations**: `tests/frontend/test_theme_tokens.py` (new); `docs/design-system.md`
  (palette + theme sections, logo-chip note); `docs/component-map.md` (header: new toggle);
  `docs/checklist.md` (mark the work done); `docs/structure.md` only if files were added
  beyond the test.
- **Work**:
  - Lightweight tests in the style of `tests/test_frontend_wiring.py`: serve `/` and assert
    the page defines `arctic` and `midnight` (and no `editorial`/`neon`), that both token
    blocks define the required `--*` keys with the brand hexes (`#F4A226`, `#132433`,
    `#F7F6F5`), and that the toggle element (`aria-label="Toggle theme"`) is present.
  - Run the full accessibility pass from `docs/skills/accessibility-mobile/SKILL.md`
    relevant to the change: contrast of text/muted/accent-text pairings on both themes,
    44px-equivalent touch target on the toggle, visible focus state.
  - Update the three docs in the same change (design decisions → `design-system.md`,
    new header control → `component-map.md`, checklist entry).
- **Rationale**: project rules require docs to move with the change and UI work to pass
  the accessibility checklist; the token-presence test guards against a future edit
  silently dropping a required variable.
- **Action**: Undergo the verification/tests/validation process for this phase. Once
  validated, commit stating: Logo Themes (4/4) Complete: Added theme token tests and
  updated design-system, component-map, and checklist docs.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| `arctic` + `midnight` token blocks | Logo-derived light/dark themes replacing `editorial`/`neon`. | `utils/frontend/templates/index.html` (`Component.THEMES`) |
| Hardcoded-color reconciliation | Logo chip, destructive red, industry/site pills verified or retuned on both themes. | `utils/frontend/templates/index.html` |
| Theme toggle switch | Persistent switch right of Options; `role="switch"`, token-styled, `data-desk`. | `utils/frontend/templates/index.html` (header + `toggleTheme()`) |
| Theme token tests | Serve `/`, assert theme keys/hexes/toggle presence. | `tests/frontend/test_theme_tokens.py` |
| Docs updates | Palette, header component, checklist entries. | `docs/design-system.md`, `docs/component-map.md`, `docs/checklist.md` |

## Notes

- Work happens on a feature branch (e.g. `logo-color-themes`) in a dedicated worktree;
  commits per phase; no push unless requested.
- Verification is via served-HTML/API checks and `uv run pytest` (the in-app browser pane
  cannot composite screenshots in this environment); restart the preview server if any
  Python is touched.
