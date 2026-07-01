"""
CRUD round-trip tests for the recommendation data model (Profile + JobAnalysis).

Runs against an isolated in-memory SQLite engine (never the real dev DB), the same
pattern as test_clear_jobs.py: patches the module-level ``SessionLocal`` that
``get_db_context`` resolves at call time. This test exercises the single-active-profile
invariant across multiple rows, which would corrupt a real profile's `is_active` flag
if it ever ran against a non-empty database without isolation.
"""

import struct

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database.models import Base


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


def test_profile_crud_and_single_active_invariant(temp_db):
    p1 = db_ops.create_profile({
        "name": "default",
        "is_active": 1,
        "interests_paragraph": "Interested in ML for healthcare.",
        "skills": ["python", "pytorch"],
        "job_titles": ["ML Engineer", "Research Scientist"],
        "keyword_groups": [
            {"label": "AI/ML", "terms": ["machine learning", "ai", "coding"]},
            {"label": "Domain", "terms": ["healthcare", "medicine"]},
        ],
    })
    p2 = db_ops.create_profile({"name": "second", "skills": ["go"]})

    active = db_ops.get_active_profile()
    assert active is not None and active["id"] == p1
    assert active["skills"] == ["python", "pytorch"]
    assert active["keyword_groups"][1]["label"] == "Domain"

    # Switching active enforces a single active profile.
    assert db_ops.set_active_profile(p2) is True
    active = db_ops.get_active_profile()
    assert active["id"] == p2
    assert db_ops.get_profile_by_id(p1)["is_active"] == 0

    # upsert_active updates the active profile in place (no new row).
    before = {p["id"] for p in db_ops.list_profiles()}
    same_id = db_ops.upsert_active_profile({"interests_paragraph": "Updated."})
    assert same_id == p2
    assert {p["id"] for p in db_ops.list_profiles()} == before
    assert db_ops.get_profile_by_id(p2)["interests_paragraph"] == "Updated."

    db_ops.delete_profile(p1)
    db_ops.delete_profile(p2)
    assert db_ops.get_profile_by_id(p1) is None
    assert db_ops.get_profile_by_id(p2) is None


def test_job_analysis_upsert_embedding_and_cascade(temp_db):
    job_id = db_ops.add_job({
        "title": "RAG Test Engineer",
        "company": "Acme",
        "location": "Remote",
        "description": "Build retrieval systems.",
        "site": "indeed",
    })
    # float32 vector packed to bytes, as the embedder will store it.
    vec = [0.1, 0.2, 0.3, 0.4]
    blob = struct.pack(f"<{len(vec)}f", *vec)
    db_ops.save_job_analysis(job_id, {
        "embedding": blob,
        "embedding_dim": len(vec),
        "extracted_skills": ["retrieval", "python"],
        "semantic_score": 0.8,
        "bm25_score": 0.5,
        "rag_score": 0.72,
        "skill_match": {"matched": ["python"], "missing": ["rust"]},
    }, profile_id=None)

    # Upsert (no duplicate row) updates fields in place.
    db_ops.save_job_analysis(job_id, {"llm_score": 91.0, "llm_rationale": "Strong fit."})

    view = db_ops.get_analysis_for_job(job_id)
    assert view["has_embedding"] is True
    assert "embedding" not in view  # excluded by default
    assert view["rag_score"] == 0.72
    assert view["llm_score"] == 91.0
    assert view["skill_match"]["missing"] == ["rust"]

    full = db_ops.get_analysis_for_job(job_id, include_embedding=True)
    assert struct.unpack(f"<{full['embedding_dim']}f", full["embedding"]) == pytest.approx(vec)

    batch = db_ops.get_analysis_for_jobs([job_id, 10_000_000])
    assert set(batch.keys()) == {job_id}

    db_ops.delete_job(job_id)
    # Deleting the job cascades to its analysis.
    assert db_ops.get_analysis_for_job(job_id) is None
