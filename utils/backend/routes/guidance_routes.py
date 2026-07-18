"""
Document Guidance API — read / edit / reset the single editable house-style document that steers
both the cover-letter and résumé generation graphs (see ``utils/backend/agents/document_guidance``).

Backs the Profile sidebar's **Guidance** tab. The guidance is plain text persisted to a gitignored
``config/document_guidance.json``; there is exactly one document (no per-kind rows), so these are
simple GET / PUT / reset endpoints.
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.agents import document_guidance

guidance_bp = Blueprint("guidance_bp", __name__)


@guidance_bp.route("/api/document-guidance", methods=["GET"])
def get_document_guidance():
    """Return the current guidance text and whether it is the built-in default."""
    return jsonify({
        "success": True,
        "guidance": document_guidance.get_guidance(),
        "is_default": document_guidance.is_default(),
    })


@guidance_bp.route("/api/document-guidance", methods=["PUT"])
def put_document_guidance():
    """Persist edited guidance. A blank string clears the override (reverts to default)."""
    data = request.get_json(silent=True) or {}
    text = data.get("guidance")
    if not isinstance(text, str):
        return jsonify({"success": False, "message": "guidance must be a string"}), 400
    if not document_guidance.set_guidance(text):
        return jsonify({"success": False, "message": "Failed to save guidance"}), 500
    logger.info("Document guidance updated.")
    return jsonify({
        "success": True,
        "guidance": document_guidance.get_guidance(),
        "is_default": document_guidance.is_default(),
    })


@guidance_bp.route("/api/document-guidance/reset", methods=["POST"])
def reset_document_guidance():
    """Remove any saved override so the built-in default is used again."""
    if not document_guidance.reset_guidance():
        return jsonify({"success": False, "message": "Failed to reset guidance"}), 500
    logger.info("Document guidance reset to default.")
    return jsonify({
        "success": True,
        "guidance": document_guidance.get_guidance(),
        "is_default": True,
    })
