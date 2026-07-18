"""
Documents API: the per-job **application-fit evaluation** and the **generated-documents** listing
for the Agentic Document System.

The Behavioral / Writing-Style / Template subsystems and the upload→ingest→draft pipeline were
retired in favor of a single editable Document Guidance document (see
``utils/backend/routes/guidance_routes.py`` and ``utils/backend/agents/document_guidance.py``); the
generation graphs now run off the profile + that guidance. What remains here is the job-evaluation
record the cover-letter graph writes and the read-only generated-documents list.
"""

from flask import Blueprint, request, jsonify

from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops

documents_bp = Blueprint("documents_bp", __name__)


# ==================== Job evaluation ====================

@documents_bp.route("/api/job-evaluation/<int:job_id>", methods=["GET"])
def get_job_evaluation(job_id):
    """Return the application-fit evaluation for a job, or {exists: False}."""
    row = docs_ops.get_job_evaluation(job_id)
    if row is None:
        return jsonify({"exists": False, "job_id": job_id})
    row["exists"] = True
    return jsonify(row)


@documents_bp.route("/api/job-evaluation/<int:job_id>", methods=["POST"])
def save_job_evaluation(job_id):
    """Upsert the application-fit evaluation for a job."""
    if db_ops.get_job_by_id(job_id) is None:
        return jsonify({"success": False, "message": "Job not found"}), 404
    data = request.json or {}
    fields = {k: data[k] for k in ("verdict", "fit_score", "emphasize", "gaps",
                                   "risks", "talking_points") if k in data}
    active = db_ops.get_active_profile()
    profile_id = active["id"] if active else None
    docs_ops.save_job_evaluation(job_id, fields, profile_id=profile_id)
    return jsonify({"success": True, "evaluation": docs_ops.get_job_evaluation(job_id)})


# ==================== Generated documents (read-only) ====================

@documents_bp.route("/api/documents", methods=["GET"])
def list_generated():
    """List generated documents for a job (?job_id=)."""
    job_id = request.args.get("job_id", type=int)
    if job_id is None:
        return jsonify({"success": False, "message": "job_id is required"}), 400
    return jsonify({"documents": docs_ops.list_generated_documents(job_id)})
