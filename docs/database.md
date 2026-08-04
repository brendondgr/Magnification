# Database — Magnification

SQLite via SQLAlchemy ORM. Source: `utils/backend/database/`.

The database file lives at `<project_root>/data/magnificiation.db` (see `config.py`;
`DATABASE_URL` is a plain `sqlite:///` path). `PROJECT_ROOT` is resolved by
`utils/backend/paths.get_project_root()`, which shells out to `git rev-parse --git-common-dir`
so the **main checkout and every git worktree share the same `data/`** — a worktree-relative
`__file__` path would otherwise point at that worktree's own empty directory. `init_database()`
(called once at app startup) runs `Base.metadata.create_all()` — creating any missing tables —
and then `_run_migrations()`, a fixed sequence of idempotent additive migrations that patch
pre-existing databases with columns added after their creation. Both are safe to call on every
startup.

## Models (`models.py`)

### `jobs`

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `title` | String(255), NOT NULL | — |
| `company` | String(255), NOT NULL | — |
| `location` | String(255), NOT NULL | — |
| `link` | String(2048) | URL to the posting |
| `description` | Text | Full job description |
| `compensation` | String(255) | Salary/pay string, or empty. Only ever a usable string — the jobspy formatter and `recommend.compensation.clean_compensation` both reject NaN-poisoned/digit-less values before they reach this column. |
| `compensation_checked` | Integer, default 0 | **Gate flag**: 1 once LLM compensation extraction has run for this job (whether or not pay was found), so a no-pay job isn't re-queried every scrape/"Analyze Matches" run. A forced reanalyze re-attempts regardless. |
| `industry` | String(64) | Detected industry (fixed taxonomy in `recommend.compensation.INDUSTRIES`), extracted in the same LLM pass as compensation. `NULL` until classified. |
| `industry_checked` | Integer, default 0 | **Gate flag**, set only when a label actually came back (unlike `compensation_checked`, which is set unconditionally). Jobs stamped-but-unlabeled by an older code path are re-opened by `migrate_reset_unlabeled_industry`. |
| `site` | String(50) | Job board the listing came from |
| `ignore` | Integer, default 0 | 1 excludes the job from the tracker/feed |
| `saved` | Integer, default 0 | **Gate-adjacent flag**: 1 pins the job to the Saved lane, hides it from the New Jobs feed, and exempts it from scrape/profile auto-filtering (`saved=1` jobs are skipped by `job_filter`). Only the manual hide action can still set `ignore=1` on a saved job. |
| `date_first_applied` / `date_first_interview` / `date_first_offer` / `date_first_rejected` / `date_first_ghosted` | String(10), Nullable | Durable, **write-once** pipeline timestamps (YYYY-MM-DD). Stamped by `update_application_status` the first time the mapped `application_statuses` milestone is checked, never cleared/overwritten afterwards (survives a card being dragged backward). No "found" column — `created_at` already serves that role. |
| `created_at` | DateTime | Also the durable "found" date (serialized as `date_found`) |
| `updated_at` | DateTime | — |

Indexes: `idx_jobs_company`, `idx_jobs_ignore`, `idx_jobs_saved`.

### `application_statuses`

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `job_id` | Integer, FK → `jobs.id` ON DELETE CASCADE, NOT NULL | — |
| `status` | String(50), NOT NULL | One of the 9 `APPLICATION_STATUSES` (`config.py`): Applied, Interview 1/2/3, Post-Interview Rejection, Offer, Accepted, Rejected, Ignored/Ghosted |
| `checked` | Integer, default 0 | **Gate flag**: 1 = milestone reached. `reset_application_status` clears every row for a job back to 0. |
| `date_reached` | String(10), Nullable | YYYY-MM-DD when `checked` last flipped to 1; mutable (unlike `jobs.date_first_*`) |

Every non-ignored job gets all 9 rows created together (`add_job` → `_create_status_records_for_job`). Indexes: `idx_app_status_job_id`, `idx_app_status_checked`.

### `profiles`

