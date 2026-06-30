"""
Profile API: load/save the active recommendation profile and build a draft profile
from an uploaded resume (PDF / LaTeX / Markdown).

Upload/build return an editable *draft* (nothing is persisted); the client edits it
and POSTs /api/profile to save. This keeps the resume bytes off disk and lets the
user correct the LLM's output before it becomes the active profile.
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.llm.config import load_llm_endpoint_config
from utils.backend.llm.client import OpenAIClient
from utils.backend.recommend.profile_builder import (
    extract_resume_text,
    build_profile_from_text,
    EMPTY_PROFILE,
)

profile_bp = Blueprint("profile_bp", __name__)

_SUPPORTED_EXTS = (".pdf", ".tex", ".md", ".markdown", ".txt")


@profile_bp.route("/api/profile", methods=["GET"])
def get_profile():
    """Return the active profile, or an empty skeleton if none exists yet."""
    profile = db_ops.get_active_profile()
    if profile is None:
        return jsonify({"exists": False, **EMPTY_PROFILE})
    profile["exists"] = True
    return jsonify(profile)


@profile_bp.route("/api/profile", methods=["POST"])
def save_profile():
    """Upsert the active profile from edited fields."""
    data = request.json or {}
    fields = {
        k: data[k]
        for k in ("name", "source_filename", "resume_text", "interests_paragraph",
                  "skills", "job_titles", "keyword_groups")
        if k in data
    }
    profile_id = db_ops.upsert_active_profile(fields)
    saved = db_ops.get_profile_by_id(profile_id)
    return jsonify({"success": True, "profile": saved})


@profile_bp.route("/api/profile/upload", methods=["POST"])
def upload_resume():
    """
    Extract text from an uploaded resume and (if the LLM is enabled) build a draft
    profile. Returns the draft + extracted text; does NOT persist.
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

    try:
        text = extract_resume_text(name, file.read())
    except Exception as e:
        logger.error(f"Resume text extraction failed: {e}")
        return jsonify({"success": False, "message": f"Could not read resume: {e}"}), 400

    draft, llm_used, llm_error = _build_draft(text)
    return jsonify({
        "success": True,
        "source_filename": name,
        "resume_text": text,
        "profile": draft,
        "llm_used": llm_used,
        "llm_error": llm_error,
    })


@profile_bp.route("/api/profile/build", methods=["POST"])
def build_profile():
    """(Re)build a draft profile from already-extracted resume text (requires LLM)."""
    data = request.json or {}
    text = (data.get("resume_text") or "").strip()
    if not text:
        return jsonify({"success": False, "message": "resume_text is required"}), 400
    draft, llm_used, llm_error = _build_draft(text)
    if not llm_used:
        return jsonify({"success": False, "message": llm_error or "LLM is not enabled"}), 400
    return jsonify({"success": True, "profile": draft, "llm_used": True})


def _build_draft(text):
    """Try to build a profile draft via the LLM; fall back to an empty manual draft."""
    config = load_llm_endpoint_config()
    if not config.get("enabled"):
        return dict(EMPTY_PROFILE), False, "LLM endpoint disabled"
    try:
        client = OpenAIClient.from_config(config)
        return build_profile_from_text(text, client), True, None
    except Exception as e:
        logger.error(f"LLM profile build failed: {e}")
        return dict(EMPTY_PROFILE), False, str(e)
