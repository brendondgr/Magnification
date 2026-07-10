"""
Documents API: the ingestion agent + supporting-document CRUD for the Agentic
Document System (design §5.2).

Mirrors the résumé flow's upload→draft→edit→save contract (see profile_routes):
`/api/documents/ingest` runs the ingestion agent and returns an editable *draft*
(nothing persisted); `/api/documents/ingest/save` persists the approved record to its
target table and logs the raw upload with a link back to what it produced. The
behavioral / writing-style / template / job-evaluation routes are plain upsert-active-row
CRUD, matching `/api/profile`.
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.agents.ingestion import ingest_document, DOC_TYPES

documents_bp = Blueprint("documents_bp", __name__)

_SUPPORTED_EXTS = (".pdf", ".tex", ".md", ".markdown", ".txt")


# ==================== Ingestion ====================

@documents_bp.route("/api/documents/ingest", methods=["POST"])
def ingest():
    """
    Run the ingestion agent on an uploaded file and return a drafted record.

    Multipart form: ``file`` (required), ``doc_type`` (optional — inferred when absent).
    Nothing is persisted; the client edits the draft and POSTs /api/documents/ingest/save.
    """
    file = request.files.get("file")
    if file is None or not file.filename:
        return jsonify({"success": False, "message": "No file provided"}), 400
    name = file.filename
    if not name.lower().endswith(_SUPPORTED_EXTS):
        return jsonify({
            "success": False,
            "message": f"Unsupported file type. Use one of: {', '.join(_SUPPORTED_EXTS)}",
        }), 400

    doc_type = (request.form.get("doc_type") or "").strip().lower() or None
    try:
        result = ingest_document(name, file.read(), doc_type=doc_type)
    except Exception as e:  # pragma: no cover - defensive; agent already guards internally
        logger.error(f"Ingestion failed: {e}")
        return jsonify({"success": False, "message": f"Ingestion failed: {e}"}), 400

    return jsonify({
        "success": True,
        "filename": name,
        "doc_type": result["doc_type"],
        "target_table": result["target_table"],
        "draft": result["draft"],
        "summary": result["summary"],
        "raw_text": result["raw_text"],
        "llm_used": result["llm_used"],
        "llm_error": result["llm_error"],
    })


@documents_bp.route("/api/documents/ingest/save", methods=["POST"])
def ingest_save():
    """
    Persist an approved ingested record to its target table + log the raw upload.

    Body: ``{doc_type, target_table, record, filename?, raw_text?, summary?}``. The record is
    upserted into the active row of its target table (profiles / behavioral / writing) or, for
    reference/other, kept as a summary on the upload log only. An ``uploaded_documents`` row is
    written linking the raw file to the record it produced (``derived_table``/``derived_id``).
    """
    data = request.json or {}
    doc_type = (data.get("doc_type") or "").strip().lower()
    target_table = data.get("target_table") or None
    record = data.get("record") or {}
    filename = data.get("filename")
    raw_text = data.get("raw_text") or ""
    summary = data.get("summary") or ""

    if doc_type and doc_type not in DOC_TYPES:
        return jsonify({"success": False, "message": f"Unknown doc_type: {doc_type}"}), 400
    if not isinstance(record, dict):
        return jsonify({"success": False, "message": "record must be an object"}), 400

    derived_id = None
    try:
        if target_table == "profiles":
            payload = dict(record)
            if filename:
                payload.setdefault("source_filename", filename)
            if raw_text:
                payload.setdefault("resume_text", raw_text)
            derived_id = db_ops.upsert_active_profile(payload)
        elif target_table == "behavioral_profiles":
            derived_id = docs_ops.upsert_active_behavioral_profile(
                {**record, "source_filename": filename}
            )
        elif target_table == "writing_style_profiles":
            derived_id = docs_ops.upsert_active_writing_style(
                {**record, "source_filename": filename}
            )
        elif target_table in (None, "", "uploaded_documents"):
            target_table = None  # reference / other → summary-only
            summary = summary or record.get("summary") or ""
        else:
            return jsonify({"success": False, "message": f"Unknown target_table: {target_table}"}), 400
    except Exception as e:
        logger.error(f"ingest/save persist failed: {e}")
        return jsonify({"success": False, "message": f"Could not save record: {e}"}), 400

    uploaded_id = docs_ops.create_uploaded_document({
        "filename": filename,
        "doc_type": doc_type or None,
        "raw_text": raw_text,
        "summary": summary,
        "derived_table": target_table,
        "derived_id": derived_id,
        "status": "saved",
    })

    return jsonify({
        "success": True,
        "derived_table": target_table,
        "derived_id": derived_id,
        "uploaded_id": uploaded_id,
    })


@documents_bp.route("/api/documents/uploaded", methods=["GET"])
def list_uploaded():
    """List raw uploads (newest first), each linked to the record it produced."""
    return jsonify({"documents": docs_ops.list_uploaded_documents()})


# ==================== Behavioral profile ====================

@documents_bp.route("/api/behavioral-profile", methods=["GET"])
def get_behavioral():
    """Return the active behavioral profile, or {exists: False}."""
    row = docs_ops.get_active_behavioral_profile()
    if row is None:
        return jsonify({"exists": False})
    row["exists"] = True
    return jsonify(row)


@documents_bp.route("/api/behavioral-profile", methods=["POST"])
def save_behavioral():
    """Upsert the active behavioral profile from edited fields."""
    data = request.json or {}
    fields = {k: data[k] for k in ("name", "traits", "strengths", "work_style_paragraph",
                                   "source_filename") if k in data}
    profile_id = docs_ops.upsert_active_behavioral_profile(fields)
    return jsonify({"success": True, "profile": docs_ops.get_active_behavioral_profile(),
                    "id": profile_id})


# ==================== Writing style ====================

@documents_bp.route("/api/writing-style", methods=["GET"])
def get_writing_style():
    """Return the active writing-style profile, or {exists: False}."""
    row = docs_ops.get_active_writing_style()
    if row is None:
        return jsonify({"exists": False})
    row["exists"] = True
    return jsonify(row)


@documents_bp.route("/api/writing-style", methods=["POST"])
def save_writing_style():
    """Upsert the active writing-style profile from edited fields."""
    data = request.json or {}
    fields = {k: data[k] for k in ("name", "tone", "formality", "sentence_length",
                                   "sample_text", "dos", "donts", "source_filename") if k in data}
    profile_id = docs_ops.upsert_active_writing_style(fields)
    return jsonify({"success": True, "profile": docs_ops.get_active_writing_style(),
                    "id": profile_id})


# ==================== Templates ====================

@documents_bp.route("/api/templates", methods=["GET"])
def list_templates():
    """List templates, optionally filtered by ?kind=cover_letter|resume|job_evaluation."""
    kind = (request.args.get("kind") or "").strip() or None
    return jsonify({"templates": docs_ops.list_templates(kind)})


@documents_bp.route("/api/templates", methods=["POST"])
def create_template():
    """Create a template. Body: {kind, name, body, format?, is_default?}."""
    data = request.json or {}
    if not (data.get("kind") or "").strip():
        return jsonify({"success": False, "message": "kind is required"}), 400
    fields = {k: data[k] for k in ("kind", "name", "body", "format", "is_default") if k in data}
    template_id = docs_ops.create_template(fields)
    return jsonify({"success": True, "template": docs_ops.get_template(template_id)})


@documents_bp.route("/api/templates/<int:template_id>", methods=["GET"])
def get_template(template_id):
    """Return a single template, or 404."""
    row = docs_ops.get_template(template_id)
    if row is None:
        return jsonify({"success": False, "message": "Template not found"}), 404
    return jsonify(row)


@documents_bp.route("/api/templates/<int:template_id>", methods=["PATCH"])
def update_template(template_id):
    """Update a template's fields."""
    data = request.json or {}
    fields = {k: data[k] for k in ("kind", "name", "body", "format", "is_default") if k in data}
    if not docs_ops.update_template(template_id, fields):
        return jsonify({"success": False, "message": "Template not found"}), 404
    return jsonify({"success": True, "template": docs_ops.get_template(template_id)})


@documents_bp.route("/api/templates/<int:template_id>", methods=["DELETE"])
def delete_template(template_id):
    """Delete a template."""
    deleted = docs_ops.delete_template(template_id)
    if not deleted:
        return jsonify({"success": False, "message": "Template not found"}), 404
    return jsonify({"success": True, "deleted": template_id})


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


# ==================== Generated documents (read-only for now) ====================

@documents_bp.route("/api/documents", methods=["GET"])
def list_generated():
    """List generated documents for a job (?job_id=). Empty until the generation graphs land."""
    job_id = request.args.get("job_id", type=int)
    if job_id is None:
        return jsonify({"success": False, "message": "job_id is required"}), 400
    return jsonify({"documents": docs_ops.list_generated_documents(job_id)})
