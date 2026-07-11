"""
The in-house (plain-Python) orchestrator for the document-generation graphs.

We deliberately do **not** use LangGraph (a standing project decision). Instead a graph is
just an ordered pipeline of node functions that read/write a shared ``state`` dict, driven by a
small :class:`Orchestrator` that:

  * streams staged progress via a ``report`` callback (the same ``{stage, percent, details}``
    shape the recommend/scrape pipelines already emit, so the frontend reuses its polling code);
  * exposes :meth:`checkpoint` — a semi-auto pause point. With no ``resume_fn`` (the default,
    used by the non-interactive happy path and the offline tests) it **auto-approves** and returns
    immediately; with one (wired by the service layer to a ``threading.Event``) it blocks the
    background thread until the ``/resume`` route delivers the user's decision.

Node functions have the signature ``node(state: dict, orch: Orchestrator) -> None`` and mutate
``state`` in place. Every node degrades gracefully when ``state["client"]`` is ``None`` (no LLM
endpoint configured), producing a deterministic, user-editable fallback — so a graph always runs
to completion, online or off.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

# Revision loop cap shared by both graphs (design §2.1 / §3.1: "cap 2-3, then checkpoint").
MAX_REVISIONS = 2
# Minimum word count for an accepted cover letter (target band is 300-400 words). Enforced only
# on the LLM path — the deterministic offline fallback cannot grow to length.
COVER_MIN_WORDS = 280
# Cover-letter Critic acceptance score (0..100) and résumé match-lift floor (0..1).
COVER_SCORE_THRESHOLD = 75
MATCH_MIN_LIFT = 0.0


class GraphError(RuntimeError):
    """Raised when a graph cannot start (e.g. the job_id does not exist)."""


@dataclass
class Checkpoint:
    """A semi-auto pause point. ``decision`` ∈ {approve, edit, reject}; ``edits`` carries any
    user-supplied overrides applied when the graph resumes."""

    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    decision: str = "approve"
    edits: Dict[str, Any] = field(default_factory=dict)


# A resume_fn takes the pending Checkpoint and blocks until it can return a resolved one.
ResumeFn = Callable[[Checkpoint], Checkpoint]
# A report callback receives the recommend/scrape progress shape.
ReportFn = Callable[[Dict[str, Any]], None]


class Orchestrator:
    """Drives a node pipeline: progress reporting + semi-auto checkpoints."""

    def __init__(self, report: Optional[ReportFn] = None, resume_fn: Optional[ResumeFn] = None):
        self._report_cb = report
        self._resume_fn = resume_fn

    def report(self, stage: str, percent: int, message: str) -> None:
        """Emit one staged progress update (no-op when no callback is wired)."""
        if not self._report_cb:
            return
        try:
            self._report_cb({"stage": stage, "percent": percent, "details": {"message": message}})
        except Exception:  # pragma: no cover - a broken UI callback must not sink the graph
            pass

    def checkpoint(self, name: str, payload: Optional[Dict[str, Any]] = None) -> Checkpoint:
        """
        Reach a semi-auto checkpoint.

        Auto-approves (returns immediately) when no ``resume_fn`` is configured — the
        non-interactive default. Otherwise hands the pending checkpoint to the service layer,
        which blocks until the user resumes, then returns the resolved decision.
        """
        cp = Checkpoint(name=name, payload=payload or {})
        if self._resume_fn is None:
            return cp
        resolved = self._resume_fn(cp)
        return resolved or cp
