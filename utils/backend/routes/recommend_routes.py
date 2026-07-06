"""
Recommendation API: run the RAG analysis over jobs and read back the ranked report.
(LLM keyword generation is added in a later phase.)
"""

import threading
import time
import uuid
from typing import Any, Dict

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.recommend import service, keywords
from utils.backend.llm.config import load_llm_endpoint_config
from utils.backend.llm.client import OpenAIClient, LLMConfigError

recommend_bp = Blueprint("recommend_bp", __name__)

# In-memory store for background analyze tasks, mirroring scrape_routes.scrape_jobs.
# Format: { job_id: {status, progress, events:[...], results, start_time, end_time, error} }
analyze_tasks: Dict[str, Any] = {}


def _cleanup_old_analyze_tasks() -> None:
    """Drop finished analyze tasks older than an hour to bound memory."""
    now = time.time()
    for jid in list(analyze_tasks.keys()):
        rec = analyze_tasks[jid]
        if rec.get("end_time") and (now - rec["end_time"] > 3600):
            del analyze_tasks[jid]


def _run_analyze_background(job_id: str, job_ids, reanalyze_all: bool) -> None:
    """Run analyze_jobs in a thread, streaming staged progress into analyze_tasks[job_id]."""
    rec = analyze_tasks[job_id]
    rec["status"] = "running"

    def progress_callback(update: Dict[str, Any]) -> None:
        rec["progress"] = update
        details = update.get("details") or {}
        msg = details.get("message") or ""
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

    try:
        result = service.analyze_jobs(
            job_ids=job_ids, llm_only_missing=not reanalyze_all,
            progress_callback=progress_callback)
        rec["results"] = result
        if result.get("success"):
            rec["status"] = "completed"
        else:
            rec["status"] = "failed"
            rec["error"] = result.get("message", "Analysis failed")
    except Exception as e:
        logger.error(f"Background analysis failed: {e}")
        rec["status"] = "failed"
        rec["error"] = str(e)
    finally:
        rec["end_time"] = time.time()


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


@recommend_bp.route("/api/recommend/analyze/start", methods=["POST"])
def analyze_start():
    """
    Start a background analysis and return a ``job_id`` to poll. Body (all optional):
    ``{job_ids:[...], reanalyze_all: bool}`` (same semantics as ``/api/recommend/analyze``).
    Progress is read back from ``/api/recommend/analyze/status/<job_id>``.
    """
    if db_ops.get_active_profile() is None:
        return jsonify({"success": False, "message": "Create a profile first."}), 400
    _cleanup_old_analyze_tasks()
    data = request.json or {}
    job_ids = data.get("job_ids")
    reanalyze_all = bool(data.get("reanalyze_all"))
    job_id = f"analyze_{uuid.uuid4().hex[:8]}"
    analyze_tasks[job_id] = {
        "status": "pending",
        "progress": {"stage": "pending", "percent": 0, "details": {}},
        "events": [],
        "results": None,
        "start_time": time.time(),
    }
    thread = threading.Thread(
        target=_run_analyze_background, args=(job_id, job_ids, reanalyze_all), daemon=True)
    thread.start()
    return jsonify({"success": True, "job_id": job_id, "message": "Analysis started"})


@recommend_bp.route("/api/recommend/analyze/status/<job_id>", methods=["GET"])
def analyze_status(job_id):
    """Return the full task record (status, progress, events, results) for a poll."""
    rec = analyze_tasks.get(job_id)
    if not rec:
        return jsonify({"success": False, "message": "Task not found"}), 404
    return jsonify(rec)


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
