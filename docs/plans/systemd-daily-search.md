# Plan: Systemd Daily Job-Search (LLM-gated, boot + daily)

## 1. Introduction

This plan adds an automated, LLM-gated **daily job-search** that runs through
`systemd` on the developer's machine. On boot (and on a daily cadence) the search should start **if and only if the
local LLM is reachable**. If the LLM is not up yet, the runner re-checks
**every 10 minutes, up to 6 times (~1 hour total)**; the moment the LLM is
reachable it runs the scrape exactly once for that day. If all 6 checks fail,
the run **skips that day** (the day is marked consumed, so no further retry
happens until the next boot/daily trigger).

The approach keeps all decision logic in a small, testable Python package
(`utils/backend/scheduler/`) so it can be unit-tested offline, and uses a thin
**systemd user timer + oneshot service** to drive it. The bounded
"every 10 min ×6" retry lives **inside the runner** (an internal wait loop), so
the timer only needs a boot trigger and a daily trigger. The LLM "is it
running?" signal is an OpenAI-compatible `GET {base_url}/models` probe against
the endpoint already configured in `config/llm_endpoint_config.json`
(currently `http://localhost:9090/v1`, served by the existing
`llamacpp-router.service`). A once-per-calendar-day stamp under `data/`
guarantees the real scrape (or a give-up) happens at most once per day even if
both the boot and daily triggers fire.

Units are installed as **systemd user units** (the machine already has
`Linger=yes`, so user units start at boot) via a repo `install.sh` that renders
absolute paths for this checkout. This mirrors the existing
`~/.config/systemd/user/llamacpp-router.service` model.

## 2. Gaps & Unanswered Questions

- **Install + enable now vs. files-only** — *Resolved by user:* install **and**
  enable on this machine now (live at next boot). Verification will **not** kick
  off a live scrape.
- **Cadence** — *Resolved by user:* **boot + daily**. Implemented as
  `OnBootSec` (boot) + `OnCalendar` (daily), both with `Persistent=true`. The
  retry is **not** a timer beat: the runner itself re-checks the LLM every
  10 min up to 6 times. A once-per-day stamp guard makes the real scrape (or a
  give-up) happen at most once/day even if both triggers fire.
- **Retry window / give-up** — *Resolved by user:* re-check every **10 minutes,
  up to 6 attempts** (~1 hour). If the LLM never becomes reachable in that
  window, **skip the day** — the state file records the day as consumed so a
  later trigger the same day exits immediately.
- **"LLM is running" definition** — *Assumption:* endpoint reachability, i.e.
  `GET {base_url}/models` returns HTTP 200. This follows whatever endpoint is in
  `llm_endpoint_config.json` (auto-adapts if the port/host changes). A stricter
  "model can actually infer" check (`OpenAIClient.test_connection()`) is
  available but heavier; reachability is the right boot-gate.
- **Daily run time** — *Assumption:* a fixed daily `OnCalendar` anchor (default
  `*-*-* 09:00:00`, adjustable) plus the boot trigger, both `Persistent=true`
  so a missed run fires shortly after boot. Documented in
  `deploy/systemd/README.md`.
- **Python launcher** — *Assumption:* the unit runs `.venv/bin/python`
  (verified: CPython 3.12.13, `requests` present) rather than `uv run`, to avoid
  any lock/sync/network attempt at boot. `install.sh` errors clearly if the venv
  is missing.
- **Worktree vs. main for install** — *Assumption:* develop in the
  `systemd-daily-search` worktree, merge to `main`, then run `install.sh`
  **from the main checkout** so the installed unit's absolute paths point at the
  permanent location.

## 3. Hierarchical Step-by-Step Instructions

> Git note: per this task, each phase **commits** to git but does **NOT push**.
> Commit-message convention below matches the repo's existing per-phase style.

### Step 1: Worktree + plan doc
- **Locations**: worktree `.claude/worktrees/systemd-daily-search`;
  `docs/plans/systemd-daily-search.md` (this file).
- **Rationale**: Isolate the work per repo convention and record the agreed
  design/decisions before writing code.
- **Action**: Verify the worktree exists and the plan doc reads correctly. Once
  validated, commit: `Systemd Daily Search (1/5) Complete: worktree + plan doc.`

### Step 2: Scheduler Python package + CLI + tests
- **Locations**:
  - `utils/backend/scheduler/__init__.py`
  - `utils/backend/scheduler/llm_health.py` — `check_llm_ready(timeout=None) -> bool`
    (loads `load_llm_endpoint_config()`, probes `{base_url}/models`).
  - `utils/backend/scheduler/daily_runner.py` — `already_ran_today()`,
    `mark_ran_today()`, and
    `run_daily_search(force=False, check_only=False, max_attempts=6,
    interval_seconds=600, sleep_fn=time.sleep, today=None) -> int`.
    State file resolved via
    `get_project_root()/"data"/"daily_search_state.json"`. Loop: up to
    `max_attempts` LLM checks `interval_seconds` apart; on the first success run
    `execute_full_scraping_workflow(save_to_database=True)` once and stamp the
    day; if all attempts fail, log + stamp the day as `llm_unavailable` (skip).
    `sleep_fn`/`today` are injected so tests never actually sleep.
  - `utils/backend/scheduler/__main__.py` — argparse CLI: default = run,
    `--check-llm` (health only), `--force` (ignore stamp). Runnable via
    `python -m utils.backend.scheduler`.
  - `tests/scheduler/test_llm_health.py`, `tests/scheduler/test_daily_runner.py`.
