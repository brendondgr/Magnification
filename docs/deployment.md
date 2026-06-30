# Deployment — Magnification

## Runtime Model

Magnification is a **local-first, single-user** Flask application. It currently runs via the Flask development server on the developer's machine; there is no production hosting target.

## Local Development

| Step | Command |
| --- | --- |
| Install deps | `uv sync` |
| Run | `uv run app.py` |
| URL | `http://127.0.0.1:5000` |

`app.py` runs `application.run(debug=True)` when executed directly.

## Runtime Dependencies

- **Python ≥ 3.12** with `uv`.
- **SQLite** database under `data/` (created on first run via `init_database()`).
- **Local LLM (optional):** llama-server binaries and model files managed by `utils/LocalLLM`; GPU detection is automatic. Not required for core scraping/tracking.
- **Network access** to job boards for scraping.

## Configuration

- `jobs_config.json` and `llm_config.json` live at the project root (gitignored) and are managed through the UI/API.
- No environment variables are required today. If introduced, document them in `docs/workflow.md` and add `.env.example`.

## Data & Backups

- All durable data is the SQLite DB in `data/` (gitignored). Back up by copying that file.

## Production Notes (future)

Not yet targeted. If hosted later: replace the dev server with a WSGI server (e.g., gunicorn/waitress), externalize config to env vars, and reconsider SQLite vs. a managed database. The planned React frontend (Mode G) would add a separate frontend build/deploy step. Track under `docs/checklist.md`.
