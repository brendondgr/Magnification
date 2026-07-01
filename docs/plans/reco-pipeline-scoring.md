# Plan: Recommendation Pipeline Reorder + LLM-Weighted Scoring

## Introduction

Refines the recommendation pipeline to match the intended order and folds the LLM verdict
into the final score. Also fixes LinkedIn rate-limiting by serializing description fetch, and
turns the Runtime score weights into sliders that must total exactly 1.0.

## Current behavior (baseline)

- Scrape → dedupe → (LLM compensation) → store → `job_filter` marks non-matching jobs ignored
  (Title/Description keywords) → analysis.
- `analyze_jobs` embeds **all** stored jobs, scores `rag_score = wsum(semantic,bm25,keyword,skill)`
  (renormalized over present signals), optionally adds an LLM verdict to the top-10 **but never
  folds `llm_score` into `rag_score`**. LinkedIn descriptions are fetched in parallel.

## Target behavior

Extract → Deduplicate → **keyword filter (Title/Description keywords)** → **embed only the
remainder (non-ignored)** → rank by **semantic + BM25** → **top 30** → **LLM** fit verdict
(2–3 sentences, weighs what the company wants) → final score folds the LLM in.

- **Weights** (sum 1.0): semantic 0.30, bm25 0.15, keyword 0.10, skill 0.05, **llm 0.40**.
- **Renormalization**: jobs without an LLM score (offline, or outside the top-30) are scored
  over the remaining signals — `ranker._combine` already divides by the sum of present weights.
- LLM returns `{score:0-100, rationale:"2-3 sentences"}`; score normalized to 0..1 as the `llm`
  signal. `top_n_llm` default 30; `enable_llm_rerank` default true (no-ops without an endpoint).

## Steps

1. **Worktree + plan** (this doc). Smoke test. Commit `(1/5)`.
2. **LinkedIn serial fetch** — `linkedin_scraper.fetch_descriptions_for_jobs` runs 1 request at a
   time (workers forced to 1) with the jittered delay, to stop rate-limiting. Update the parallel
   test to assert serial. Commit `(2/5)`.
3. **Pipeline + scoring** — `service.analyze_jobs`: analyze only non-ignored jobs; embed the
   remainder; select top-30 by semantic+bm25 for the LLM; recompute `rag_score` folding `llm`;
   `ranker.DEFAULT_WEIGHTS` gains `llm`; public `combined_score`; refined 2–3 sentence
   company-aware verdict prompt; `runtime_config` defaults (`top_n_llm=30`,
   `enable_llm_rerank=True`, weights incl. `llm`). Tests. Commit `(3/5)`.
4. **Weights UI** — Options→Runtime: 5 range sliders (semantic/bm25/keyword/skill/llm), a live
   **Total** with an exactly-1.0 indicator (green ✓ / red), Save blocked unless total==1.0.
   Commit `(4/5)`.
5. **Docs + merge** — recommendation/data-flow/api-contract/find_jobs/checklist; full gate;
   merge to `main`. Commit `(5/5)`.

## Deliverables

| Deliverable | Location |
| --- | --- |
| Serial LinkedIn fetch | `utils/backend/scrapers/linkedin_scraper.py` |
| Pipeline reorder + LLM-weighted score | `utils/backend/recommend/service.py`, `ranker.py`, `runtime_config.py` |
| Company-aware 2–3 sentence verdict | `utils/backend/recommend/service.py` |
| Weight sliders + total=1.0 | `utils/frontend/templates/index.html` |
| Tests | `tests/recommend/test_ranker.py`, `tests/recommend/test_recommend_service.py`, `tests/recommend/test_linkedin_parallel.py` |
| Docs | `docs/*` |
