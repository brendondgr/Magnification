"""
Agentic Document System — in-house agent orchestration.

Plain-Python agents (no LangGraph) that ride on the existing ``OpenAIClient`` and DB
layers. This package currently ships the ingestion/summarization agent (§1.3); the
cover-letter and résumé generation graphs (§2/§3) are planned follow-ups that will add
sibling ``cover_letter/`` and ``resume/`` modules plus a small orchestrator + service.
See docs/plans/agentic-documents-system.md and docs/plans/agentic-documents-foundation.md.
"""
