"""
Generation service: run the cover-letter / résumé graphs as background tasks and persist
their output — the glue between the graphs and the HTTP layer.

Mirrors ``recommend_routes``' async task+poll pattern exactly: an in-memory ``generation_tasks``
store, a daemon thread per run, staged progress events in the ``{status, progress, events,
results}`` shape the frontend already polls. Semi-auto checkpoints are implemented with a
``threading.Event``: at an interactive checkpoint the worker thread parks (status ``paused``,
``checkpoint`` exposed for the UI) until the ``/resume`` route delivers the decision. The finished
document is written to ``generated_documents`` (with the résumé match-lift and a
``checkpoint_state`` snapshot).
"""

import threading
import time
import uuid
from typing import Any, Dict, Optional

from loguru import logger

from ..database import documents_ops as docs_ops
from . import context, cover_letter, resume
from .orchestrator import Checkpoint, Orchestrator

# { task_id: {status, kind, job_id, progress, events, results, start_time, end_time, error,
#             checkpoint, _event, _decision} }  — underscore keys are stripped from API views.
generation_tasks: Dict[str, Dict[str, Any]] = {}

# Serializes the revise_from read-modify-write in _persist so two concurrent refines of the same
# document (e.g. an orphaned background thread + a fresh one) can't lose a revision bump.
_persist_lock = threading.Lock()

_GRAPHS = {"cover_letter": cover_letter, "resume": resume}


def _cleanup_old_tasks() -> None:
    """Drop finished tasks older than an hour to bound memory (mirrors recommend_routes)."""
    now = time.time()
    for tid in list(generation_tasks.keys()):
        rec = generation_tasks[tid]
        if rec.get("end_time") and (now - rec["end_time"] > 3600):
            del generation_tasks[tid]


def _append_event(rec: Dict[str, Any], update: Dict[str, Any]) -> None:
    msg = (update.get("details") or {}).get("message") or ""
    events = rec.setdefault("events", [])
    if msg and (not events or events[-1].get("message") != msg):
        events.append({
            "t": round(time.time() - rec.get("start_time", time.time()), 1),
            "stage": update.get("stage"),
            "percent": update.get("percent"),
            "message": msg,
        })
        if len(events) > 200:
            del events[:len(events) - 200]


def _checkpoint_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """A JSON-safe slice of graph state stored on the persisted document (design §5.1)."""
    keys = ("needs_review", "evaluation", "strategy", "gap", "plan", "critique",
            "truthful", "match_before", "match_after", "lift", "revision")
    return {k: state[k] for k in keys if k in state}


def _persist(kind: str, job_id: int, state: Dict[str, Any],
             revise_from: Optional[int] = None) -> int:
    """Persist the finished document. With ``revise_from`` set, update that row in place (bumping
    ``revision``) so a refine loop keeps one evolving draft per kind instead of accumulating rows."""
    payload: Dict[str, Any] = {
        "content": state.get("final") or "",
        # The graphs now render LaTeX; fall back to the template's format only if a graph didn't set one.
        "format": state.get("format") or (state.get("template") or {}).get("format") or "markdown",
        "status": "draft",
        "checkpoint_state": _checkpoint_snapshot(state),
    }
    if kind == "resume":
        payload["match_before"] = state.get("match_before")
        payload["match_after"] = state.get("match_after")

    if revise_from:
        with _persist_lock:  # atomic revision read-modify-write across concurrent refines
            existing = docs_ops.get_generated_document(revise_from)
            if existing and existing.get("job_id") == job_id and existing.get("kind") == kind:
                payload["revision"] = (existing.get("revision") or 1) + 1
                docs_ops.update_generated_document(revise_from, payload)
                return revise_from

    payload["job_id"] = job_id
    payload["kind"] = kind
    payload["revision"] = state.get("revision", 1)
    return docs_ops.create_generated_document(payload)


