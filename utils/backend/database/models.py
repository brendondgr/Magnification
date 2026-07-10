"""
SQLAlchemy ORM Model Definitions for Magnification Job Search Application.

This module defines the database models:
- Job: Stores job listing information
- ApplicationStatus: Tracks application progression through interview stages
- Profile: A user profile built from a resume (interests, skills, titles, keyword groups)
- JobAnalysis: Per-job recommendation artifacts (embedding, skills, RAG/LLM scores)
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Index,
    Float, JSON, LargeBinary,
)
from sqlalchemy.orm import relationship, declarative_base, backref

Base = declarative_base()


class Job(Base):
    """
    Job model representing a job listing from web scrapers.
    
    Attributes:
        id: Primary key
        title: Job title (required)
        company: Company name (required)
        location: Job location (required)
        link: URL to the job posting
        description: Full job description
        compensation: Salary/compensation information
        site: The job board site where the job was found
        ignore: Flag to exclude from application tracking (0=track, 1=ignore)
        saved: Flag pinning the job to the Saved lane (0=not saved, 1=saved). Saved jobs
            are hidden from the New Jobs feed and always shown under the Saved tab, even
            after they are marked Applied.
        created_at: When the job was added to the database
        updated_at: Last update timestamp
    """
    __tablename__ = 'jobs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    link = Column(String(2048), nullable=True)
    description = Column(Text, nullable=True)
    compensation = Column(String(255), nullable=True)
    site = Column(String(50), nullable=True)
    ignore = Column(Integer, default=0)
    saved = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to application statuses - cascade delete when job is deleted
    application_statuses = relationship(
        "ApplicationStatus",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    # Indexes for frequently queried columns
    __table_args__ = (
        Index('idx_jobs_company', 'company'),
        Index('idx_jobs_ignore', 'ignore'),
        Index('idx_jobs_saved', 'saved'),
    )

    def is_ignored(self) -> bool:
        """Check if job is marked as ignored."""
        return self.ignore == 1

    def is_saved(self) -> bool:
        """Check if job is marked as saved (pinned to the Saved lane)."""
        return self.saved == 1
    
    def __repr__(self):
        return f"<Job(id={self.id}, title='{self.title}', company='{self.company}')>"


class ApplicationStatus(Base):
    """
    ApplicationStatus model tracking the progression of job applications.
    
    Each job (where ignore=0) will have 9 ApplicationStatus records,
    one for each stage of the application process.
    
    Attributes:
        id: Primary key
        job_id: Foreign key to jobs table
        status: Current status name (one of the 9 predefined values)
        checked: Checkpoint indicator (0=not reached, 1=reached)
        date_reached: Date when status was checked/reached (YYYY-MM-DD format)
    """
    __tablename__ = 'application_statuses'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    status = Column(String(50), nullable=False)
    checked = Column(Integer, default=0)
    date_reached = Column(String(10), nullable=True)  # YYYY-MM-DD format
    
    # Relationship back to job
    job = relationship("Job", back_populates="application_statuses")
    
    # Indexes for frequently queried columns
    __table_args__ = (
        Index('idx_app_status_job_id', 'job_id'),
        Index('idx_app_status_checked', 'checked'),
    )
    
    def is_checked(self) -> bool:
        """Check if this status milestone has been reached."""
        return self.checked == 1

    def __repr__(self):
        return f"<ApplicationStatus(id={self.id}, job_id={self.job_id}, status='{self.status}', checked={self.checked})>"


class Profile(Base):
    """
    A user profile built from a resume, used as the comparison target for the
    RAG + LLM recommendation system.

    Attributes:
        id: Primary key
        name: Human label (the shipped UI uses a single "default" profile)
        is_active: 1 if this is the active profile used for scoring (only one at a time)
        source_filename: Original resume filename (pdf/tex/md), if uploaded
        resume_text: Extracted plain text of the resume
        interests_paragraph: Open-body paragraph of research/job interests (LLM matching)
        skills: JSON list of skill strings
        job_titles: JSON list of search-query job titles
        keyword_groups: JSON list of {label, terms:[...], scopes:[...]} groups. Semantics
            are AND across groups, OR within a group (matches utils/backend/scrapers/job_filter).
            ``scopes`` is a subset of {"title","description"} controlling where a group's terms
            are matched (defaults to both). An unsatisfied group hard-blocks a job.
        blocked_companies: JSON list of company names to hide entirely (case-insensitive).
        title_blocklist: JSON list of substrings; any job whose title contains one is hidden.
        llm_instructions: free-text guidance the user supplies to steer the LLM profile build.
        created_at / updated_at: Audit timestamps
    """
    __tablename__ = 'profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, default='default')
    is_active = Column(Integer, default=0)
    source_filename = Column(String(512), nullable=True)
    resume_text = Column(Text, nullable=True)
    interests_paragraph = Column(Text, nullable=True)
    skills = Column(JSON, nullable=True)            # list[str]
    job_titles = Column(JSON, nullable=True)        # list[str]
    keyword_groups = Column(JSON, nullable=True)    # list[{label, terms:[...], scopes:[...]}]
    blocked_companies = Column(JSON, nullable=True) # list[str]
    title_blocklist = Column(JSON, nullable=True)   # list[str]
    llm_instructions = Column(Text, nullable=True)  # free-text guidance for the LLM profile build
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_profiles_active', 'is_active'),
    )

    def __repr__(self):
        return f"<Profile(id={self.id}, name='{self.name}', is_active={self.is_active})>"


class JobAnalysis(Base):
    """
    Per-job recommendation artifacts (1:1 with Job).

    The embedding is profile-independent (the job description's vector) and is
    computed once on retrieval; the scores are computed against ``profile_id`` and
    are overwritten when a job is re-analyzed against a different active profile.

    Attributes:
        job_id: FK to jobs.id (unique -> 1:1)
        profile_id: FK to profiles.id the scores were computed against
        embedding: packed float32 bytes of the bge-small-en-v1.5 vector
        embedding_dim: vector dimensionality (384 for bge-small-en-v1.5)
        extracted_skills: JSON list of skills found in the job description
        semantic_score / bm25_score / keyword_score / skill_score: component signals
        rag_score: combined hybrid relevance (0..1)
        keyword_group_hits: JSON {group_label: [matched terms]}
        skill_match: JSON {matched:[...], missing:[...]}
        llm_score: optional LLM verdict (0..100)
        llm_rationale: optional LLM explanation
        analyzed_at: last analysis timestamp
    """
    __tablename__ = 'job_analyses'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    profile_id = Column(Integer, ForeignKey('profiles.id', ondelete='SET NULL'), nullable=True)

    embedding = Column(LargeBinary, nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    extracted_skills = Column(JSON, nullable=True)

    semantic_score = Column(Float, nullable=True)
    bm25_score = Column(Float, nullable=True)
    keyword_score = Column(Float, nullable=True)
    skill_score = Column(Float, nullable=True)
    rag_score = Column(Float, nullable=True)

    keyword_group_hits = Column(JSON, nullable=True)
    skill_match = Column(JSON, nullable=True)

    llm_score = Column(Float, nullable=True)
    llm_rationale = Column(Text, nullable=True)

    analyzed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 1:1 with Job; deleting a job removes its analysis (ORM-level cascade,
    # mirroring how ApplicationStatus is cascaded).
    job = relationship(
        "Job",
        backref=backref("analysis", uselist=False, cascade="all, delete-orphan"),
    )

    __table_args__ = (
        Index('idx_job_analyses_job_id', 'job_id', unique=True),
        Index('idx_job_analyses_profile_id', 'profile_id'),
        Index('idx_job_analyses_rag_score', 'rag_score'),
    )

    def __repr__(self):
        return f"<JobAnalysis(id={self.id}, job_id={self.job_id}, rag_score={self.rag_score})>"


# ============================================================================
# Agentic Document System — supporting-document + generation tables.
#
# These back the Profile & Documents sidebar and the (future) cover-letter /
# résumé agent graphs. They are brand-new tables, so ``Base.metadata.create_all``
# adds them to both fresh and pre-existing databases — no column migration is
# needed. The two "profile-like" tables (BehavioralProfile, WritingStyleProfile)
# keep a single ``is_active`` row, exactly like ``Profile``. Job-linked tables FK
# to ``jobs.id`` with cascade delete, mirroring ``JobAnalysis``.
# See docs/plans/agentic-documents-system.md §1.2.
# ============================================================================


class UploadedDocument(Base):
    """
    A raw source file the user drops into the Profile & Documents sidebar,
    stored before/after summarization by the ingestion agent.

    Attributes:
        filename: original upload filename.
        doc_type: inferred/declared type (resume | behavioral | writing | reference | other).
        raw_text: extracted plain text of the upload.
        summary: agent summary (used directly for reference/other docs).
        derived_table / derived_id: link to the structured record the ingestion agent
            produced from this upload (e.g. ('behavioral_profiles', 3)), so the user can
            always trace "this record came from that file".
        status: draft (ingested, not yet saved) | saved.
        uploaded_at: upload timestamp.
    """
    __tablename__ = 'uploaded_documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(512), nullable=True)
    doc_type = Column(String(50), nullable=True)
    raw_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    derived_table = Column(String(64), nullable=True)
    derived_id = Column(Integer, nullable=True)
    status = Column(String(32), default='draft')
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_uploaded_documents_doc_type', 'doc_type'),
    )

    def __repr__(self):
        return f"<UploadedDocument(id={self.id}, filename='{self.filename}', doc_type='{self.doc_type}')>"


class BehavioralProfile(Base):
    """
    DISC/PI-style work-style traits that shape the *tone and framing* of generated
    documents. Single-active-row pattern (mirrors ``Profile``).

    Attributes:
        traits: JSON of work-style traits (e.g. {"dominance": "high", ...} or a list).
        strengths: JSON list of strength strings.
        work_style_paragraph: a cohesive paragraph describing how the candidate works.
        source_filename: the upload this was derived from, if any.
    """
    __tablename__ = 'behavioral_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, default='default')
    is_active = Column(Integer, default=0)
    traits = Column(JSON, nullable=True)
    strengths = Column(JSON, nullable=True)
    work_style_paragraph = Column(Text, nullable=True)
    source_filename = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_behavioral_profiles_active', 'is_active'),
    )

    def __repr__(self):
        return f"<BehavioralProfile(id={self.id}, name='{self.name}', is_active={self.is_active})>"


class WritingStyleProfile(Base):
    """
    Tone, structure, do's/don'ts, and a real writing sample to imitate. Single-active-row
    pattern (mirrors ``Profile``).

    Attributes:
        tone: high-level tone label (e.g. "warm-professional").
        formality: formality label (e.g. "semi-formal").
        sentence_length: preferred cadence label (e.g. "medium, varied").
        sample_text: a representative writing sample the Voice agent imitates.
        dos / donts: JSON lists of do / don't guidance.
        source_filename: the upload this was derived from, if any.
    """
    __tablename__ = 'writing_style_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False, default='default')
    is_active = Column(Integer, default=0)
    tone = Column(String(120), nullable=True)
    formality = Column(String(60), nullable=True)
    sentence_length = Column(String(60), nullable=True)
    sample_text = Column(Text, nullable=True)
    dos = Column(JSON, nullable=True)
    donts = Column(JSON, nullable=True)
    source_filename = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_writing_style_profiles_active', 'is_active'),
    )

    def __repr__(self):
        return f"<WritingStyleProfile(id={self.id}, name='{self.name}', is_active={self.is_active})>"


class DocumentTemplate(Base):
    """
    A reusable cover-letter / résumé skeleton, or a job-evaluation rubric. Multiple rows;
    ``is_default`` marks the default within a ``kind``.

    Attributes:
        kind: cover_letter | resume | job_evaluation.
        name: human label (e.g. "Classic", "Narrative", "Referral").
        body: the template body, with slots like {{hook}}, {{why_them}}, {{why_you}}, {{close}}.
        format: markdown | latex | docx.
        is_default: 1 if this is the default template for its kind.
    """
    __tablename__ = 'document_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    kind = Column(String(32), nullable=False, default='cover_letter')
    name = Column(String(120), nullable=False, default='Untitled')
    body = Column(Text, nullable=True)
    format = Column(String(16), default='markdown')
    is_default = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('idx_document_templates_kind', 'kind'),
    )

    def __repr__(self):
        return f"<DocumentTemplate(id={self.id}, kind='{self.kind}', name='{self.name}')>"


class JobEvaluation(Base):
    """
    Per-job **application-fit** evaluation — a richer, application-oriented read than
    ``JobAnalysis`` (which is recommendation ranking). Seeded from ``JobAnalysis`` so it
    starts half-filled and cheap. 1:1 with Job (upserted by job_id).

    Attributes:
        verdict: short application-fit verdict text.
        fit_score: application-fit score (0..100).
        emphasize / gaps / talking_points: JSON lists.
        risks: free-text risks/notes.
    """
    __tablename__ = 'job_evaluations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    profile_id = Column(Integer, ForeignKey('profiles.id', ondelete='SET NULL'), nullable=True)

    verdict = Column(Text, nullable=True)
    fit_score = Column(Float, nullable=True)
    emphasize = Column(JSON, nullable=True)
    gaps = Column(JSON, nullable=True)
    risks = Column(Text, nullable=True)
    talking_points = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 1:1 with Job; deleting a job removes its evaluation (ORM-level cascade, like JobAnalysis).
    job = relationship(
        "Job",
        backref=backref("evaluation", uselist=False, cascade="all, delete-orphan"),
    )

    __table_args__ = (
        Index('idx_job_evaluations_job_id', 'job_id', unique=True),
        Index('idx_job_evaluations_profile_id', 'profile_id'),
    )

    def __repr__(self):
        return f"<JobEvaluation(id={self.id}, job_id={self.job_id}, fit_score={self.fit_score})>"


class GeneratedDocument(Base):
    """
    A generated cover letter or résumé linked to a job. Multiple revisions per job.

    Attributes:
        kind: cover_letter | resume.
        content: the rendered document body.
        format: markdown | latex | docx.
        status: draft | approved.
        match_before / match_after: recommender match-lift (résumé fine-tuner), 0..1.
        revision: revision counter.
        checkpoint_state: JSON snapshot of the in-house orchestrator's paused state, so a
            document generation can survive HTTP round-trips / interrupts (in lieu of a
            LangGraph checkpointer).
    """
    __tablename__ = 'generated_documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False)
    kind = Column(String(32), nullable=False, default='cover_letter')
    content = Column(Text, nullable=True)
    format = Column(String(16), default='markdown')
    status = Column(String(16), default='draft')
    match_before = Column(Float, nullable=True)
    match_after = Column(Float, nullable=True)
    revision = Column(Integer, default=1)
    checkpoint_state = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job = relationship(
        "Job",
        backref=backref("generated_documents", cascade="all, delete-orphan", lazy="dynamic"),
    )

    __table_args__ = (
        Index('idx_generated_documents_job_id', 'job_id'),
        Index('idx_generated_documents_kind', 'kind'),
    )

    def __repr__(self):
        return f"<GeneratedDocument(id={self.id}, job_id={self.job_id}, kind='{self.kind}', status='{self.status}')>"
