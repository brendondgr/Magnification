# Systemd deploy — LLM-gated daily job search

These are **systemd user units** that run Magnification's daily job search
automatically. The machine already runs the local LLM as a user service
(`llamacpp-router.service`) and has lingering enabled (`loginctl enable-linger`),
so user units start at boot without a login.

## What it does

On boot (and once per day) the timer starts a oneshot service that runs
`python -m utils.backend.scheduler`. That runner:

1. Skips immediately if today's search was already handled (a once-per-day stamp
   at `data/daily_search_state.json`).
2. Otherwise probes the LLM (`GET {base_url}/models`, endpoint from
   `config/llm_endpoint_config.json`). It re-checks **every 10 minutes, up to 6
   times (~1 hour)**.
3. The first time the LLM is reachable, it runs the full scrape + analysis once
   and stamps the day.
4. If all 6 checks fail, it logs and **skips the day** (stamps it as
   `llm_unavailable`); nothing retries until the next boot/daily trigger.

The retry loop lives in the Python runner, so the units stay simple.

## Files

| File | Purpose |
| --- | --- |
| `magnification-daily-search.service` | Oneshot unit; runs the scheduler CLI. Template (`{{REPO_ROOT}}`, `{{PYTHON}}`). |
| `magnification-daily-search.timer` | Boot (`OnBootSec`) + daily (`OnCalendar`) trigger. Template. |
| `install.sh` | Renders + installs + enables the units for this checkout. |
| `uninstall.sh` | Disables + removes the installed units. |

## Install

Run from the checkout the units should point at (normally the **main** checkout):

```bash
deploy/systemd/install.sh          # install + enable (live at next boot)
deploy/systemd/install.sh --now    # also start the timer in this session
```

`install.sh` requires a working venv at `.venv/bin/python` (it does not use
`uv run`, to avoid any lock/sync/network attempt at boot).

## Inspect / operate

```bash
systemctl --user list-timers magnification-daily-search.timer --all
systemctl --user status magnification-daily-search.service
journalctl --user -u magnification-daily-search.service -e

# Probe the LLM gate without scraping (exit 0 = reachable):
.venv/bin/python -m utils.backend.scheduler --check-llm ; echo exit=$?

# Trigger a run now:
systemctl --user start magnification-daily-search.service   # honors once-per-day guard
.venv/bin/python -m utils.backend.scheduler --force         # bypasses the guard
```

## Change the schedule / retry

- **Daily time:** edit `OnCalendar=` in the timer (e.g. `*-*-* 07:30:00`), then
  re-run `install.sh` (or `systemctl --user daemon-reload`).
- **Retry cadence:** the runner defaults to 6 checks × 10 min. Override per-run
  with `--max-attempts` / `--interval-seconds`, or edit `ExecStart` in the
  service template.

## Uninstall

```bash
deploy/systemd/uninstall.sh
```
