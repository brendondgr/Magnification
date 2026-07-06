# Plan — Analyze Matches Progress Popup

## 1. Introduction

Today "Analyze Matches" fires a single synchronous `POST /api/recommend/analyze` and only
shows a toast when it finishes. With the LLM fit now running over every non-ignored job that
lacks a verdict, the call can take a long time and gives the user no feedback on how many jobs
are being processed or how far along it is.

This plan adds a live progress **popup** for Analyze, mirroring the already-proven scraping
activity-feed pattern: the analysis runs in a background thread that writes stage/percent/event
progress into an in-memory store, a status endpoint is polled once per second, and a dedicated
modal shows a percent ring, per-stage job counts, and a live activity feed. The
recommendation service already emits a `progress_callback` with staged percentages
(`embedding` → `compensation` → `skills` → `scoring` → `llm` → `completed`); we enrich those
messages with job counts and wire the callback through.

## 2. Gaps & Unanswered Questions

- **Per-job vs per-stage percent** — the LLM verdict is issued in one batched `chat_many` call,
  so there is no per-job callback without reworking the client. *Assumption:* keep the existing
  stage-level percent for the ring, and surface job **counts** in the stage message + activity
  feed (e.g. "LLM fit verdict on 58 matches…", "Embedding 247 jobs…"). This satisfies "how many
  it is going through and % done" without a risky client rewrite.
- **Backward compatibility** — the synchronous `POST /api/recommend/analyze` is covered by tests
  and may be used elsewhere. *Assumption:* keep it, and add new `/api/recommend/analyze/start`
  + `/api/recommend/analyze/status/<job_id>` endpoints for the polled flow.
- **Cancel** — *Assumption:* closing the popup stops client polling (like `closeFind`); the
  background thread finishes server-side harmlessly (results still persist). No hard-abort.
- **Concurrent clicks** — *Assumption:* guard on the existing `analyzing` state so a second
  Analyze can't start while one is in flight.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Worktree + plan doc
- **Locations**: `docs/plans/analyze-progress-popup.md`; worktree `analyze-progress-popup`.
- **Rationale**: Record the design before coding, per repo rules.
- **Action**: Undergo validation for this phase (plan reviewed). Commit stating: Analyze
  Progress Popup (1/4) Complete: Worktree + plan doc.

### Step 2: Background analyze runner + status routes + count-rich progress
- **Locations**: `utils/backend/routes/recommend_routes.py` (new in-memory `analyze_tasks`
  store, `run_analyze_background`, `POST /api/recommend/analyze/start`, `GET
  /api/recommend/analyze/status/<job_id>`, mirroring `scrape_routes.py`);
  `utils/backend/recommend/service.py` (`analyze_jobs` emits count-rich messages for the
  compensation + LLM stages and a summary `completed` message; pass counts into `_report`).
- **Rationale**: The request must return immediately with a `job_id` and stream progress the UI
  can poll; the messages must carry the job counts the popup displays.
- **Action**: Undergo verification (route smoke test + `import app`). Commit stating: Analyze
  Progress Popup (2/4) Complete: Background analyze runner + status endpoint + count-rich stages.

### Step 3: Analyze progress popup (frontend)
- **Locations**: `utils/frontend/templates/index.html` — new modal overlay gated by
  `{{ analyzeOpen }}` (percent ring, stage, message, a Total/LLM-fit/Pay-recovered stats grid,
  and a live activity feed reusing the scrape feed's markup); `analyzeJobs()` rewritten to POST
  `/start` then `pollAnalyze(jobId)` (mirror `pollScrape`); new state fields (`analyzeOpen`,
  `aPercent`, `aStage`, `aStatusMsg`, `aEvents`, `aDone`, `aTotal`, `aLLM`, `aComp`);
  `closeAnalyze()`; render-map bindings for all of the above.
- **Rationale**: Deliver the visible popup showing count + percent, consistent with the existing
  scraping feed's look and interaction.
- **Action**: Undergo verification (frontend-wiring test + `import app`; in-browser smoke if
  preview available). Commit stating: Analyze Progress Popup (3/4) Complete: live progress modal
  + poll wiring.

### Step 4: Docs + tests + merge
- **Locations**: `tests/recommend/` or `tests/` (status-store/route unit test with a stubbed
  `analyze_jobs`); `docs/api-contract.md`, `docs/routes.md`, `docs/data-flow.md`,
  `docs/component-map.md`, `docs/checklist.md`.
- **Rationale**: Lock the endpoints/behavior and keep canonical docs in sync; then merge.
- **Action**: Undergo full verification (offline subset green, `import app` clean). Commit
  stating: Analyze Progress Popup (4/4) Complete: tests + docs + merge. Merge the worktree branch
  into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Background analyze runner | In-memory task store + `run_analyze_background` thread mirroring scrape | `utils/backend/routes/recommend_routes.py` |
| Start/status endpoints | `POST /api/recommend/analyze/start`, `GET /api/recommend/analyze/status/<id>` | `utils/backend/routes/recommend_routes.py` |
| Count-rich progress | `analyze_jobs` stage messages carry job counts + summary line | `utils/backend/recommend/service.py` |
| Analyze progress popup | Percent ring, stats grid, live feed modal + poll wiring | `utils/frontend/templates/index.html` |
| Route/store test | Status store + endpoint round-trip with a stubbed analyze | `tests/recommend/test_analyze_progress.py` |
| Docs update | Endpoints, routes, data flow, components, checklist | `docs/api-contract.md`, `docs/routes.md`, `docs/data-flow.md`, `docs/component-map.md`, `docs/checklist.md` |
