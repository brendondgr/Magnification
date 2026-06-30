"""
Options API: configure the OpenAI-compatible LLM endpoint and the runtime knobs
(parallelism + analysis toggles + score weights). Backs the Options panel's two tabs.
"""

from flask import Blueprint, request, jsonify
from loguru import logger

from utils.backend.llm.config import (
    load_llm_endpoint_config,
    save_llm_endpoint_config,
)
from utils.backend.llm.client import OpenAIClient, LLMConfigError
from utils.backend.recommend.runtime_config import (
    get_runtime_config,
    save_runtime_config,
)

options_bp = Blueprint("options_bp", __name__)


# ---- LLM endpoint config (tab 1) -------------------------------------

@options_bp.route("/api/options/llm", methods=["GET"])
def get_llm_options():
    return jsonify(load_llm_endpoint_config())


@options_bp.route("/api/options/llm", methods=["POST"])
def save_llm_options():
    data = request.json or {}
    if save_llm_endpoint_config(data):
        return jsonify({"success": True, "config": load_llm_endpoint_config()})
    return jsonify({"success": False, "message": "Failed to save LLM config"}), 500


@options_bp.route("/api/options/llm/test", methods=["POST"])
def test_llm_options():
    """
    Test connectivity. Uses the posted config if provided (so the user can test
    before saving), otherwise the saved config. Ignores the enabled flag for tests.
    """
    data = request.json or {}
    config = load_llm_endpoint_config()
    config.update({k: v for k, v in data.items() if k in config})
    try:
        client = OpenAIClient.from_config(config, require_enabled=False)
    except LLMConfigError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    result = client.test_connection()
    status = 200 if result.get("ok") else 502
    return jsonify(result), status


# ---- Runtime knobs (tab 2) -------------------------------------------

@options_bp.route("/api/options/runtime", methods=["GET"])
def get_runtime_options():
    return jsonify(get_runtime_config())


@options_bp.route("/api/options/runtime", methods=["POST"])
def save_runtime_options():
    data = request.json or {}
    if save_runtime_config(data):
        return jsonify({"success": True, "config": get_runtime_config()})
    return jsonify({"success": False, "message": "Failed to save runtime config"}), 500
