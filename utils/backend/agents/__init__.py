"""
Agentic Document System — in-house agent orchestration.

Plain-Python agents (no LangGraph) that ride on the existing ``OpenAIClient`` and DB
layers. This package ships the cover-letter and résumé generation graphs (§2/§3) driven
by a small orchestrator + service, all steered by the single editable Document Guidance
(``document_guidance.py``). See docs/plans/agentic-documents-system.md and
docs/plans/documents-sidebar-simplify.md.
"""
