from flask import Blueprint, request, jsonify
import threading
import uuid
import time
from typing import Dict, Any

from ..scrapers.scraping_service import execute_full_scraping_workflow

scrape_bp = Blueprint('scrape_bp', __name__)

# In-memory storage for job status
# Format: { job_id: { status: str, progress: dict, results: dict, error: str } }
scrape_jobs: Dict[str, Any] = {}

def cleanup_old_jobs():
    """Remove jobs older than 1 hour"""
    current_time = time.time()
    for job_id in list(scrape_jobs.keys()):
        job = scrape_jobs[job_id]
        if job.get('end_time') and (current_time - job['end_time'] > 3600):
            del scrape_jobs[job_id]

def run_scraping_background(job_id: str, use_config: bool = True):
    """Background task to run the scraping workflow"""
    try:
        scrape_jobs[job_id]['status'] = 'running'
        
        def progress_callback(status_update):
            rec = scrape_jobs[job_id]
            rec['progress'] = status_update
            # Append a timestamped entry to an append-only event log so the UI can show a
            # live, step-by-step activity feed. Consecutive identical messages are skipped,
            # and the log is capped to bound memory.
            details = status_update.get('details') or {}
            msg = details.get('message') or ''
            events = rec.setdefault('events', [])
            if msg and (not events or events[-1].get('message') != msg):
                events.append({
                    't': round(time.time() - rec.get('start_time', time.time()), 1),
                    'stage': status_update.get('stage'),
                    'percent': status_update.get('percent'),
                    'message': msg,
                })
                if len(events) > 200:
                    del events[:len(events) - 200]
            # If completed or failed, status is handled by return value usually,
            # but callback might be faster for real-time UI
            if status_update.get('stage') == 'failed':
                rec['status'] = 'failed'
                rec['error'] = details.get('message', 'Unknown error')
        
        # Execute workflow
        # Note: If use_config is True, we pass None for params so it loads from config
        results = execute_full_scraping_workflow(
            search_terms=None if use_config else [], # Logic handles None by loading config
            progress_callback=progress_callback
        )
        
        scrape_jobs[job_id]['results'] = results
        if results.get('success'):
            scrape_jobs[job_id]['status'] = 'completed'
        else:
            scrape_jobs[job_id]['status'] = 'failed'
            scrape_jobs[job_id]['error'] = '; '.join(results.get('errors', []))
            
    except Exception as e:
        scrape_jobs[job_id]['status'] = 'failed'
        scrape_jobs[job_id]['error'] = str(e)
    finally:
        scrape_jobs[job_id]['end_time'] = time.time()

@scrape_bp.route('/api/scrape/start', methods=['POST'])
def start_scraping():
    cleanup_old_jobs()
    
    data = request.json or {}
    use_config = data.get('use_config', True)
    
    job_id = f"scrape_{uuid.uuid4().hex[:8]}"
    
    scrape_jobs[job_id] = {
        'status': 'pending',
        'progress': {'stage': 'pending', 'percent': 0, 'details': {}},
        'events': [],
        'results': None,
        'start_time': time.time()
    }
    
    # Start thread
    thread = threading.Thread(target=run_scraping_background, args=(job_id, use_config))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True, 
        'job_id': job_id,
        'message': 'Scraping started'
    })

@scrape_bp.route('/api/scrape/status/<job_id>', methods=['GET'])
def get_status(job_id):
    job = scrape_jobs.get(job_id)
    if not job:
        return jsonify({'success': False, 'message': 'Job not found'}), 404
    
    return jsonify(job)
