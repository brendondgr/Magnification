"""
CRUD operations for the Agentic Document System's per-job tables: ``job_evaluations`` (the
application-fit read the cover-letter graph writes) and ``generated_documents`` (the produced
cover letters / résumés).

Kept separate from ``operations.py`` so that file stays under the repo's 800-line cap. Mirrors the
conventions there: every function wraps queries in ``get_db_context()`` (auto-commit/rollback/close)
and each model has a ``_*_to_dict`` serializer that ``.isoformat()``s datetimes and provides safe
defaults for JSON columns.

The Behavioral / Writing-Style / Document-Template / Uploaded-Document tables (and the ingestion
pipeline that fed them) were retired in favor of a single editable Document Guidance document; see
``utils/backend/agents/document_guidance.py``.
"""

from typing import Any, Dict, List, Optional

from .init_db import get_db_context
from .models import JobEvaluation, GeneratedDocument

# ---- caller-settable field whitelists (mirrors _PROFILE_FIELDS in operations.py) ----

_EVALUATION_FIELDS = ('verdict', 'fit_score', 'emphasize', 'gaps', 'risks', 'talking_points')
_GENERATED_FIELDS = (
    'kind', 'content', 'format', 'status', 'match_before', 'match_after',
    'revision', 'checkpoint_state',
)


# ==================== Job Evaluations (1:1 by job_id, upsert) ====================

def save_job_evaluation(job_id: int, data: Dict[str, Any],
                        profile_id: Optional[int] = None) -> int:
    """Upsert the application-fit evaluation row for a job (1:1 by job_id)."""
    with get_db_context() as db:
        row = db.query(JobEvaluation).filter(JobEvaluation.job_id == job_id).first()
        if not row:
            row = JobEvaluation(job_id=job_id)
            db.add(row)
        if profile_id is not None:
            row.profile_id = profile_id
        for key in _EVALUATION_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.flush()
        eval_id = row.id
    return eval_id


def get_job_evaluation(job_id: int) -> Optional[Dict[str, Any]]:
    """Return the evaluation for a job, or None."""
    with get_db_context() as db:
        row = db.query(JobEvaluation).filter(JobEvaluation.job_id == job_id).first()
        return _job_evaluation_to_dict(row) if row else None


# ==================== Generated Documents (multi-row per job) ====================

def create_generated_document(data: Dict[str, Any]) -> int:
    """Create a generated document. ``data`` must include ``job_id``."""
    with get_db_context() as db:
        row = GeneratedDocument(job_id=data['job_id'])
        for key in _GENERATED_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.add(row)
        db.flush()
        new_id = row.id
    return new_id


def update_generated_document(doc_id: int, updates: Dict[str, Any]) -> bool:
    """Update a generated document's fields. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(GeneratedDocument).filter(GeneratedDocument.id == doc_id).first()
        if not row:
            return False
        for key in _GENERATED_FIELDS:
            if key in updates:
                setattr(row, key, updates[key])
    return True


def delete_generated_document(doc_id: int) -> bool:
    """Delete a generated document. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(GeneratedDocument).filter(GeneratedDocument.id == doc_id).first()
        if not row:
            return False
        db.delete(row)
    return True


def get_generated_document(doc_id: int) -> Optional[Dict[str, Any]]:
    """Return a single generated document by id, or None."""
    with get_db_context() as db:
        row = db.query(GeneratedDocument).filter(GeneratedDocument.id == doc_id).first()
        return _generated_to_dict(row) if row else None


def list_generated_documents(job_id: int, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """List generated documents for a job (newest first), optionally filtered by kind."""
    with get_db_context() as db:
        query = db.query(GeneratedDocument).filter(GeneratedDocument.job_id == job_id)
        if kind:
            query = query.filter(GeneratedDocument.kind == kind)
        rows = query.order_by(GeneratedDocument.created_at.desc()).all()
        return [_generated_to_dict(r) for r in rows]


# ==================== Serializers ====================

def _job_evaluation_to_dict(row: JobEvaluation) -> Dict[str, Any]:
    return {
        'id': row.id,
        'job_id': row.job_id,
        'profile_id': row.profile_id,
        'verdict': row.verdict or '',
        'fit_score': row.fit_score,
        'emphasize': row.emphasize or [],
        'gaps': row.gaps or [],
        'risks': row.risks or '',
        'talking_points': row.talking_points or [],
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _generated_to_dict(row: GeneratedDocument) -> Dict[str, Any]:
    return {
        'id': row.id,
        'job_id': row.job_id,
        'kind': row.kind,
        'content': row.content or '',
        'format': row.format or 'markdown',
        'status': row.status or 'draft',
        'match_before': row.match_before,
        'match_after': row.match_after,
        'revision': row.revision,
        'checkpoint_state': row.checkpoint_state if row.checkpoint_state is not None else {},
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }
