"""
Round-trip + invariant tests for the Agentic Document System's data layer.

Runs against an isolated in-memory SQLite engine (never the real dev DB) by patching
the module-level ``SessionLocal`` that ``get_db_context`` resolves at call time, exactly
like tests/database/test_clear_jobs.py.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.database.seed_documents import seed_documents_if_empty
from utils.backend.database.models import (
    Base, Job, JobEvaluation, GeneratedDocument, BehavioralProfile,
    WritingStyleProfile, DocumentTemplate,
)


@pytest.fixture()
def temp_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)
    yield engine
    engine.dispose()


# ---- behavioral profile: single-active + upsert -------------------------------

def test_behavioral_single_active_and_upsert(temp_db):
    assert docs_ops.get_active_behavioral_profile() is None

    # Upsert with no active row -> creates an active "default".
    bid = docs_ops.upsert_active_behavioral_profile(
        {"strengths": ["clear writing"], "traits": {"influence": "high"}}
    )
    active = docs_ops.get_active_behavioral_profile()
    assert active["id"] == bid
    assert active["is_active"] == 1
    assert active["strengths"] == ["clear writing"]
    assert active["traits"] == {"influence": "high"}

    # A second explicitly-active row deactivates the first.
    other = docs_ops.create_behavioral_profile({"name": "alt", "is_active": 1})
    with init_db.SessionLocal() as db:
        actives = db.query(BehavioralProfile).filter(BehavioralProfile.is_active == 1).count()
    assert actives == 1
    assert docs_ops.get_active_behavioral_profile()["id"] == other

    # Upsert now updates the (new) active row rather than creating another.
    same = docs_ops.upsert_active_behavioral_profile({"work_style_paragraph": "ships increments"})
    assert same == other
    assert docs_ops.get_active_behavioral_profile()["work_style_paragraph"] == "ships increments"


# ---- writing style: single-active + upsert ------------------------------------

def test_writing_style_single_active_and_upsert(temp_db):
    assert docs_ops.get_active_writing_style() is None
    wid = docs_ops.upsert_active_writing_style(
        {"tone": "warm", "dos": ["hook first"], "donts": ["generic openers"]}
    )
    active = docs_ops.get_active_writing_style()
    assert active["id"] == wid
    assert active["tone"] == "warm"
    assert active["dos"] == ["hook first"]

    docs_ops.create_writing_style({"name": "formal", "is_active": 1})
    with init_db.SessionLocal() as db:
        actives = db.query(WritingStyleProfile).filter(WritingStyleProfile.is_active == 1).count()
    assert actives == 1


# ---- templates: default-per-kind + filtering ----------------------------------

def test_templates_default_per_kind(temp_db):
    a = docs_ops.create_template({"kind": "cover_letter", "name": "Classic", "body": "{{hook}}", "is_default": 1})
    b = docs_ops.create_template({"kind": "cover_letter", "name": "Narrative", "body": "x", "is_default": 0})
    r = docs_ops.create_template({"kind": "resume", "name": "Skeleton", "body": "y", "is_default": 1})

    # Default for cover_letter is the first; a resume default is independent.
    assert docs_ops.get_default_template("cover_letter")["id"] == a
    assert docs_ops.get_default_template("resume")["id"] == r

    # Promoting the second cover-letter template clears the first's default.
    docs_ops.update_template(b, {"is_default": 1})
    assert docs_ops.get_default_template("cover_letter")["id"] == b
    with init_db.SessionLocal() as db:
        cover_defaults = db.query(DocumentTemplate).filter(
            DocumentTemplate.kind == "cover_letter", DocumentTemplate.is_default == 1
        ).count()
    assert cover_defaults == 1

    # Listing by kind + delete.
    assert len(docs_ops.list_templates("cover_letter")) == 2
    assert len(docs_ops.list_templates()) == 3
    assert docs_ops.delete_template(r) is True
    assert docs_ops.get_default_template("resume") is None


# ---- job evaluation: upsert by job_id -----------------------------------------

def test_job_evaluation_upsert(temp_db):
    job_id = db_ops.add_job({"title": "SWE", "company": "Acme", "location": "Remote"}, create_statuses=False)

    e1 = docs_ops.save_job_evaluation(job_id, {"verdict": "strong fit", "fit_score": 80.0,
                                               "emphasize": ["python"]}, profile_id=None)
    got = docs_ops.get_job_evaluation(job_id)
    assert got["id"] == e1
    assert got["fit_score"] == 80.0
    assert got["emphasize"] == ["python"]

    # Second save for the same job updates the same row (1:1).
    e2 = docs_ops.save_job_evaluation(job_id, {"fit_score": 90.0, "gaps": ["kubernetes"]})
    assert e2 == e1
    got = docs_ops.get_job_evaluation(job_id)
    assert got["fit_score"] == 90.0
    assert got["gaps"] == ["kubernetes"]
    assert got["emphasize"] == ["python"]  # untouched fields persist
    with init_db.SessionLocal() as db:
        assert db.query(JobEvaluation).count() == 1


# ---- generated documents: multi-row per job + cascade -------------------------

def test_generated_documents_and_cascade(temp_db):
    job_id = db_ops.add_job({"title": "SWE", "company": "Acme", "location": "Remote"}, create_statuses=False)
    d1 = docs_ops.create_generated_document({"job_id": job_id, "kind": "cover_letter", "content": "v1"})
    d2 = docs_ops.create_generated_document({"job_id": job_id, "kind": "resume", "content": "r1",
                                             "match_before": 0.6, "match_after": 0.8})
    assert len(docs_ops.list_generated_documents(job_id)) == 2
    assert len(docs_ops.list_generated_documents(job_id, kind="resume")) == 1

    docs_ops.update_generated_document(d1, {"status": "approved"})
    assert docs_ops.get_generated_document(d1)["status"] == "approved"
    assert docs_ops.get_generated_document(d2)["match_after"] == 0.8

    # Deleting the job cascades the generated docs + evaluation (ORM backref cascade).
    docs_ops.save_job_evaluation(job_id, {"verdict": "ok"})
    assert db_ops.delete_job(job_id) is True
    with init_db.SessionLocal() as db:
        assert db.query(GeneratedDocument).count() == 0
        assert db.query(JobEvaluation).count() == 0


# ---- uploaded documents: raw log + derived link -------------------------------

def test_uploaded_documents_link(temp_db):
    uid = docs_ops.create_uploaded_document(
        {"filename": "assessment.pdf", "doc_type": "behavioral", "raw_text": "disc..."}
    )
    assert docs_ops.get_uploaded_document(uid)["status"] == "draft"

    bid = docs_ops.upsert_active_behavioral_profile({"strengths": ["ownership"]})
    docs_ops.update_uploaded_document(uid, {"derived_table": "behavioral_profiles",
                                            "derived_id": bid, "status": "saved"})
    got = docs_ops.get_uploaded_document(uid)
    assert got["derived_table"] == "behavioral_profiles"
    assert got["derived_id"] == bid
    assert got["status"] == "saved"
    assert len(docs_ops.list_uploaded_documents()) == 1


# ---- seed: idempotent + non-destructive ---------------------------------------

def test_seed_idempotent(temp_db):
    seed_documents_if_empty()
    n_templates = len(docs_ops.list_templates())
    assert n_templates >= 5
    assert docs_ops.get_active_behavioral_profile() is not None
    assert docs_ops.get_active_writing_style() is not None
    assert docs_ops.get_default_template("cover_letter") is not None
    assert docs_ops.get_default_template("job_evaluation") is not None

    # Running again adds nothing and does not clobber a user's edited active row.
    docs_ops.upsert_active_writing_style({"tone": "user-edited"})
    seed_documents_if_empty()
    assert len(docs_ops.list_templates()) == n_templates
    assert docs_ops.get_active_writing_style()["tone"] == "user-edited"
    with init_db.SessionLocal() as db:
        assert db.query(BehavioralProfile).filter(BehavioralProfile.is_active == 1).count() == 1


# ---- clear_jobs_database removes job-scoped rows, keeps document records -------

def test_clear_jobs_keeps_document_records(temp_db):
    seed_documents_if_empty()
    job_id = db_ops.add_job({"title": "SWE", "company": "Acme", "location": "Remote"}, create_statuses=True)
    docs_ops.save_job_evaluation(job_id, {"verdict": "ok"})
    docs_ops.create_generated_document({"job_id": job_id, "kind": "cover_letter", "content": "v1"})

    deleted = db_ops.clear_jobs_database()
    assert deleted == 1
    with init_db.SessionLocal() as db:
        assert db.query(Job).count() == 0
        assert db.query(JobEvaluation).count() == 0
        assert db.query(GeneratedDocument).count() == 0
        # Supporting-document records survive a jobs-scope clear.
        assert db.query(BehavioralProfile).count() >= 1
        assert db.query(WritingStyleProfile).count() >= 1
        assert db.query(DocumentTemplate).count() >= 5