def _result_payload(kind: str, job_id: int, doc_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "success": True,
        "document_id": doc_id,
        "job_id": job_id,
        "kind": kind,
        "content": state.get("final") or "",
        "needs_review": state.get("needs_review", False),
    }
    if kind == "resume":
        out.update({"match_before": state.get("match_before"),
                    "match_after": state.get("match_after"),
                    "lift": state.get("lift")})
        out["evaluation"] = None
    else:
        out["evaluation"] = state.get("evaluation")
        out["critique"] = state.get("critique")
    return out


def _run(task_id: str, kind: str, job_id: int, template_id: Optional[int],
         interactive: bool, instructions: str = "", prior_content: str = "",
         revise_from: Optional[int] = None) -> None:
    rec = generation_tasks[task_id]
    rec["status"] = "running"

    def report(update: Dict[str, Any]) -> None:
        rec["progress"] = update
        _append_event(rec, update)

    def resume_fn(pending: Checkpoint) -> Checkpoint:
        rec["status"] = "paused"
        rec["checkpoint"] = {"name": pending.name, "payload": pending.payload}
        rec["_event"].clear()
        rec["_event"].wait()  # park the worker until the /resume route delivers a decision
        decision = rec.get("_decision") or {}
        rec["status"] = "running"
        rec["checkpoint"] = None
        return Checkpoint(name=pending.name, payload=pending.payload,
                          decision=decision.get("decision", "approve"),
                          edits=decision.get("edits") or {})

    try:
        state = context.load_context(job_id, kind, template_id,
                                     instructions=instructions, prior_content=prior_content)
        state["interactive"] = interactive
        orch = Orchestrator(report=report, resume_fn=resume_fn if interactive else None)
        state = _GRAPHS[kind].run(state, orch)
        doc_id = _persist(kind, job_id, state, revise_from=revise_from)
        rec["results"] = _result_payload(kind, job_id, doc_id, state)
        rec["status"] = "completed"
    except Exception as e:
        logger.error(f"Document generation failed ({kind}, job {job_id}): {e}")
        rec["status"] = "failed"
        rec["error"] = str(e)
    finally:
        rec["end_time"] = time.time()


def start_generation(kind: str, job_id: int, template_id: Optional[int] = None,
                     interactive: bool = False, instructions: str = "",
                     prior_content: str = "", revise_from: Optional[int] = None) -> str:
    """Create a task record + spawn the graph in a daemon thread. Returns the task id.

    ``instructions`` + ``prior_content`` steer a refine re-run; ``revise_from`` (a doc id) makes the
    result update that document in place instead of creating a new one.
    """
    if kind not in _GRAPHS:
        raise ValueError(f"Unknown generation kind: {kind}")
    _cleanup_old_tasks()
    task_id = f"{kind}_{uuid.uuid4().hex[:8]}"
    generation_tasks[task_id] = {
        "status": "pending",
        "kind": kind,
        "job_id": job_id,
        "progress": {"stage": "pending", "percent": 0, "details": {}},
        "events": [],
        "results": None,
        "checkpoint": None,
        "start_time": time.time(),
        "_event": threading.Event(),
        "_decision": None,
    }
    thread = threading.Thread(
        target=_run,
        args=(task_id, kind, job_id, template_id, interactive, instructions, prior_content, revise_from),
        daemon=True)
    thread.start()
    return task_id


def resume_task(task_id: str, decision: str = "approve",
                edits: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Deliver a checkpoint decision to a parked task and unblock its worker thread."""
    rec = generation_tasks.get(task_id)
    if not rec:
        return None
    rec["_decision"] = {"decision": decision, "edits": edits or {}}
    rec["_event"].set()
    return get_task(task_id)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Return a JSON-safe view of a task (internal ``_`` keys stripped)."""
    rec = generation_tasks.get(task_id)
    if not rec:
        return None
    return {k: v for k, v in rec.items() if not k.startswith("_")}
