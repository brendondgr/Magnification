"""
CRUD operations for the Agentic Document System's supporting-document and
generation tables (see docs/plans/agentic-documents-system.md §1.2).

Kept separate from ``operations.py`` so that file stays under the repo's 800-line
cap. Mirrors the conventions there exactly: every function wraps queries in
``get_db_context()`` (auto-commit/rollback/close), the two "profile-like" tables
enforce a single ``is_active`` row via a ``_deactivate_*`` helper called inside the
session, and each model has a ``_*_to_dict`` serializer that ``.isoformat()``s
datetimes and provides safe defaults for JSON columns.
"""

from typing import Any, Dict, List, Optional

from .init_db import get_db_context
from .models import (
    UploadedDocument,
    BehavioralProfile,
    WritingStyleProfile,
    DocumentTemplate,
    JobEvaluation,
    GeneratedDocument,
)

# ---- caller-settable field whitelists (mirrors _PROFILE_FIELDS in operations.py) ----

_BEHAVIORAL_FIELDS = (
    'name', 'is_active', 'traits', 'strengths', 'work_style_paragraph', 'source_filename',
)
_WRITING_FIELDS = (
    'name', 'is_active', 'tone', 'formality', 'sentence_length', 'sample_text',
    'dos', 'donts', 'source_filename',
)
_TEMPLATE_FIELDS = ('kind', 'name', 'body', 'format', 'is_default')
_EVALUATION_FIELDS = ('verdict', 'fit_score', 'emphasize', 'gaps', 'risks', 'talking_points')
_GENERATED_FIELDS = (
    'kind', 'content', 'format', 'status', 'match_before', 'match_after',
    'revision', 'checkpoint_state',
)
_UPLOADED_FIELDS = (
    'filename', 'doc_type', 'raw_text', 'summary', 'derived_table', 'derived_id', 'status',
)


# ==================== Behavioral Profile (single active row) ====================

def create_behavioral_profile(data: Dict[str, Any]) -> int:
    """Create a behavioral profile; enforce the single-active invariant if active."""
    with get_db_context() as db:
        row = BehavioralProfile()
        for key in _BEHAVIORAL_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.add(row)
        db.flush()
        new_id = row.id
        if row.is_active:
            _deactivate_other(db, BehavioralProfile, new_id)
    return new_id


def update_behavioral_profile(profile_id: int, updates: Dict[str, Any]) -> bool:
    """Update a behavioral profile's fields. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(BehavioralProfile).filter(BehavioralProfile.id == profile_id).first()
        if not row:
            return False
        for key in _BEHAVIORAL_FIELDS:
            if key in updates:
                setattr(row, key, updates[key])
        if updates.get('is_active'):
            _deactivate_other(db, BehavioralProfile, profile_id)
    return True


def get_active_behavioral_profile() -> Optional[Dict[str, Any]]:
    """Return the active behavioral profile, or None."""
    with get_db_context() as db:
        row = db.query(BehavioralProfile).filter(BehavioralProfile.is_active == 1).order_by(
            BehavioralProfile.updated_at.desc()
        ).first()
        return _behavioral_to_dict(row) if row else None


def upsert_active_behavioral_profile(data: Dict[str, Any]) -> int:
    """Update the active behavioral profile if present, else create a new active one."""
    active = get_active_behavioral_profile()
    if active:
        update_behavioral_profile(active['id'], data)
        return active['id']
    payload = dict(data)
    payload.setdefault('name', 'default')
    payload['is_active'] = 1
    return create_behavioral_profile(payload)


# ==================== Writing Style Profile (single active row) ====================

def create_writing_style(data: Dict[str, Any]) -> int:
    """Create a writing-style profile; enforce the single-active invariant if active."""
    with get_db_context() as db:
        row = WritingStyleProfile()
        for key in _WRITING_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.add(row)
        db.flush()
        new_id = row.id
        if row.is_active:
            _deactivate_other(db, WritingStyleProfile, new_id)
    return new_id


def update_writing_style(profile_id: int, updates: Dict[str, Any]) -> bool:
    """Update a writing-style profile's fields. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(WritingStyleProfile).filter(WritingStyleProfile.id == profile_id).first()
        if not row:
            return False
        for key in _WRITING_FIELDS:
            if key in updates:
                setattr(row, key, updates[key])
        if updates.get('is_active'):
            _deactivate_other(db, WritingStyleProfile, profile_id)
    return True


def get_active_writing_style() -> Optional[Dict[str, Any]]:
    """Return the active writing-style profile, or None."""
    with get_db_context() as db:
        row = db.query(WritingStyleProfile).filter(WritingStyleProfile.is_active == 1).order_by(
            WritingStyleProfile.updated_at.desc()
        ).first()
        return _writing_style_to_dict(row) if row else None


def upsert_active_writing_style(data: Dict[str, Any]) -> int:
    """Update the active writing-style profile if present, else create a new active one."""
    active = get_active_writing_style()
    if active:
        update_writing_style(active['id'], data)
        return active['id']
    payload = dict(data)
    payload.setdefault('name', 'default')
    payload['is_active'] = 1
    return create_writing_style(payload)


# ==================== Document Templates (multi-row, default per kind) ====================

def create_template(data: Dict[str, Any]) -> int:
    """Create a template. If marked default, clear other defaults of the same kind."""
    with get_db_context() as db:
        row = DocumentTemplate()
        for key in _TEMPLATE_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.add(row)
        db.flush()
        new_id = row.id
        if row.is_default:
            _clear_other_defaults(db, row.kind, new_id)
    return new_id


