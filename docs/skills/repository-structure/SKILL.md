---
name: repository-structure
description: Use this skill when setting up, restructuring, documenting, or enforcing repository layout standards for projects, including web apps, backend systems, CLI tools, and agentic AI systems.
---
# Repository Structure Standard

This document defines the universal file structure for all repositories within the ecosystem. Adhering to this structure ensures consistency, maintainability, and ease of navigation across different projects.

## Core Directory Structure

```text
root/
├── docs/       # Project documentation and architectural overviews
├── libs/       # Shared libraries and internal packages
├── utils/      # Utility functions and helper classes
└── [workflow]/ # Domain-specific folders (e.g., web/, api/, core/)
```

### Workflow-Specific Structures
App-specific structures are documented individually to keep our core guidelines clean.
- [Web Interfaces](structures/web-interfaces.md)
- [Lab Reports](structures/lab-reports.md)
- [LangGraph Structure](structures/langgraph.md)

For websites, dashboards, and web applications, this skill must be paired with `website-architecture`. The web architecture skill owns the route map, app mode, frontend/backend boundary, data flow, documentation requirements, and deployment assumptions before files are generated.

---

## 1. Documentation (`docs/`)
All documentation regarding the project, including architecture, setup guides, and structural maps, resides here.

- **Mandatory File:** `docs/structure.md`
  - This file must be kept up-to-date with the current file structure.
  - It should detail main sub-folders and primary files, explaining their purpose without including source code.

---

## 2. Utilities (`utils/`)
Utilities that support the main codebase.

- **Small Utilities:** Basic utilities (e.g., a simple logger) should be kept as individual files directly within `utils/`.
- **Large Utilities:** If a utility requires complex logic or becomes a large class, it should be placed in its own sub-folder.
- **Initialization:** For Python projects, sub-folders must include an `__init__.py` file for proper package initialization.

---

## 3. Libraries (`libs/`)
Internal libraries and external-facing components are modularized within the `libs/` directory.

## 4. Tests (`tests/`)
Python projects should create lightweight tests over time in a top-level `tests/` directory.

- Keep tests small and focused as features are added.
- Group related Python tests into sub-directories that match the area or purpose they cover.
- Use descriptive names so the test tree stays readable as it grows.
- Prefer `tests/<area>/test_<behavior>.py` over a single oversized flat test folder.

### Example Test Layout

```text
tests/
├── api/
│   ├── test_auth.py
│   └── test_routes.py
├── data/
│   └── test_parsing.py
└── utils/
    └── test_formatting.py
```

---

## Global Code Guidelines

### File Length Limits
- **Maximum Length:** 800 lines.
- **Ideal Length:** Under 500 lines.
- **Rule:** Favor modularity. If a file exceeds 800 lines, outsource logic to secondary files/modules.

### Package Management
We use `uv` as the primary package manager for all Python projects.
- **Primary Commands:** `uv add`, `uv init`, `uv run`.
- Avoid using other package managers unless explicitly required by environment constraints.

---

## Universal Examples

### Utility Organization (`utils/`)

- **Single Functionality:**
  - `utils/logger.py` – A lightweight logging class.
- **Complex Sub-system:**
  - `utils/auth_handler/`
    - `__init__.py` – Orchestrates the authentication exports.
    - `oauth.py` – Handles OAuth2 flows.
    - `session.py` – Manages user sessions.

### Directory Summary Table (Sample `docs/structure.md` entry)

| File / Folder | Purpose |
| :--- | :--- |
| `utils/database.py` | Minimal database connection wrapper. |
| `utils/payment_engine/` | Sub-folder for complex transaction logic. |
| `libs/analytics/` | Internal event-tracking package. |

---

*Last Updated: 2026-03-27*
