"""
Recommendation API: run the RAG analysis over jobs and read back the ranked report.
(LLM keyword generation is added in a later phase.)
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.recommend import service, keywords
from utils.backend.llm.config import load_llm_endpoint_config
from utils.backend.llm.client import OpenAIClient, LLMConfigError

recommend_bp = Blueprint("recommend_bp", __name__)


@recommend_bp.route("/api/recommend/analyze", methods=["POST"])
def analyze():
    """
    Embed + score jobs against the active profile.

    Body (all optional): ``{job_ids:[...], reanalyze_all: bool}``. By default the LLM fit
    verdict only fills jobs that don't have one yet (gap-fill); pass ``reanalyze_all: true``
    to force a fresh verdict on every job.
    """
    if db_ops.get_active_profile() is None:
        return jsonify({"success": False, "message": "Create a profile first."}), 400
    data = request.json or {}
    job_ids = data.get("job_ids")
    reanalyze_all = bool(data.get("reanalyze_all"))
    try:
        result = service.analyze_jobs(job_ids=job_ids, llm_only_missing=not reanalyze_all)
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Recommendation analysis failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@recommend_bp.route("/api/recommend/rescore", methods=["POST"])
def rescore():
    """
    Cheaply recompute match scores from **stored** analysis artifacts (embeddings, extracted
    skills, preserved LLM verdicts) against the current profile + score weights — no job
    re-embedding, no LLM calls. Used to refresh the displayed match percentages after a
    score-weight or profile/skill change without paying the full "Analyze Matches" cost.

    No body required. Returns ``{success, rescored, profile_id, top}``.
    """
    if db_ops.get_active_profile() is None:
        return jsonify({"success": False, "message": "Create a profile first."}), 400
    try:
        result = service.rescore_jobs()
        status = 200 if result.get("success") else 400
        return jsonify(result), status
    except Exception as e:
        logger.error(f"Recommendation rescore failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@recommend_bp.route("/api/recommend/keywords", methods=["POST"])
def gen_keywords():
    """
    LLM-generate search terms + AND/OR keyword groups + a job type. Body: optional
    {seed:str}; falls back to the active profile when no seed is given.
    """
    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return jsonify({"success": False, "message": "Enable the LLM endpoint in Options first."}), 400
    data = request.json or {}
    seed = (data.get("seed") or "").strip() or keywords.seed_from_profile(db_ops.get_active_profile())
    if not seed:
        return jsonify({"success": False, "message": "Provide a seed or create a profile first."}), 400
    try:
        client = OpenAIClient.from_config(cfg)
        result = keywords.generate_keywords(seed, client)
        return jsonify({"success": True, **result})
    except LLMConfigError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Keyword generation failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 502


@recommend_bp.route("/api/recommend/report", methods=["GET"])
def report():
    """Ranked jobs (highest rag_score first) that have an analysis."""
    try:
        limit = int(request.args.get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    include_ignored = request.args.get("include_ignored") in ("1", "true", "yes")
    try:
        jobs = service.build_report(limit=limit, include_ignored=include_ignored)
        return jsonify({"success": True, "count": len(jobs), "jobs": jobs})
    except Exception as e:
        logger.error(f"Recommendation report failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