Single-active-row comparison target for the recommendation system.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `name` | String(120), default `"default"` | Human label |
| `is_active` | Integer, default 0 | 1 for the one profile used for scoring; invariant enforced by `set_active_profile`/`upsert_active_profile` |
| `source_filename` | String(512) | Original resume filename (pdf/tex/md) |
| `resume_text` | Text | Extracted resume plain text |
| `interests_paragraph` | Text | Free-body interests paragraph (LLM matching) |
| `skills` | JSON | list[str] |
| `job_titles` | JSON | list[str] search-query titles |
| `keyword_groups` | JSON | list[{label, terms:[...], scopes:[...]}] — AND across groups, OR within a group; `scopes` ⊆ {title, description}; an unsatisfied group hard-blocks a job at scrape time |
| `blocked_companies` | JSON | list[str], case-insensitive company hide-list |
| `title_blocklist` | JSON | list[str], any title substring match hides the job |
| `llm_instructions` | Text | Free-text guidance steering the LLM profile build |
| `created_at` / `updated_at` | DateTime | — |

Index: `idx_profiles_active`.

### `job_analyses` (1:1 with `jobs`)

RAG/embedding relevance signal, upserted by `job_id`. Embedding is profile-independent (computed once on retrieval); scores are recomputed per `profile_id`.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `job_id` | Integer, FK → `jobs.id` ON DELETE CASCADE, unique | 1:1 |
| `profile_id` | Integer, FK → `profiles.id` ON DELETE SET NULL, Nullable | Profile the scores were computed against |
| `embedding` | LargeBinary | Packed float32 bytes, bge-small-en-v1.5 |
| `embedding_dim` | Integer | 384 |
| `extracted_skills` | JSON | Skills found in the description |
| `semantic_score` / `bm25_score` / `keyword_score` / `skill_score` | Float | Component signals |
| `rag_score` | Float | Combined hybrid relevance (0..1) |
| `keyword_group_hits` | JSON | `{group_label: [matched terms]}` |
| `skill_match` | JSON | `{matched:[...], missing:[...]}` |
| `llm_score` | Float | Optional LLM verdict (0..100) |
| `llm_rationale` | Text | Optional LLM explanation |
| `analyzed_at` | DateTime | — |

Deleting a `Job` cascades (ORM-level, via `Job.analysis` backref). Indexes: `idx_job_analyses_job_id` (unique), `idx_job_analyses_profile_id`, `idx_job_analyses_rag_score`.

### `job_evaluations` (1:1 with `jobs`)

Agentic-documents application-fit verdict — distinct from `job_analyses` (ranking signal vs. fit narrative). Upserted by `job_id`.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `job_id` | Integer, FK → `jobs.id` ON DELETE CASCADE, unique | 1:1 |
| `profile_id` | Integer, FK → `profiles.id` ON DELETE SET NULL, Nullable | — |
| `verdict` | Text | Short fit verdict |
| `fit_score` | Float | 0..100 |
| `emphasize` | JSON | list[str] |
| `gaps` | JSON | list[str] |
| `risks` | Text | Free-text |
| `talking_points` | JSON | list[str] |
| `created_at` / `updated_at` | DateTime | — |

Deleting a `Job` cascades. Indexes: `idx_job_evaluations_job_id` (unique), `idx_job_evaluations_profile_id`.

### `generated_documents` (many per `jobs`)

Storage for generated cover letters/résumés.

| Column | Type | Meaning |
| --- | --- | --- |
| `id` | Integer PK | — |
| `job_id` | Integer, FK → `jobs.id` ON DELETE CASCADE | Not unique — multiple docs/revisions per job |
| `kind` | String(32), default `cover_letter` | `cover_letter` or `resume` |
| `content` | Text | Rendered document body |
| `format` | String(16), default `markdown` | markdown / latex / docx |
| `status` | String(16), default `draft` | `draft` or `approved` |
| `match_before` / `match_after` | Float | Fit-score lift before/after generation |
| `revision` | Integer, default 1 | — |
| `checkpoint_state` | JSON | In-progress generation state, so a run survives HTTP round-trips |
| `created_at` / `updated_at` | DateTime | — |

Deleting a `Job` cascades. Indexes: `idx_generated_documents_job_id`, `idx_generated_documents_kind`.

> The `uploaded_documents`, `behavioral_profiles`, `writing_style_profiles`, and
> `document_templates` tables (and their ingestion pipeline) were retired in favor of a single
> editable Document Guidance document (`config/document_guidance.json`, not a DB table); their
> ORM models were removed from `models.py`. A pre-existing database keeps them as harmless
> orphans — no destructive migration was run. See `utils/backend/agents/document_guidance.py`.

