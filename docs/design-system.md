# Design System — Magnification

Captured from `utils/frontend/static/css/variables.css` and the inline Tailwind config in `index.html`. This is the design-quality brief required by `docs/skills/website-architecture/SKILL.md`. Keep tokens here in sync with `variables.css`.

## Visual Motif

Warm, tactile, "card-on-cream" job board with a playful but focused feel — a personal cockpit for hunting and tracking jobs, not a generic SaaS dashboard. Soft cream surfaces, an electric-coral accent, glassmorphism on the header, and a spring-like hover lift on interactive cards. Avoid generic AI-site patterns (vague productivity copy, glowing gradients, abstract orbs, fake metrics, repeated identical feature-card grids).

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

## Typography

- Headings: **Space Grotesk** (`.font-heading`)
- Body: **DM Sans** (`.font-body`)
- Mono / metadata: **JetBrains Mono** (`.font-mono-custom`)
- Body text ≥ 16px on mobile (per `docs/skills/accessibility-mobile/SKILL.md`).

## Surfaces, Radius, Shadow, Motion

- **Glassmorphism:** `.glass` and `.glass-header` (translucent cream + `blur(12px)`).
- **Hover lift:** `.hover-lift` — `translateY(-2px) scale(1.01)` with a spring cubic-bezier and `shadow-lg`.
- Radius/spacing follow Tailwind defaults configured inline in `index.html`; standardizing them as tokens is a follow-up.

## Iconography

FontAwesome + Lucide. Prefer one library per surface for consistency.

## Domain Vocabulary (UI copy)

Use concrete job-hunt terms: *New Jobs*, *Tracker*, *Applied / Interviewing / Offers / Archived*, *Find Jobs*, *Ignore*, *job detail*, *compensation*, *location*, *source/board*. Avoid generic phrases like "boost productivity" or "all-in-one platform."

## Required UI States

Every view must design: **loading, empty, partial-data, error, success,** and **permission** (n/a — single user) states. Concrete states are enumerated per view in `docs/routes.md`.

## Mobile-Specific Decisions

- Bottom tab nav (`parts/mobile-nav.html`) on small screens; top tabs + sidebar on desktop.
- Single-column card flow on mobile; multi-column grid / kanban on wider viewports.
- Tap targets ≥ 44×44px; the job-detail slide-over and modals must not trap focus or hide the active input behind the mobile keyboard.

## Anti-Generic Checklist

- Show real job data (title, company, comp, location, source) prominently — not placeholder marketing.
- Use the categorization palette meaningfully (tags/status), not as decoration.
- Keep copy specific to job hunting.
