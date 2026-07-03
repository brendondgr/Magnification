"""CLI entry point: ``python -m utils.backend.scheduler``.

Invoked by the systemd oneshot service (see ``deploy/systemd/``). Exit code 0
means the day is handled (ran, skipped, or gave up waiting for the LLM);
non-zero means an actual error worth surfacing in ``systemctl status``.
"""

from __future__ import annotations

import argparse
import sys

from .daily_runner import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    run_daily_search,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m utils.backend.scheduler",
        description="LLM-gated daily job search (systemd-driven).",
    )
    parser.add_argument(
        "--check-llm",
        action="store_true",
        help="Only probe the LLM endpoint; exit 0 if reachable, 1 otherwise. No scrape.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if today's search was already handled.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"LLM re-check attempts before skipping the day (default {DEFAULT_MAX_ATTEMPTS}).",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"Seconds between LLM re-checks (default {DEFAULT_INTERVAL_SECONDS}).",
    )
    args = parser.parse_args(argv)
    return run_daily_search(
        force=args.force,
        check_only=args.check_llm,
        max_attempts=args.max_attempts,
        interval_seconds=args.interval_seconds,
    )


if __name__ == "__main__":
    sys.exit(main())