## Migrations (`_run_migrations`, `init_db.py`)

All are idempotent (safe to run on every startup) and no-op when the database file or the target table doesn't exist yet. Run in this order:

| Module | Adds / repairs |
| --- | --- |
| `migrate_profile_blocklists` | `profiles.blocked_companies`, `profiles.title_blocklist` (JSON, stored as TEXT) |
| `migrate_profile_llm_instructions` | `profiles.llm_instructions` (TEXT) |
| `migrate_job_saved` | `jobs.saved` (INTEGER default 0) |
| `migrate_job_compensation_checked` | `jobs.compensation_checked` (INTEGER default 0) |
| `migrate_job_industry` | `jobs.industry` (VARCHAR(64)), `jobs.industry_checked` (INTEGER default 0) |
| `migrate_job_pipeline_dates` | `jobs.date_first_applied/interview/offer/rejected/ghosted` (TEXT); backfills each from the earliest matching checked `application_statuses.date_reached` |
| `migrate_clean_bad_compensation` | Data repair: blanks malformed `compensation` strings (e.g. `"USDnan - USDnan hourly"`) via `recommend.compensation.clean_compensation`, and clears `compensation_checked` on the repaired rows so the description extractor re-derives real pay. Runs after the column migrations. |
| `migrate_reset_unlabeled_industry` | Data repair: clears `industry_checked` on rows stamped by an earlier always-stamp code path that carry no `industry` label, so they're reclassified |

`migrate_site_field` (adds `jobs.site`) exists in the same directory but is **not** wired into
`_run_migrations` — `site` ships as a `create_all` column on fresh databases, and this script is
a standalone legacy tool (run manually if ever needed against a pre-`site` database).

## Operations

### Jobs — read/write (`operations.py`)

`add_job`, `update_job`, `delete_job`, `clear_jobs_database` (bulk-deletes `job_analyses`, `job_evaluations`, `generated_documents`, `application_statuses` then `jobs`, since bulk delete bypasses ORM cascade), `get_job_by_id`, `get_all_jobs`, `get_active_jobs`, `get_feed_jobs` (feed visibility: not ignored, or saved, or already applied), `get_job_counts`, `get_jobs_by_ids`, `set_job_ignore`, `set_job_saved`

### Dedupe

`get_existing_job_keys` — set of lowercased `(title, company)` tuples for the whole table, used by the scrape pipeline to drop already-tracked jobs before spending LinkedIn/LLM calls on them (location intentionally excluded)

### Application status + write-once pipeline dates

`create_application_status_records`, `update_application_status` (also stamps the matching `jobs.date_first_*` column on first check, via `PIPELINE_DATE_COLUMN` + `_stamp_pipeline_date`), `get_application_status_by_job`, `get_statuses_for_jobs` (batched, chunked at 500 IDs), `get_status_by_name`, `reset_application_status`

### Query

`get_jobs_by_status`, `get_jobs_by_company`, `get_timeline_for_job`

### Profile

`create_profile`, `update_profile`, `get_profile_by_id`, `get_active_profile`, `list_profiles`, `set_active_profile`, `upsert_active_profile` (update-if-active-exists else create), `delete_profile`

### Analysis

`save_job_analysis` (upsert by `job_id`), `get_analysis_for_job`, `get_analysis_for_jobs`

### Agentic documents (`documents_ops.py`)

`save_job_evaluation` (upsert by `job_id`), `get_job_evaluation`, `create_generated_document`, `update_generated_document`, `delete_generated_document`, `get_generated_document`, `list_generated_documents`

## Testing

Tests live in top-level `tests/database/`. Because every worktree shares the one real
`data/magnificiation.db` (see the intro), tests must never touch it: the standard pattern
(`tests/database/test_job_saved.py` and siblings) creates an in-memory `sqlite://` engine with
`StaticPool`, runs `Base.metadata.create_all(bind=engine)`, and `monkeypatch`es
`init_db.SessionLocal` to a session factory bound to that engine — every `get_db_context()` call
in `operations.py`/`documents_ops.py` then transparently resolves to the isolated engine.
Profile-touching tests that can't fully isolate this way must snapshot and restore the active
profile instead.
