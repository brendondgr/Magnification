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
| **llm** | `service._llm_rerank` verdict | The LLM's 0-100 fit score (÷100), computed for **every analyzed job** by default (see Flow). Coverage is dialed by the single `llm_fraction` knob (default `1.0` = all; `<1.0` keeps the top `ceil(fraction × N)` by semantic+bm25). Absent when offline or outside that coverage share. |

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
| `compensation.py` | The **pure** enrichment layer: the combined prompt, the candidate predicates, `clean_compensation` (the single pay-string normalizer — rejects `nan`-poisoned and digit-less values), and the fixed `INDUSTRIES` taxonomy + `normalize_industry` (synonyms → canonical, unknown → "Other") that is the source of truth for the card's per-industry color. `extract_enrichment_llm` pulls **compensation + industry** from the description in one `chat_many` pass per job. Compensation returns None when no pay is stated (never fabricates). |
| `enrichment.py` | The **shared orchestration** around it — `enrich_jobs(jobs, runtime, force, on_progress)` is the one place that gates on `enable_llm_compensation` / `enable_llm_industry` + an enabled endpoint, selects candidates, calls the extractor, and persists. Called by **both** the scrape pipeline (before analysis) and `analyze_jobs`, so "Find Jobs" and "Analyze Matches" run identical extraction rather than two implementations. |
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
        → enrichment.enrich_jobs — extract compensation + industry from the description in one
          combined LLM pass (when enable_llm_compensation / enable_llm_industry + endpoint
          enabled). Pay is ALWAYS re-derived from the description, whatever the board reported;
          compensation_checked is flagged on every attempt so each job costs one call, not one
          per run, while industry_checked is flagged only when a label came back (an empty
          response = failed call → retry). Same function the scrape pipeline calls.   [once]
        → extract skills — reuse each job's stored extracted_skills; only (re)extract
          jobs that lack them (gazetteer, or LLM batch if enabled)   [reuse, like embeddings]
        → ranker.rank_batch → semantic/bm25/keyword/skill scores
        → seed any existing stored LLM verdict onto the fresh analysis  [preserve]
        → pick the coverage set over ALL analyzed jobs: top ceil(`llm_fraction` × N) by
          semantic+bm25 (default 1.0 = every job; <1.0 = that top share) — the slider is the
          single coverage control; THEN gap-fill — issue an LLM fit verdict only for jobs in
          the coverage set that don't already have one (2-3 sentences, weighs what the company
          wants) → fold `llm` into rag_score (renormalized when absent). So 100% guarantees
          every job ends up with a verdict while repeat runs stay cheap; 50% = the top 50% of
          all jobs. Applies to manual searches and the daily bot (shared workflow).
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
