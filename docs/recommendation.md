# Recommendation System — Magnification

A hybrid **RAG + LLM** recommender that scores each scraped job against the active
[profile](profile.md) and surfaces a per-job **match score** with a breakdown.

## Signals (hybrid score)

Computed per job by `utils/backend/recommend/ranker.py` and combined into `rag_score` (0..1):

| Signal | Source | Notes |
| --- | --- | --- |
| **semantic** | `embedder.cosine(profile_vec, job_vec)` | bge-small-en-v1.5 (384-dim, CPU). Profile vector = embedding of interests + skills + titles + keyword terms. |
| **bm25** | `bm25.BM25Index` over the job corpus | Lexical overlap of the profile query vs descriptions, normalized 0..1. |
| **keyword** | `ranker.keyword_group_score` | Fraction of the profile's keyword groups satisfied — **AND across groups, OR within**, and **scope-aware**: each group's `scopes` (⊆ title/description) picks where its terms are matched. Groups also act as a **hard filter** at scrape time (see `docs/profile.md`). |
| **skill** | `skills.match_profile_skills` | Fraction of the job's extracted skills the profile covers. |
| **llm** | `service._llm_rerank` verdict | The LLM's 0-100 fit score (÷100), computed only for the top-N candidates (see Flow). Absent when offline or outside the top-N. |

Weights are configurable in **Options → Runtime** (`runtime_config.weights`) as sliders that
must total exactly **1.00**; default `semantic 0.30 / bm25 0.15 / keyword 0.10 / skill 0.05 /
llm 0.40`. `ranker.combined_score` **renormalizes over the signals actually present**, so a job
with no LLM verdict is scored over the remaining `0.60` (i.e. the LLM's `0.40` is dropped and
the rest rescaled) — exactly as if the LLM weren't configured.

## Modules (`utils/backend/recommend/`)

| File | Role |
| --- | --- |
| `embedder.py` | fastembed bge-small singleton; batch/parallel embed; float32 byte (de)serialization; cosine. |
| `bm25.py` | rank_bm25 index + tokenizer; raw + normalized scores. |
| `skills.py` | gazetteer skill extractor (+ optional LLM); `match_profile_skills`. |
| `compensation.py` | LLM compensation extraction — recovers pay from the description prose for jobs the board left blank (parallel `chat_many`); returns None when no pay is stated (never fabricates). Gated by `enable_llm_compensation` + an enabled endpoint; runs in the scrape pipeline before storage. |
| `ranker.py` | pure hybrid scoring (no I/O) — unit-tested with fake vectors. |
| `service.py` | orchestration: embed-on-retrieve (reuse stored vectors), skill extraction, scoring, persist `JobAnalysis`; builds the ranked report. |
| `runtime_config.py` | parallelism + toggles + weights (`config/runtime_config.json`). |
| `profile_builder.py` | résumé → profile (see [profile.md](profile.md)). |

## Flow

```
Scrape completes → scraping_service (if runtime.enable_analysis and an active profile exists)
    → recommend.service.analyze_jobs(new_job_ids)
        → keep only the remainder left visible after filtering (non-ignored jobs)
          [jobs_config Title/Description keywords + profile block rules: blocked companies,
           title blocklist, scoped keyword groups — see docs/profile.md]
        → embed missing job descriptions (parallel, fastembed)         [embed-on-retrieve]
        → extract skills (gazetteer, or LLM batch if enabled)
        → ranker.rank_batch → semantic/bm25/keyword/skill scores
        → take the top-N (default 30) by (semantic + bm25) → LLM fit verdict (2-3 sentences,
          weighs what the company wants) → fold `llm` into rag_score (renormalized when absent)
        → save_job_analysis per job (JobAnalysis table)

Manual: POST /api/recommend/analyze  (re-score on demand, e.g. after editing the profile)
Read:   GET  /api/jobs?with_analysis=1   → each job carries its `analysis`
        GET  /api/recommend/report       → jobs ranked by rag_score
```

Analysis is **non-fatal** in the scrape pipeline: if the embedding model is unavailable
(offline) the scrape still succeeds; jobs simply have no scores until analyzed later.

## UI

New Jobs cards show a **match badge** (color-graded by score) and a **Sort: Match/Newest**
toggle + **Analyze matches** button. The job detail panel shows a **Profile Match** section:
the score, per-signal bars, matched vs missing skills, matched keyword groups, and (when LLM
re-rank is enabled) the LLM rationale. See `docs/component-map.md`.

## Performance / parallelism

- Embedding: fastembed batch with `parallel=embed_workers`.
- LinkedIn description fetch: **serial (1 at a time)** to avoid the guest endpoint's rate-limiting
  (see `docs/data-flow.md`).
- LLM skill extraction / verdicts: `OpenAIClient.chat_many` with `llm_workers`.
- Stored embeddings are reused across re-analysis (only missing ones are recomputed).
