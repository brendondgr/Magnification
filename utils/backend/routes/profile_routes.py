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
    normalize_profile,
    EMPTY_PROFILE,
)
from utils.backend.scrapers.job_filter import apply_profile_filters

profile_bp = Blueprint("profile_bp", __name__)

_SUPPORTED_EXTS = (".pdf", ".tex", ".md", ".markdown", ".txt")


def _clean_block_fields(fields):
    """Normalize the block-related fields in place (scopes on groups, string lists)."""
    if "keyword_groups" in fields or "blocked_companies" in fields or "title_blocklist" in fields:
        norm = normalize_profile({
            "keyword_groups": fields.get("keyword_groups", []),
            "blocked_companies": fields.get("blocked_companies", []),
            "title_blocklist": fields.get("title_blocklist", []),
        })
        if "keyword_groups" in fields:
            fields["keyword_groups"] = norm["keyword_groups"]
        if "blocked_companies" in fields:
            fields["blocked_companies"] = norm["blocked_companies"]
        if "title_blocklist" in fields:
            fields["title_blocklist"] = norm["title_blocklist"]
    return fields


@profile_bp.route("/api/profile", methods=["GET"])
def get_profile():
    """Return the active profile, or an empty skeleton if none exists yet."""
    profile = db_ops.get_active_profile()
    if profile is None:
        return jsonify({"exists": False, **EMPTY_PROFILE, "favorite_companies": []})
    profile["exists"] = True
    return jsonify(profile)


@profile_bp.route("/api/profile", methods=["POST"])
def save_profile():
    """
    Upsert the active profile from edited fields, then re-apply the profile's block rules to
    the existing feed so blocklist/keyword-group edits take effect immediately (one-directional:
    matching jobs are hidden; nothing is un-hidden — a re-scrape re-evaluates from scratch).
    """
    data = request.json or {}
    fields = {
        k: data[k]
        for k in ("name", "source_filename", "resume_text", "interests_paragraph",
                  "skills", "job_titles", "keyword_groups",
                  "blocked_companies", "title_blocklist", "llm_instructions")
        if k in data
    }
    _clean_block_fields(fields)
    profile_id = db_ops.upsert_active_profile(fields)
    hidden = 0
    try:
        hidden = apply_profile_filters().get("blocked", 0)
    except Exception as e:  # non-fatal: saving must succeed even if re-filtering hiccups
        logger.warning(f"apply_profile_filters after save failed (non-fatal): {e}")
    saved = db_ops.get_profile_by_id(profile_id)
    return jsonify({"success": True, "profile": saved, "hidden": hidden})


@profile_bp.route("/api/profile/block-company", methods=["POST"])
def block_company():
    """
    Add a company to the active profile's blocklist and immediately hide its jobs.

    Body: {"company": "<name>"}. Creates a default active profile if none exists. De-dupes
    case-insensitively. Returns the updated blocked list and how many jobs were hidden.
    """
    data = request.json or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"success": False, "message": "company is required"}), 400

    profile = db_ops.get_active_profile()
    blocked = list((profile or {}).get("blocked_companies") or [])
    if not any(company.lower() == str(b).strip().lower() for b in blocked):
        blocked.append(company)
    # Blocking and favoriting contradict each other; a blocked company is no longer a favorite.
    favorites = [f for f in ((profile or {}).get("favorite_companies") or [])
                 if str(f).strip().lower() != company.lower()]

    profile_id = db_ops.upsert_active_profile({
        "blocked_companies": blocked, "favorite_companies": favorites,
    })
    hidden = 0
    try:
        hidden = apply_profile_filters().get("blocked", 0)
    except Exception as e:
        logger.warning(f"apply_profile_filters after block-company failed (non-fatal): {e}")
    saved = db_ops.get_profile_by_id(profile_id)
    return jsonify({
        "success": True,
        "blocked_companies": saved.get("blocked_companies", []),
        "favorite_companies": saved.get("favorite_companies", []),
        "hidden": hidden,
    })


