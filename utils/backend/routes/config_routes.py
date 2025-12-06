from flask import Blueprint, request, jsonify
import json
import os
from loguru import logger

config_bp = Blueprint('config_bp', __name__)

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../config/jobs_config.json'))

def load_jobs_config():
    if not os.path.exists(CONFIG_PATH):
        # Return default if file doesn't exist (though it should)
        return {
            "search_terms": [],
            "job_titles": [],
            "description_keywords": [],
            "sites": ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"],
            "hours_old": 24,
            "results_wanted": 20
        }
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return {}

def save_jobs_config(data):
    try:
        # Validate data (basic validation)
        if not isinstance(data.get('search_terms'), list):
            raise ValueError("search_terms must be a list")
        if not isinstance(data.get('sites'), list):
            raise ValueError("sites must be a list")
            
        with open(CONFIG_PATH, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False

@config_bp.route('/api/config/load', methods=['GET'])
def get_config():
    config = load_jobs_config()
    return jsonify(config)

@config_bp.route('/api/config/save', methods=['POST'])
def save_config():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    
    if save_jobs_config(data):
        return jsonify({"success": True, "message": "Configuration saved successfully"})
    else:
        return jsonify({"success": False, "message": "Failed to save configuration"}), 500
