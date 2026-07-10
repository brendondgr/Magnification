"""
Ingestion / summarization agent (design §1.3).

Generalizes the résumé→profile flow to every supporting document type: extract text
→ classify → summarize/normalize into the structured record for its target table,
returning a *draft* the user reviews before anything is persisted.
"""

from .agent import ingest_document, classify_document, DOC_TYPES

__all__ = ["ingest_document", "classify_document", "DOC_TYPES"]
