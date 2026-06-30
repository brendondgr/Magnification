---
name: website-architecture
description: Use this skill when planning, scaffolding, restructuring, or documenting a website, dashboard, web app, Next.js app, React app, SvelteKit app, Astro site, Flask app, Django app, API-backed frontend, or Dockerized web application.
---

# Website Architecture Skill

This skill defines the structural phase that must happen before UI code is generated for a website or web application. It sits between universal repository structure and frontend visual implementation.

All website-specific code, assets, routes, and runtime files must live under the root `web/` directory. Repository-level documentation remains under `docs/`.

For any web-facing project, include `ui-frontend`, `accessibility-mobile`, and `ada-compliance` with this skill so visual quality, mobile-readiness, and WCAG/ADA requirements are captured before implementation is declared complete.

## Core Rule

Do not generate isolated visual pages until structure, routes, stack choices, data flow, and design-quality requirements are defined.

## Required Outputs

Before generating website files, define:

1. Application mode and rendering model
2. Frontend framework and package choices
3. Route map
4. User role and auth map
5. Data-flow map
6. Frontend/backend boundary
7. Directory structure
8. Design-system and anti-generic quality brief
9. Required documentation files
10. Build, run, test, lint, and format commands

## Application Modes

Choose exactly one primary mode before scaffolding. If the project combines modes, name the primary mode and document secondary modes in `docs/architecture.md`.

- Static HTML/CSS/JS site
- Astro content or marketing site, optionally with React or Svelte islands
- React/Vite single-page app
- React/Next.js App Router app
- React/Next.js marketing site with interactive product sections
- SvelteKit app
- Flask/Jinja or Flask/HTMX monolith
- Flask/FastAPI/Django API plus separate frontend
- Django application with templates, admin, ORM, and optional API
- Dashboard or admin panel
- Dockerized full-stack app

## Stack and Library Selection

The agent must ask for and record explicit stack choices. Do not assume Astro, Svelte, Tailwind, React, or Next.js just because the project is a website.

Record decisions for:

- language: JavaScript or TypeScript
- rendering model: static, SSR, SSG, ISR, SPA, server actions, server-rendered templates, or API-backed frontend
- framework: Next.js, React/Vite, Astro, SvelteKit, Flask, Django, FastAPI, or another explicit choice
- styling: Tailwind, UnoCSS, CSS Modules, SCSS, vanilla CSS, styled-components, or another explicit choice
- component primitives: shadcn/ui, Radix UI, Headless UI, native HTML, custom primitives, or framework-specific alternatives
- data fetching and caching: framework loaders/actions, TanStack Query, server actions, direct API calls, or server-rendered context
- tables and dense data: TanStack Table, native tables, data-grid library, or custom components
- forms and validation: React Hook Form, framework-native forms/actions, Zod, Yup, server-side validation, or another explicit choice
- routing: framework routing, React Router, TanStack Router, file-based routing, or backend-owned routing
- motion: Framer Motion/Motion, GSAP, CSS transitions, View Transitions, or no animation library
- auth/session ownership: frontend, backend, framework middleware, provider SDK, or none
- testing: unit, component, route, API, accessibility, responsive viewport, build, lint, and type checks

### React/Next.js Reference Stack

Use this as an option, not as a default:

- Next.js App Router
- TypeScript
- Tailwind when utility-first styling is requested
- shadcn/ui for copy-owned component scaffolds
- Radix UI for accessible primitives when shadcn/ui or custom components need headless behavior
- Framer Motion or Motion for purposeful interaction and page transitions
- TanStack Query for client-side server-state caching when the app is API-heavy
- TanStack Table for dense tabular data
- React Hook Form plus Zod for complex client-side forms and validation
- Server actions, route handlers, or a separate backend depending on the project boundary

### React/Vite Reference Stack

Use this when the app is a client-heavy SPA or frontend shell:

- React/Vite
- TypeScript
- React Router or TanStack Router
- TanStack Query for API-backed server state
- Tailwind, CSS Modules, SCSS, or another confirmed styling layer
- shadcn/ui or Radix UI when accessible React primitives are desired
- React Hook Form plus Zod for complex forms
- Framer Motion/Motion, GSAP, or CSS transitions for purposeful motion

### Astro or SvelteKit Reference Stack

Use Astro when content, performance, static output, and partial islands are central. Use SvelteKit when the application benefits from Svelte routing, actions, stores, SSR, and a full app framework.

For these stacks, select component, form, and motion libraries that actually fit the framework. Do not force React-only tools such as Radix UI React or React Hook Form into a non-React app unless the project explicitly uses React islands.

## Library Inclusion Rules

- Include a library only when it has a defined job.
- Do not install overlapping tools without a reason, such as multiple routers, multiple form libraries, or multiple animation systems.
- Record every selected optional library in `docs/architecture.md` and every command in `docs/workflow.md`.
- If a library affects folder structure, record that ownership in `docs/structure.md` and `docs/component-map.md`.
- If the user is unsure, propose a conservative stack and ask for confirmation.

## Route Map

Every major route or page must be listed before implementation. For each route, define:

- path
- purpose
- user role or auth level
- data dependencies
- primary page, layout, and component ownership
- backend endpoints used, if any
- loading, empty, error, and permission states

## Data Flow

Document where data comes from and how it moves through the application:

- static content
- database-backed content
- uploaded files
- third-party APIs
- server-rendered data
- client-only state
- cached or derived data
- streaming, real-time, or background job updates

## Frontend/Backend Boundary

For projects with both frontend and backend code, define:

- which layer owns routing
- which layer owns auth/session handling
- which layer validates data
- which endpoints, actions, or contracts connect the layers
- where shared schemas, OpenAPI specs, or type contracts live
- which layer owns errors, retries, caching, and optimistic updates

## Design-Quality Planning Gate

Before UI implementation, create a short design-quality brief in `docs/design-system.md` or `docs/architecture.md`. It must define:

- project-specific visual motif
- color palette, typography, radius, shadow, icon, and spacing rules
- meaningful imagery or product artifacts to show near the top of key pages
- concrete domain vocabulary to use in UI copy
- at least one layout decision that is specific to this project
- required loading, empty, error, partial-data, success, and permission states
- mobile-specific layout decisions

The UI implementation must follow `ui-frontend/ui/design-quality.md`. Remove generic AI-site patterns such as vague productivity copy, decorative glowing gradients, fake metrics, abstract orb imagery, and repeated identical feature-card grids unless the project specifically justifies them.

## Required Documentation

Create or update:

- `docs/architecture.md`
- `docs/structure.md`
- `docs/routes.md`
- `docs/component-map.md`
- `docs/data-flow.md`
- `docs/deployment.md`
- `docs/design-system.md`
- `docs/api-contract.md` when backend/API contracts exist

Each document should be concise, concrete, and useful for a later agent or engineer maintaining the project.
