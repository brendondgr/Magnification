"""
Flask test-client tests for the PDF/tex endpoints of the generation blueprint.

Generates a document end-to-end on an isolated in-memory DB (offline path), then exercises
``GET /api/documents/<id>/pdf`` (compiles LaTeX → PDF), the ``?download=1`` disposition, the
``/tex`` source download, and the 404 / 415 error paths. The compile tests are skipped when
``pdflatex`` is not installed.
"""

import shutil
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import application
from utils.backend.database import init_db
from utils.backend.database import operations as db_ops
from utils.backend.database import documents_ops as docs_ops
from utils.backend.database.seed_documents import seed_documents_if_empty
from utils.backend.database.models import Base
from utils.backend.agents import context

_HAS_PDFLATEX = shutil.which("pdflatex") is not None
_needs_tex = pytest.mark.skipif(not _HAS_PDFLATEX, reason="pdflatex not installed")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(init_db, "SessionLocal", TestSession)

    def _no_endpoint(*a, **k):
        raise RuntimeError("endpoint disabled")
    monkeypatch.setattr(context.OpenAIClient, "from_config", _no_endpoint)

    # Redirect the PDF cache to a temp dir so tests never touch the shared data root.
    from utils.backend import pdf_compile
    monkeypatch.setattr(pdf_compile, "_CACHE_DIR", tmp_path / "pdfs")

    application.config.update(TESTING=True)
    yield application.test_client()
    engine.dispose()


def _seed():
    seed_documents_if_empty()
    db_ops.upsert_active_profile({"name": "Jane Doe", "resume_text": "Engineer. Python & C++.",
                                  "skills": ["Python", "PyTorch"], "job_titles": ["ML Engineer"]})
    job_id = db_ops.add_job({"title": "ML Engineer", "company": "R&D Labs & Co", "location": "Remote",
                             "description": "Python, PyTorch, Kubernetes."}, create_statuses=False)
    db_ops.save_job_analysis(job_id, {"rag_score": 0.5,
                             "skill_match": {"matched": ["Python"], "missing": ["PyTorch"]},
                             "extracted_skills": ["Python", "PyTorch"]},
                             profile_id=db_ops.get_active_profile()["id"])
    return job_id


def _generate(client, kind):
    path = f"/api/documents/{kind.replace('_', '-')}/start"
    tid = client.post(path, json={"job_id": _seed()}).get_json()["task_id"]
    deadline = time.time() + 15
    while time.time() < deadline:
        rec = client.get(f"/api/documents/status/{tid}").get_json()
        if rec.get("status") in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert rec["status"] == "completed", rec
    return rec["results"]["document_id"]


@_needs_tex
def test_pdf_route_streams_pdf(client):
    doc_id = _generate(client, "cover_letter")
    row = client.get(f"/api/documents/{doc_id}").get_json()
    assert row["format"] == "latex"
    assert row["content"].lstrip().startswith("\\documentclass")

    resp = client.get(f"/api/documents/{doc_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.get_data()[:5] == b"%PDF-"

    dl = client.get(f"/api/documents/{doc_id}/pdf?download=1")
    assert "attachment" in dl.headers.get("Content-Disposition", "")


@_needs_tex
def test_resume_pdf_route(client):
    doc_id = _generate(client, "resume")
    resp = client.get(f"/api/documents/{doc_id}/pdf")
    assert resp.status_code == 200 and resp.get_data()[:5] == b"%PDF-"


def test_tex_route_returns_source(client):
    doc_id = _generate(client, "cover_letter") if _HAS_PDFLATEX else None
    if doc_id is None:
        # Without pdflatex we still generate LaTeX; just skip the compile-dependent path.
        doc_id = _generate(client, "cover_letter")
    resp = client.get(f"/api/documents/{doc_id}/tex")
    assert resp.status_code == 200
    assert resp.mimetype in ("application/x-tex", "text/x-tex")
    assert b"\\documentclass" in resp.get_data()


def test_pdf_404_for_missing_and_415_for_non_latex(client):
    _seed()
    assert client.get("/api/documents/999999/pdf").status_code == 404
    # A markdown document has no PDF preview → 415.
    md_id = docs_ops.create_generated_document({
        "job_id": db_ops.get_all_jobs()[0]["id"], "kind": "cover_letter",
        "content": "# Plain markdown", "format": "markdown", "status": "draft"})
    assert client.get(f"/api/documents/{md_id}/pdf").status_code == 415
