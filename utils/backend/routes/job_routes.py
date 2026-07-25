from flask import Blueprint, request, jsonify
from ..database import operations as db_ops
from ..database.init_db import reset_database
from loguru import logger

job_bp = Blueprint('job_bp', __name__)

_TRUTHY = ('1', 'true', 'yes')


@job_bp.route('/api/jobs', methods=['GET'])
def get_jobs():
    """Get the jobs the feed renders, with their application statuses.

    By default ignored jobs are withheld (unless they are saved or applied to, which
    the Saved lane and Tracker still need) — on a database with a large blocklist that
    is nearly the whole table. Pass ?include_ignored=1 to get everything; the front-end
    does that lazily, the first time "Show Ignored" is switched on.

    Pass ?with_analysis=1 to attach each job's recommendation analysis (match scores,
    skill match, keyword hits) under a `analysis` key.
    """
    try:
        include_ignored = request.args.get('include_ignored') in _TRUTHY
        jobs = db_ops.get_feed_jobs(include_ignored=include_ignored)

        job_ids = [j['id'] for j in jobs]
        with_analysis = request.args.get('with_analysis') in _TRUTHY
        analyses = db_ops.get_analysis_for_jobs(job_ids) if with_analysis else {}
        statuses = db_ops.get_statuses_for_jobs(job_ids)

        # Hydrate with statuses (+ analysis when requested)
        for job in jobs:
            job['statuses'] = statuses.get(job['id'], [])
            if with_analysis:
                job['analysis'] = analyses.get(job['id'])

        return jsonify(jobs)
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        return jsonify({'error': str(e)}), 500


@job_bp.route('/api/jobs/counts', methods=['GET'])
def get_job_counts():
    """Row counts for the jobs table: {total, feed, hidden}.

    `hidden` is how many ignored jobs the default /api/jobs payload leaves out — the
    front-end uses it to label the "Show Ignored" button without loading those rows.
    """
    try:
        return jsonify(db_ops.get_job_counts())
    except Exception as e:
        logger.error(f"Error counting jobs: {e}")
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

@job_bp.route('/api/jobs/<int:job_id>/save', methods=['PATCH'])
def save_job(job_id):
    """Toggle the saved flag on a job (pins it to the Saved lane)."""
    try:
        data = request.json or {}
        saved_value = data.get('saved', 1)

        success = db_ops.set_job_saved(job_id, saved_value)
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

@job_bp.route('/api/database/clear', methods=['POST'])
def clear_database():
    """
    Clear the database at the requested scope.

    Body: {"scope": "full" | "jobs"} (defaults to "full" for backward compat).
      - "full": drop and recreate every table (jobs + profiles + everything).
      - "jobs": delete jobs, application statuses, and analyses; keep profiles.
    """
    data = request.json or {}
    scope = (data.get('scope') or 'full').lower()
    try:
        if scope == 'full':
            reset_database()
        elif scope == 'jobs':
            db_ops.clear_jobs_database()
        else:
            return jsonify({'error': f'Unknown scope: {scope}'}), 400
        return jsonify({'success': True, 'scope': scope})
    except Exception as e:
        logger.error(f"Error clearing database (scope={scope}): {e}")
        return jsonify({'error': str(e)}), 500
