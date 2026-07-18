"""
Document-generation API (design §5.2) — runs the cover-letter / résumé graphs as background
tasks and reads back the generated documents.

Kept in its own blueprint (``generation_bp``) so ``documents_routes`` stays focused on ingestion
+ supporting-document CRUD. Follows the async task+poll contract of ``recommend_routes`` exactly:
``.../start`` returns a ``task_id``; ``/status/<task_id>`` polls ``{status, progress, events,
results}``; ``/<task_id>/resume`` delivers a checkpoint decision to a paused graph.
"""

from flask import Blueprint, request, jsonify, send_file
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.agents import service
from utils.backend.pdf_compile import compile_pdf, LatexCompileError

generation_bp = Blueprint("generation_bp", __name__)

_UPDATABLE_DOC_FIELDS = ("content", "status", "format")


def _is_latex(row) -> bool:
    fmt = (row.get("format") or "").lower()
    return fmt == "latex" or (row.get("content") or "").lstrip().startswith("\\documentclass")


def _start(kind: str):
    data = request.json or {}
    job_id = data.get("job_id")
    if not isinstance(job_id, int):
        return jsonify({"success": False, "message": "job_id (int) is required"}), 400
    if db_ops.get_job_by_id(job_id) is None:
        return jsonify({"success": False, "message": "Job not found"}), 404
    interactive = bool(data.get("interactive"))
    instructions = (data.get("instructions") or "").strip()

    # A refine re-run: update the named draft in place and build on its current content.
    revise_from = data.get("revise_from")
    prior_content = ""
    if isinstance(revise_from, int):
        prev = docs_ops.get_generated_document(revise_from)
        prior_content = (prev or {}).get("content") or "" if prev else ""
    else:
        revise_from = None

    task_id = service.start_generation(
        kind, job_id, interactive=interactive,
        instructions=instructions, prior_content=prior_content, revise_from=revise_from)
    return jsonify({"success": True, "task_id": task_id, "kind": kind, "job_id": job_id})


@generation_bp.route("/api/documents/cover-letter/start", methods=["POST"])
def start_cover_letter():
    """Start a cover-letter generation.

    Body: ``{job_id, interactive?, instructions?, revise_from?}``. ``instructions`` is
    Application-Mode guidance for a steered re-run; ``revise_from`` (a doc id) updates that draft in
    place, building on its current content.
    """
    return _start("cover_letter")


@generation_bp.route("/api/documents/resume/start", methods=["POST"])
def start_resume():
    """Start a résumé fine-tune. Body: ``{job_id, interactive?, instructions?,
    revise_from?}`` (same refine semantics as the cover-letter start)."""
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


@generation_bp.route("/api/documents/<int:doc_id>/pdf", methods=["GET"])
def get_generated_document_pdf(doc_id):
    """Compile the document's LaTeX source to a PDF and stream it.

    Served inline for the review-pane preview; ``?download=1`` sets an attachment disposition.
    Returns 404 (no doc), 415 (not a LaTeX doc), or 422 (compile failed, with the log tail).
    """
    row = docs_ops.get_generated_document(doc_id)
    if row is None:
        return jsonify({"success": False, "message": "Document not found"}), 404
    if not _is_latex(row):
        return jsonify({"success": False, "message": "Document is not LaTeX; no PDF preview."}), 415
    try:
        pdf_path = compile_pdf(doc_id, row.get("content") or "")
    except LatexCompileError as e:
        return jsonify({"success": False, "message": str(e), "log": getattr(e, "log", "")}), 422

    download = request.args.get("download") in ("1", "true", "yes")
    name = ("resume" if row.get("kind") == "resume" else "cover_letter") + f"_{doc_id}.pdf"
    return send_file(str(pdf_path), mimetype="application/pdf",
                     as_attachment=download, download_name=name, max_age=0)


@generation_bp.route("/api/documents/<int:doc_id>/tex", methods=["GET"])
def get_generated_document_tex(doc_id):
    """Download the raw LaTeX source of a generated document."""
    row = docs_ops.get_generated_document(doc_id)
    if row is None:
        return jsonify({"success": False, "message": "Document not found"}), 404
    name = ("resume" if row.get("kind") == "resume" else "cover_letter") + f"_{doc_id}.tex"
    return (row.get("content") or ""), 200, {
        "Content-Type": "application/x-tex; charset=utf-8",
        "Content-Disposition": f'attachment; filename="{name}"',
    }


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
