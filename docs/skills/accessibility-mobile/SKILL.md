---
name: accessibility-mobile
description: Use this skill when implementing, auditing, or documenting mobile-friendly responsive web interfaces, touch behavior, mobile accessibility, mobile SEO parity, forms, media, and Core Web Vitals.
---

# Mobile Accessibility and Responsive UX

Use this skill for any website, web app, dashboard, admin panel, or frontend UI that must work well on phones and tablets. Pair it with `ada-compliance` for accessibility requirements and with `ui-frontend` for visual implementation details.

Before declaring a web interface complete, verify the checklist below or document any intentionally deferred items in `docs/checklist.md`.

## Responsive Layout and Viewport

- Every page includes `<meta name="viewport" content="width=device-width, initial-scale=1">` in the document head.
- Layouts are designed mobile-first, starting from a 320-375px viewport and scaling up with `min-width` media queries.
- CSS Grid and Flexbox use flexible units such as `%`, `fr`, `rem`, `clamp()`, and `auto-fit` or `auto-fill`.
- Multi-column layouts collapse into readable single-column flows on small screens.
- Images, videos, canvases, tables, and embeds cannot force horizontal scrolling.
- Key breakpoints are checked at 320px, 375px, 390px, 768px, 1024px, and a desktop viewport.

## Typography and Readability

- Body text is at least 16px on mobile.
- Line height is comfortable for small screens, usually 1.5-1.75 for body copy.
- Long-form text uses readable line lengths and does not run edge-to-edge on wide phones.
- Text contrast meets WCAG AA thresholds.
- Labels, metadata, captions, and helper text stay readable and do not fall below 12px unless there is a deliberate design-system exception.
- Fluid type uses bounded scaling so headings do not overflow or crowd controls.

## Touch and Navigation

- Primary tap targets are at least 44x44 CSS pixels.
- Smaller secondary targets still meet the accessibility minimum defined by `ada-compliance`.
- Tap targets have enough spacing to avoid accidental activation.
- All interactive elements provide visible pressed, focused, disabled, and loading states.
- No required interaction depends on hover alone.
- Mobile navigation matches the information architecture: short navs can use bottom tabs, while larger navs need grouped menus or drawers.
- Sticky headers, footers, cookie notices, and bottom action bars do not obscure content or focused elements.

## Images, Media, and Performance

- Responsive images use `srcset`, `sizes`, or framework equivalents when multiple asset sizes are available.
- Images below the fold are lazy-loaded unless doing so would delay the largest contentful paint element.
- Images include width and height, aspect-ratio, or other stable dimensions to prevent layout shift.
- Video uses mobile-safe playback behavior, including `playsinline` when appropriate.
- Initial page weight is kept reasonable for mobile networks.
- Core Web Vitals targets are considered: LCP under 2.5s, INP under 200ms, and CLS under 0.1 where possible.
- Loading, empty, and slow-network states are visible and do not create blank mobile screens.

## Forms and Inputs

- Inputs use semantic types such as `email`, `tel`, `number`, `search`, `url`, and `password`.
- Fields use appropriate `autocomplete` attributes for names, emails, addresses, payment details, and one-time codes.
- Inputs, selects, textareas, checkboxes, radios, and switches are large enough to use by touch.
- Long forms use grouping, clear progression, or progressive disclosure.
- Inline validation appears near the relevant field and remains accessible to assistive technology.
- Mobile keyboards, safe areas, and sticky action bars do not hide the active input.

## Mobile SEO and Rendering Parity

- Mobile and desktop render the same meaningful content.
- Robots, canonical, structured data, title, meta description, and heading structure remain consistent across breakpoints.
- CSS, JavaScript, and images needed to render the page are not blocked from crawlers.
- Hidden mobile content is hidden for UX reasons only, not as a substitute for missing mobile content.

## Mobile Accessibility Validation

- Test screen-reader behavior with platform expectations in mind, such as VoiceOver on iOS and TalkBack on Android when available.
- Semantic landmarks and heading structure still make sense on small screens.
- Focus order follows the visual reading order after responsive layout changes.
- Controls remain usable with keyboard, switch, and touch input.
- Motion respects `prefers-reduced-motion`.
- Error, success, loading, and status messages do not rely on color alone.