- **Rationale**: Put the gate/guard/run logic in importable, unit-testable code
  (mock `requests` + `execute_full_scraping_workflow`) instead of brittle bash;
  the systemd unit only orchestrates.
- **Action**: Run `uv run pytest tests/scheduler` (offline, mocked) and
  `.venv/bin/python -m utils.backend.scheduler --check-llm` (exit 0 while the LLM
  is up). Do **not** run a live scrape. Once validated, commit:
  `Systemd Daily Search (2/5) Complete: LLM-health + daily-run scheduler package + CLI + tests.`

### Step 3: systemd unit templates + installer
- **Locations**:
  - `deploy/systemd/magnification-daily-search.service` (template, oneshot).
  - `deploy/systemd/magnification-daily-search.timer` (template:
    `OnBootSec`, `OnCalendar` daily, `Persistent=true`).
  - The service uses `Type=oneshot` with `TimeoutStartSec=infinity` because a
    single invocation may block up to ~1 hour (the 10-min ×6 retry) plus the
    scrape/LLM-fit time.
  - `deploy/systemd/install.sh` — renders `{{REPO_ROOT}}` / `{{PYTHON}}`
    placeholders from `git rev-parse --show-toplevel`, copies to
    `~/.config/systemd/user/`, `daemon-reload`, `enable` (no live start).
  - `deploy/systemd/uninstall.sh`, `deploy/systemd/README.md`.
- **Rationale**: Keep machine-specific absolute paths out of git; render correct
  units at install time. Ordered `After=`/`Wants=llamacpp-router.service` so the
  service nudges the LLM up and the health check gracefully waits.
- **Action**: `bash -n` the scripts; render a unit to the scratchpad and confirm
  substitution + `systemd-analyze verify` (or a syntax check) passes. Once
  validated, commit:
  `Systemd Daily Search (3/5) Complete: systemd user service + timer templates + installer.`

### Step 4: Documentation updates
- **Locations**: `docs/structure.md` (new `deploy/` + `utils/backend/scheduler/`),
  `docs/workflow.md` (install/enable/inspect/uninstall commands + venv-python
  note), `docs/documentation.md` (status line), `docs/checklist.md` (new DoD
  section), this plan doc (cross-links).
- **Rationale**: `docs/` is the single source of truth; new dirs/commands must be
  reflected in the same change.
- **Action**: `uv run pytest tests/docs` (skill-pointer/doc integrity). Once
  validated, commit:
  `Systemd Daily Search (4/5) Complete: docs for scheduler + systemd deploy.`

### Step 5: Merge to main, install + enable, verify
- **Locations**: `main` working tree; `~/.config/systemd/user/` (installed
  units); `deploy/systemd/install.sh`.
- **Rationale**: The installed unit must reference the permanent main checkout,
  so install happens after the merge, from main.
- **Action**: Merge `systemd-daily-search` → `main` (fix any conflicts); run the
  full offline test subset + `import app`; run `install.sh` from the main
  checkout; verify with `systemctl --user status`/`list-timers --all` and
  `python -m utils.backend.scheduler --check-llm`. Confirm the timer is
  **enabled** (live next boot) **without** triggering a live scrape now. Once
  validated, commit any merge/doc follow-ups:
  `Systemd Daily Search (5/5) Complete: merged, installed + enabled user timer, verified.`

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| LLM health check | Config-driven `GET {base_url}/models` reachability probe | `utils/backend/scheduler/llm_health.py` |
| Daily runner | Once-per-day guard + LLM gate + calls the scrape workflow | `utils/backend/scheduler/daily_runner.py` |
| Scheduler CLI | `python -m utils.backend.scheduler` (`--check-llm`, `--force`) | `utils/backend/scheduler/__main__.py` |
| Health-check tests | Mocked `requests` → True/False on 200 vs. error | `tests/scheduler/test_llm_health.py` |
| Runner tests | Stamp round-trip, skip/gate paths (mocked scrape) | `tests/scheduler/test_daily_runner.py` |
| systemd service | Oneshot unit template running the CLI | `deploy/systemd/magnification-daily-search.service` |
| systemd timer | Boot + hourly-beat timer template | `deploy/systemd/magnification-daily-search.timer` |
| Installer | Renders paths, installs, enables user units | `deploy/systemd/install.sh` |
| Uninstaller | Disables + removes installed units | `deploy/systemd/uninstall.sh` |
| Deploy README | How to install/inspect/change cadence | `deploy/systemd/README.md` |
| Docs updates | structure/workflow/documentation/checklist | `docs/*.md` |
