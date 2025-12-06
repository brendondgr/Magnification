from flask import Blueprint, request, jsonify
from ..database import operations as db_ops
from loguru import logger

job_bp = Blueprint('job_bp', __name__)

@job_bp.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Get all active jobs with their application statuses."""
    try:
        # Get all active jobs (ignore=0)
        jobs = db_ops.get_all_jobs(include_ignored=False)
        
        # Hydrate with statuses
        full_jobs = []
        for job in jobs:
            statuses = db_ops.get_application_status_by_job(job['id'])
            job['statuses'] = statuses
            full_jobs.append(job)
            
        return jsonify(full_jobs)
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        return jsonify({'error': str(e)}), 500

@job_bp.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Get a single job with details."""
    try:
        job = db_ops.get_job_by_id(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
            
        statuses = db_ops.get_application_status_by_job(job_id)
        job['statuses'] = statuses
        
        return jsonify(job)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@job_bp.route('/api/jobs/<int:job_id>/ignore', methods=['PATCH'])
def ignore_job(job_id):
    """Mark a job as ignored."""
    try:
        data = request.json or {}
        ignore_value = data.get('ignore', 1)
        
        success = db_ops.set_job_ignore(job_id, ignore_value)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Job not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@job_bp.route('/api/jobs/<int:job_id>/status', methods=['PATCH'])
def update_status(job_id):
    """Update application status."""
    try:
        data = request.json
        status_name = data.get('status')
        checked = data.get('checked', 1)
        date_reached = data.get('date_reached') # Optional
        
        if not status_name:
             return jsonify({'error': 'Status name required'}), 400
             
        success = db_ops.update_application_status(
            job_id, status_name, checked, date_reached
        )
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Update failed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
