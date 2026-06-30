# Website Architecture Setup

Before creating or modifying a website, dashboard, or web application, answer these questions and use the answers to create the architecture planning artifact.

All website material belongs in the root `web/` directory. All documentation belongs in `docs/`.

## 1. Application Type

Which primary mode should this project use?

- Static HTML/CSS/JS site
- Astro content or marketing site
- React/Vite single-page app
- React/Next.js App Router app
- React/Next.js marketing or product site
- SvelteKit app
- Flask/Jinja or Flask/HTMX monolith
- Flask/FastAPI/Django API plus separate frontend
- Django application
- Dashboard/admin panel
- Dockerized full-stack app

If the project combines modes, name the primary mode and the secondary mode.

## 2. Frontend Stack and Optional Libraries

Define the frontend stack before scaffolding:

- JavaScript or TypeScript
- framework and rendering model
- styling layer, such as Tailwind, UnoCSS, SCSS, CSS Modules, vanilla CSS, or styled-components
- UI primitives, such as shadcn/ui, Radix UI, Headless UI, native HTML, or custom primitives
- data fetching/cache strategy, such as framework loaders/actions, TanStack Query, direct API calls, or server-rendered context
- routing layer, such as framework routing, React Router, TanStack Router, or backend-owned routing
- forms and validation, such as React Hook Form, Zod, server-side validation, or framework-native actions
- tables or dense-data tooling, such as TanStack Table or native tables
- motion layer, such as Framer Motion/Motion, GSAP, CSS transitions, View Transitions, or none

Only include optional libraries when they have a defined role.

## 3. User Roles

Which user roles exist?

- Public users
- Logged-in users
- Admin users
- Internal or high-permission users

For each role, define what routes and actions it can access.

## 4. Route Map

List every major route or page before building. For each route, define:

- path
- purpose
- required auth level
- data dependencies
- primary page/layout/components
- backend endpoints used, if any
- loading, empty, error, success, partial-data, and permission states

## 5. Data Sources and Flow

Define where data comes from and how it reaches the UI:

- static content
- database records
- uploaded files
- third-party APIs
- server-rendered context
- client-side state only
- cached or derived data
- streaming, real-time, or background job updates

## 6. Backend and API Needs

If a backend or API exists, define:

- framework
- endpoint groups
- request/response contracts
- validation ownership
- error response shape
- shared schema location
- retry, caching, optimistic update, and loading behavior

If no backend exists, explicitly state that `docs/api-contract.md` is not required.

## 7. Auth and Session Requirements

Define:

- auth mechanism, if any
- session or token ownership
- protected route behavior
- logged-out redirects or fallback states
- admin/high-permission boundaries

## 8. Design Quality and Product Specificity

Before UI generation, define:

- project-specific visual motif
- concrete domain vocabulary for UI copy
- color palette, type direction, radius, shadows, icons, and spacing rules
- meaningful imagery, screenshots, diagrams, product artifacts, or sample outputs to show
- generic AI-site patterns to avoid for this project
- at least one layout decision that should feel specific to the project
- real UI states that must be designed, including loading, empty, error, partial-data, success, mobile, and permission states

Use `ui-frontend/ui/design-quality.md` as the quality bar.

## 9. Runtime and Deployment

Define:

- local dev command
- build command
- test command
- lint and format commands
- deployment target
- required environment variables
- whether Docker is required

## 10. Testing and Validation

Define which checks are required:

- frontend unit/component tests
- backend tests
- route/API tests
- accessibility checks
- responsive viewport checks
- lint and format checks
- type checks
- production build check

## Required Planning Artifact

Before Step 5 of `initialize.md`, summarize the answers into a short planning artifact that names the selected application mode, framework, optional libraries, routes, auth roles, data flow, design-quality brief, repository layout, docs to create, and commands to run.
