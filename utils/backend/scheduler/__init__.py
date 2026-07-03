"""Scheduled, LLM-gated daily job-search entry points (systemd-driven).

See ``deploy/systemd/`` for the units that invoke this package and
``docs/plans/systemd-daily-search.md`` for the design.
"""

from .daily_runner import run_daily_search
from .llm_health import check_llm_ready

__all__ = ["run_daily_search", "check_llm_ready"]