@profile_bp.route("/api/profile/favorite-company", methods=["POST"])
def favorite_company():
    """
    Star or un-star a company on the active profile. Purely visual: the UI outlines that
    company's cards; nothing is hidden or un-hidden.

    Body: {"company": "<name>", "favorite": true|false}. Omitting ``favorite`` toggles.
    Matching is case-insensitive on the trimmed name and the first-seen spelling is kept.
    Creates a default active profile if none exists. Returns the updated favorites list.
    """
    data = request.json or {}
    company = (data.get("company") or "").strip()
    if not company:
        return jsonify({"success": False, "message": "company is required"}), 400

    profile = db_ops.get_active_profile()
    favorites = list((profile or {}).get("favorite_companies") or [])
    lc = company.lower()
    present = any(str(f).strip().lower() == lc for f in favorites)
    want = (not present) if data.get("favorite") is None else bool(data.get("favorite"))
    if want and not present:
        favorites.append(company)
    elif not want:
        favorites = [f for f in favorites if str(f).strip().lower() != lc]

    profile_id = db_ops.upsert_active_profile({"favorite_companies": favorites})
    saved = db_ops.get_profile_by_id(profile_id)
    return jsonify({
        "success": True,
        "favorite": want,
        "favorite_companies": saved.get("favorite_companies", []),
    })


@profile_bp.route("/api/profile/add-skill", methods=["POST"])
def add_skill():
    """
    Add a skill to the active profile's skills list.

    Body: {"skill": "<name>"}. Creates a default active profile if none exists. De-dupes
    case-insensitively (mirrors block_company). Lets a user promote a job's "skills you lack"
    tag into their profile with one click; because the skill is now already present, a later
    LLM rebuild unions it in rather than dropping it (see rebuildProfile in index.html).
    """
    data = request.json or {}
    skill = (data.get("skill") or "").strip()
    if not skill:
        return jsonify({"success": False, "message": "skill is required"}), 400

    profile = db_ops.get_active_profile()
    skills = list((profile or {}).get("skills") or [])
    if not any(skill.lower() == str(s).strip().lower() for s in skills):
        skills.append(skill)

    profile_id = db_ops.upsert_active_profile({"skills": skills})
    saved = db_ops.get_profile_by_id(profile_id)
    return jsonify({"success": True, "skills": saved.get("skills", [])})


@profile_bp.route("/api/profile/upload", methods=["POST"])
def upload_resume():
    """
    Extract plain text from an uploaded resume and return it immediately.

    This is intentionally **lightweight** — it only runs the local text extractor
    (pypdf for PDF, light cleanup for tex/md) so the upload returns fast. The LLM
    profile build is a separate, explicit step (`POST /api/profile/build`, triggered
    by the "Build Profile (LLM)" button) so a slow model never blocks the upload.
    Nothing is persisted.
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

    return jsonify({
        "success": True,
        "source_filename": name,
        "resume_text": text,
    })


@profile_bp.route("/api/profile/build", methods=["POST"])
def build_profile():
    """
    (Re)build a draft profile from already-extracted resume text (requires LLM).

    Optional ``instructions`` free-text steers the build (job titles, queries, skills, interests);
    when omitted it falls back to the saved profile's ``llm_instructions``.
    """
    data = request.json or {}
    text = (data.get("resume_text") or "").strip()
    if not text:
        return jsonify({"success": False, "message": "resume_text is required"}), 400
    instructions = data.get("instructions")
    if instructions is None:
        active = db_ops.get_active_profile()
        instructions = (active or {}).get("llm_instructions", "")
    draft, llm_used, llm_error = _build_draft(text, instructions)
    if not llm_used:
        return jsonify({"success": False, "message": llm_error or "LLM is not enabled"}), 400
    return jsonify({"success": True, "profile": draft, "llm_used": True})


def _build_draft(text, instructions=""):
    """Try to build a profile draft via the LLM; fall back to an empty manual draft."""
    config = load_llm_endpoint_config()
    if not config.get("enabled"):
        return dict(EMPTY_PROFILE), False, "LLM endpoint disabled"
    try:
        client = OpenAIClient.from_config(config)
        return build_profile_from_text(text, client, instructions), True, None
    except Exception as e:
        logger.error(f"LLM profile build failed: {e}")
        return dict(EMPTY_PROFILE), False, str(e)
