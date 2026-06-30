# Repository Structure Setup

When configuring the repository structure, please answer the following questions to help tailor the environment to your tech stack:

1. **Web Interface Generation:** Are we creating a web interface specific structure, or is this a purely backend/CLI project?
2. **Primary Runtime:** What is the main runtime or language for the project (Python with `uv`, Node, mixed full-stack, static-only, or another runtime)?
3. **Repository Shape:** Is this a single app, a multi-app workspace, or a library/tooling repository?
4. **Shared Code:** Will the project need shared `libs/`, `utils/`, or contract/schema folders?
5. **Test Structure:** If the project uses Python, which top-level `tests/` sub-directories should exist to group related test coverage by purpose?
6. **Generated Documentation:** Which structure documents must be created or updated beyond `docs/structure.md`?

*(AI Note: If the answer indicates a website, dashboard, frontend, Flask app, FastAPI app, Django app, Astro site, SvelteKit app, React/Vite app, Next.js app, or API-backed web interface, immediately route the setup into `website-architecture/SETUP.md`. Web-specific details must be captured there before repository files are generated.)*