def update_template(template_id: int, updates: Dict[str, Any]) -> bool:
    """Update a template's fields. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(DocumentTemplate).filter(DocumentTemplate.id == template_id).first()
        if not row:
            return False
        for key in _TEMPLATE_FIELDS:
            if key in updates:
                setattr(row, key, updates[key])
        if updates.get('is_default'):
            _clear_other_defaults(db, row.kind, template_id)
    return True


def delete_template(template_id: int) -> bool:
    """Delete a template. Returns True if it existed."""
    with get_db_context() as db:
        row = db.query(DocumentTemplate).filter(DocumentTemplate.id == template_id).first()
        if not row:
            return False
        db.delete(row)
    return True


def get_template(template_id: int) -> Optional[Dict[str, Any]]:
    """Return a single template by id, or None."""
    with get_db_context() as db:
        row = db.query(DocumentTemplate).filter(DocumentTemplate.id == template_id).first()
        return _template_to_dict(row) if row else None


def list_templates(kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """List templates, optionally filtered by kind (defaults first, then newest)."""
    with get_db_context() as db:
        query = db.query(DocumentTemplate)
        if kind:
            query = query.filter(DocumentTemplate.kind == kind)
        rows = query.order_by(
            DocumentTemplate.is_default.desc(), DocumentTemplate.created_at.desc()
        ).all()
        return [_template_to_dict(r) for r in rows]


def get_default_template(kind: str) -> Optional[Dict[str, Any]]:
    """Return the default template for a kind (falls back to the newest of that kind)."""
    with get_db_context() as db:
        row = db.query(DocumentTemplate).filter(
            DocumentTemplate.kind == kind, DocumentTemplate.is_default == 1
        ).first()
        if not row:
            row = db.query(DocumentTemplate).filter(
                DocumentTemplate.kind == kind
            ).order_by(DocumentTemplate.created_at.desc()).first()
        return _template_to_dict(row) if row else None


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


# ==================== Uploaded Documents (raw-upload log) ====================

def create_uploaded_document(data: Dict[str, Any]) -> int:
    """Insert a raw-upload record."""
    with get_db_context() as db:
        row = UploadedDocument()
        for key in _UPLOADED_FIELDS:
            if key in data:
                setattr(row, key, data[key])
        db.add(row)
        db.flush()
        new_id = row.id
    return new_id


def update_uploaded_document(doc_id: int, updates: Dict[str, Any]) -> bool:
    """Update a raw-upload record (e.g. link derived_table/derived_id after Save)."""
    with get_db_context() as db:
        row = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
        if not row:
            return False
        for key in _UPLOADED_FIELDS:
            if key in updates:
                setattr(row, key, updates[key])
    return True


def get_uploaded_document(doc_id: int) -> Optional[Dict[str, Any]]:
    """Return a single raw-upload record by id, or None."""
    with get_db_context() as db:
        row = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
        return _uploaded_to_dict(row) if row else None


def list_uploaded_documents(limit: int = 100) -> List[Dict[str, Any]]:
    """List raw-upload records, newest first."""
    with get_db_context() as db:
        rows = db.query(UploadedDocument).order_by(
            UploadedDocument.uploaded_at.desc()
        ).limit(limit).all()
        return [_uploaded_to_dict(r) for r in rows]


# ==================== Internal helpers ====================

def _deactivate_other(db, model, keep_id: int) -> None:
    """Set is_active=0 on every row of ``model`` except keep_id (call inside a session)."""
    db.query(model).filter(model.id != keep_id).update(
        {model.is_active: 0}, synchronize_session=False
    )


def _clear_other_defaults(db, kind: str, keep_id: int) -> None:
    """Clear is_default on every other template of the same kind (call inside a session)."""
    db.query(DocumentTemplate).filter(
        DocumentTemplate.kind == kind, DocumentTemplate.id != keep_id
    ).update({DocumentTemplate.is_default: 0}, synchronize_session=False)


# ==================== Serializers ====================

def _behavioral_to_dict(row: BehavioralProfile) -> Dict[str, Any]:
    return {
        'id': row.id,
        'name': row.name,
        'is_active': row.is_active,
        'traits': row.traits if row.traits is not None else {},
        'strengths': row.strengths or [],
        'work_style_paragraph': row.work_style_paragraph or '',
        'source_filename': row.source_filename,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _writing_style_to_dict(row: WritingStyleProfile) -> Dict[str, Any]:
    return {
        'id': row.id,
        'name': row.name,
        'is_active': row.is_active,
        'tone': row.tone or '',
        'formality': row.formality or '',
        'sentence_length': row.sentence_length or '',
        'sample_text': row.sample_text or '',
        'dos': row.dos or [],
        'donts': row.donts or [],
        'source_filename': row.source_filename,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _template_to_dict(row: DocumentTemplate) -> Dict[str, Any]:
    return {
        'id': row.id,
        'kind': row.kind,
        'name': row.name,
        'body': row.body or '',
        'format': row.format or 'markdown',
        'is_default': row.is_default,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


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


def _uploaded_to_dict(row: UploadedDocument) -> Dict[str, Any]:
    return {
        'id': row.id,
        'filename': row.filename,
        'doc_type': row.doc_type,
        'raw_text': row.raw_text or '',
        'summary': row.summary or '',
        'derived_table': row.derived_table,
        'derived_id': row.derived_id,
        'status': row.status or 'draft',
        'uploaded_at': row.uploaded_at.isoformat() if row.uploaded_at else None,
    }
