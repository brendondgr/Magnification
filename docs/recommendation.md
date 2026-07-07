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
| **llm** | `service._llm_rerank` verdict | The LLM's 0-100 fit score (÷100), computed for **every analyzed job** by default (see Flow). Coverage is dialed by `llm_fraction` (default `1.0` = all; `<1.0` keeps the top `ceil(fraction × N)` by semantic+bm25), with an optional `top_n_llm` absolute cap composing on top (`0` = all; `N>0` = top-N by semantic+bm25). Absent when offline or excluded by the fraction/cap. |

Weights are configurable in **Options → Runtime** (`runtime_config.weights`) as sliders that
must total exactly **1.00**; default `semantic 0.30 / bm25 0.15 / keyword 0.10 / skill 0.05 /
llm 0.40`. `ranker.combined_score` **renormalizes over the signals actually present**, so a job
with no LLM verdict is scored over the remaining `0.60` (i.e. the LLM's `0.40` is dropped and
the rest rescaled) — exactly as if the LLM weren't configured. Saving new weights auto-triggers a
cheap `rescore` (see Flow) so the displayed match percentages update immediately — no full
"Analyze Matches" needed.

## Modules (`utils/backend/recommend/`)

| File | Role |
| --- | --- |
| `embedder.py` | fastembed bge-small singleton; batch/parallel embed; float32 byte (de)serialization; cosine. |
| `bm25.py` | rank_bm25 index + tokenizer; raw + normalized scores. |
| `skills.py` | gazetteer skill extractor (+ optional LLM); `match_profile_skills`. |
| `compensation.py` | LLM compensation extraction — recovers pay from the description prose for jobs the board left blank (parallel `chat_many`); returns None when no pay is stated (never fabricates). Gated by `enable_llm_compensation` + an enabled endpoint; runs in the scrape pipeline before storage **and** during `analyze_jobs` (so "Analyze Matches" backfills pay for existing jobs). |
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
        → recover missing compensation from descriptions (LLM, when enable_llm_compensation
          + endpoint enabled) and persist it                            [gap-fill]
        → extract skills (gazetteer, or LLM batch if enabled)
        → ranker.rank_batch → semantic/bm25/keyword/skill scores
        → seed any existing stored LLM verdict onto the fresh analysis  [preserve]
        → LLM fit verdict only for jobs that don't already have one (gap-fill; 2-3 sentences,
          weighs what the company wants); coverage = `llm_fraction` (default 1.0 = all; <1.0
          keeps the top ceil(fraction × N) by semantic+bm25) then optional `top_n_llm` cap
          (0 = all, N>0 = top-N by semantic+bm25) → fold `llm` into rag_score (renormalized
          when absent). Applies to both manual searches and the daily bot (shared workflow).
        → save_job_analysis per job (JobAnalysis table)

Manual: POST /api/recommend/analyze  ("Analyze Matches" — gap-fills LLM fit + compensation for
        non-ignored jobs; pass reanalyze_all=true to re-score every job, e.g. after a profile edit)
Rescore: POST /api/recommend/rescore ("cheap refresh" — recompute sub-scores + rag_score from the
        STORED embedding/extracted_skills + current weights, preserving the stored LLM verdict; no
        re-embed, no LLM. Fired automatically by the UI after a score-weight save, a skill quick-add,
        or a Profile save so match percentages update on the page. Reweight-only fallback offline.)
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
