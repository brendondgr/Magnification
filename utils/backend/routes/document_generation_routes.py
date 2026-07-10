"""
Document-generation API (design §5.2) — runs the cover-letter / résumé graphs as background
tasks and reads back the generated documents.

Kept in its own blueprint (``generation_bp``) so ``documents_routes`` stays focused on ingestion
+ supporting-document CRUD. Follows the async task+poll contract of ``recommend_routes`` exactly:
``.../start`` returns a ``task_id``; ``/status/<task_id>`` polls ``{status, progress, events,
results}``; ``/<task_id>/resume`` delivers a checkpoint decision to a paused graph.
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.agents import service

generation_bp = Blueprint("generation_bp", __name__)

_UPDATABLE_DOC_FIELDS = ("content", "status", "format")


def _start(kind: str):
    data = request.json or {}
    job_id = data.get("job_id")
    if not isinstance(job_id, int):
        return jsonify({"success": False, "message": "job_id (int) is required"}), 400
    if db_ops.get_job_by_id(job_id) is None:
        return jsonify({"success": False, "message": "Job not found"}), 404
    template_id = data.get("template_id")
    interactive = bool(data.get("interactive"))
    task_id = service.start_generation(kind, job_id, template_id=template_id, interactive=interactive)
    return jsonify({"success": True, "task_id": task_id, "kind": kind, "job_id": job_id})


@generation_bp.route("/api/documents/cover-letter/start", methods=["POST"])
def start_cover_letter():
    """Start a cover-letter generation. Body: ``{job_id, template_id?, interactive?}``."""
    return _start("cover_letter")


@generation_bp.route("/api/documents/resume/start", methods=["POST"])
def start_resume():
    """Start a résumé fine-tune. Body: ``{job_id, template_id?, interactive?}``."""
    return _start("resume")


@generation_bp.route("/api/documents/status/<task_id>", methods=["GET"])
def generation_status(task_id):
    """Poll a generation task: ``{status, progress, events, results, checkpoint}``."""
    rec = service.get_task(task_id)
    if not rec:
        return jsonify({"success": False, "message": "Task not found"}), 404
    return jsonify(rec)


@generation_bp.route("/api/documents/<task_id>/resume", methods=["POST"])
def resume_generation(task_id):
    """
    Resume a graph paused at a checkpoint. Body: ``{decision: approve|edit|reject, edits?}``.

    ``edits`` overrides the paused state — for the cover letter ``{thesis, hooks}``; for the
    résumé ``{plan}``.
    """
    data = request.json or {}
    decision = (data.get("decision") or "approve").strip().lower()
    edits = data.get("edits") or {}
    rec = service.resume_task(task_id, decision=decision, edits=edits)
    if rec is None:
        return jsonify({"success": False, "message": "Task not found"}), 404
    return jsonify({"success": True, "task": rec})


@generation_bp.route("/api/documents/<int:doc_id>", methods=["GET"])
def get_generated_document(doc_id):
    """Fetch a single generated document."""
    row = docs_ops.get_generated_document(doc_id)
    if row is None:
        return jsonify({"success": False, "message": "Document not found"}), 404
    return jsonify(row)


@generation_bp.route("/api/documents/<int:doc_id>", methods=["PATCH"])
def update_generated_document(doc_id):
    """Edit / approve a generated document. Body: ``{content?, status?, format?}``."""
    data = request.json or {}
    fields = {k: data[k] for k in _UPDATABLE_DOC_FIELDS if k in data}
    if not fields:
        return jsonify({"success": False, "message": "No updatable fields provided"}), 400
    if not docs_ops.update_generated_document(doc_id, fields):
        return jsonify({"success": False, "message": "Document not found"}), 404
    return jsonify({"success": True, "document": docs_ops.get_generated_document(doc_id)})
