"""Once-per-day, LLM-gated driver for the scraping workflow.

Behaviour (see ``docs/plans/systemd-daily-search.md``):

* At most one real run per calendar day. A small stamp file under ``data/``
  (shared across the main checkout and every worktree via ``get_project_root``)
  records the day as consumed once a run cycle finishes — success *or* give-up.
* On each invocation the runner re-checks the LLM up to ``max_attempts`` times,
  ``interval_seconds`` apart. The first time the LLM is reachable it runs the
  scrape once and stamps the day. If every attempt fails, it logs, stamps the
  day as ``llm_unavailable`` and skips (no scrape until the next day's trigger).

``execute_full_scraping_workflow`` is imported lazily and ``time.sleep`` is
injectable so the unit tests stay offline and instant.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from ..paths import get_project_root
from .llm_health import check_llm_ready

DEFAULT_MAX_ATTEMPTS = 6
DEFAULT_INTERVAL_SECONDS = 600  # 10 minutes → 6 attempts ≈ 1 hour


def get_state_path() -> Path:
    """Path of the once-per-day stamp file (in the shared ``data/`` root)."""
    return get_project_root() / "data" / "daily_search_state.json"


def _load_state(state_path: Path) -> dict:
    try:
        with open(state_path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def already_ran_today(today: date, state_path: Path) -> bool:
    """True if a run cycle (success or give-up) was already recorded for ``today``."""
    return _load_state(state_path).get("last_run_date") == today.isoformat()


def mark_ran_today(today: date, state_path: Path, status: str, attempts: int) -> None:
    """Record that ``today``'s single run cycle completed (with any outcome)."""
    state = _load_state(state_path)
    state.update(
        {
            "last_run_date": today.isoformat(),
            "last_status": status,
            "last_run_at": datetime.now().isoformat(timespec="seconds"),
            "attempts": attempts,
        }
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    tmp.replace(state_path)  # atomic on the same filesystem


def run_daily_search(
    force: bool = False,
    check_only: bool = False,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    today: Optional[date] = None,
    state_path: Optional[Path] = None,
    check_llm: Callable[[], bool] = check_llm_ready,
) -> int:
    """Run (or skip) today's LLM-gated job search. Returns a process exit code.

    Exit code 0 means the day is handled (ran, skipped, or gave up because the
    LLM never came up); non-zero means an actual error worth surfacing in
    ``systemctl status``.
    """
    if today is None:
        today = date.today()
    if state_path is None:
        state_path = get_state_path()

    if check_only:
        ready = check_llm()
        logger.info(f"LLM readiness check: {'ready' if ready else 'not ready'}")
        return 0 if ready else 1

    if not force and already_ran_today(today, state_path):
        logger.info(f"Daily search already handled for {today.isoformat()}; skipping.")
        return 0

    for attempt in range(1, max_attempts + 1):
        if check_llm():
            logger.info(f"LLM reachable (attempt {attempt}/{max_attempts}); starting daily search.")
            try:
                from ..scrapers.scraping_service import execute_full_scraping_workflow

                result = execute_full_scraping_workflow(save_to_database=True)
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Daily search workflow raised: {e}")
                mark_ran_today(today, state_path, "scrape_error", attempt)
                return 1

            ok = bool(result.get("success"))
            mark_ran_today(today, state_path, "success" if ok else "scrape_failed", attempt)
            if ok:
                logger.info(
                    "Daily search complete: "
                    f"found={result.get('jobs_found')} kept={result.get('jobs_kept')} "
                    f"added={result.get('jobs_added')}."
                )
                return 0
            logger.error(f"Daily search finished with errors: {result.get('errors')}")
            return 1

        if attempt < max_attempts:
            logger.info(
                f"LLM not reachable (attempt {attempt}/{max_attempts}); "
                f"retrying in {interval_seconds}s."
            )
            sleep_fn(interval_seconds)
        else:
            logger.warning(
                f"LLM not reachable after {max_attempts} attempts; "
                f"skipping today ({today.isoformat()})."
            )
            mark_ran_today(today, state_path, "llm_unavailable", attempt)
            return 0

    return 0  # pragma: no cover - loop always returns
