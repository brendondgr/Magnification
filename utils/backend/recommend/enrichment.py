"""
The shared description-enrichment pass: compensation + industry, in one LLM call per job.

This is the **single** implementation used by both workflows that touch job descriptions:

- **Find Jobs** — ``scrapers/scraping_service.execute_full_scraping_workflow`` step 7a, on the
  jobs a fresh scrape kept.
- **Analyze Matches** — ``recommend/service.analyze_jobs``, on every non-ignored job.

Both call :func:`enrich_jobs`. Keeping the gating, candidate selection, LLM call, and
persistence in one place is deliberate: the two paths previously re-implemented all four
around the shared extractor and drifted apart. The pure extraction layer (prompt, predicates,
parsing, the industry taxonomy) lives in ``compensation.py``.

Semantics:

- Compensation is **always** re-derived from the description text — the board's own salary
  field is unreliable (Indeed reports NaN amounts) — so any job with a description is a
  candidate until it has been checked once. A figure found in the description wins; when the
  description states no pay, whatever the board gave is left alone.
- ``compensation_checked`` is stamped on every attempted job, including the ones whose
  description genuinely states no pay, so they are asked once rather than once per run.
- ``industry_checked`` is stamped **only when a label actually came back**. An empty or failed
  response has to retry on the next run — the model is asked to always pick a label, so
  "no answer" means the call failed, not that the job has no industry.
"""

from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from utils.backend.database import operations as db_ops
from utils.backend.llm.client import OpenAIClient
from utils.backend.llm.config import load_llm_endpoint_config
from .compensation import clean_compensation, extract_enrichment_llm, needs_enrichment
from .runtime_config import get_runtime_config

ProgressFn = Optional[Callable[[str], None]]


def _emit(on_progress: ProgressFn, message: str) -> None:
    if not on_progress:
        return
    try:
        on_progress(message)
    except Exception:  # pragma: no cover - a broken reporter must not fail enrichment
        pass


def enrichment_fields(runtime: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
    """Which enrichment fields are switched on right now (``{"compensation": …, "industry": …}``)."""
    runtime = runtime if runtime is not None else get_runtime_config()
    return {
        "compensation": bool(runtime.get("enable_llm_compensation")),
        "industry": bool(runtime.get("enable_llm_industry")),
    }


def select_candidates(jobs: List[Dict[str, Any]], runtime: Optional[Dict[str, Any]] = None,
                      force: bool = False) -> List[Dict[str, Any]]:
    """The jobs an enrichment run would query, honoring the per-field toggles."""
    fields = enrichment_fields(runtime)
    if not (fields["compensation"] or fields["industry"]):
        return []
    return [j for j in (jobs or [])
            if needs_enrichment(j, comp_on=fields["compensation"],
                                industry_on=fields["industry"], force=force)]


def enrich_jobs(jobs: List[Dict[str, Any]], runtime: Optional[Dict[str, Any]] = None,
                force: bool = False, on_progress: ProgressFn = None) -> Dict[str, int]:
    """
    Extract compensation + industry from the given jobs' descriptions and persist the results.

    Mutates the passed job dicts in place (so callers scoring them in the same pass see the
    recovered values) and writes them through ``update_job``. Returns
    ``{"candidates", "compensation", "industry"}`` — the number of jobs queried and the number
    of each field actually filled.

    A no-op when both field toggles are off, when the LLM endpoint is disabled, or when no job
    needs anything. Non-fatal: a failing endpoint is logged and reported as zero recoveries so
    the surrounding scrape/analysis still completes. Pass ``force=True`` (a full reanalyze) to
    re-query jobs that were already checked.
    """
    empty = {"candidates": 0, "compensation": 0, "industry": 0}

    fields = enrichment_fields(runtime)
    comp_on, industry_on = fields["compensation"], fields["industry"]
    if not (comp_on or industry_on):
        return empty

    cfg = load_llm_endpoint_config()
    if not cfg.get("enabled"):
        return empty

    runtime = runtime if runtime is not None else get_runtime_config()
    pending = select_candidates(jobs, runtime, force=force)
    if not pending:
        _emit(on_progress, "Pay + industry already extracted — nothing to recover.")
        return empty

    what = " + ".join(n for n, on in (("pay", comp_on), ("industry", industry_on)) if on)
    _emit(on_progress, f"Extracting {what} from {len(pending)} description(s) via LLM…")

    # Snapshot so we only write a field back when this pass actually produced it — the job
    # dicts already carry the board's compensation, which is not ours to re-persist.
    before = [(j.get("compensation"), j.get("industry")) for j in pending]

    try:
        client = OpenAIClient.from_config(cfg)
        comp_found, industry_found = extract_enrichment_llm(
            pending, client, comp=comp_on, industry=industry_on,
            max_workers=int(runtime.get("llm_workers", 4) or 4))
    except Exception as e:
        logger.warning(f"Enrichment (pay/industry) extraction failed (non-fatal): {e}")
        _emit(on_progress, "Pay + industry extraction unavailable (LLM error).")
        return empty

    for job, (old_comp, old_industry) in zip(pending, before):
        updates: Dict[str, Any] = {}
        if comp_on:
            # Checked either way: a description that states no pay must not be re-asked.
            updates["compensation_checked"] = 1
            found = clean_compensation(job.get("compensation"))
            if found and job.get("compensation") != old_comp:
                updates["compensation"] = found
        if industry_on and job.get("industry") and job.get("industry") != old_industry:
            # Only stamp `checked` alongside a real label, so a failed call retries later.
            updates["industry"] = job["industry"]
            updates["industry_checked"] = 1
        try:
            db_ops.update_job(job["id"], updates)
        except Exception as e:  # pragma: no cover - one bad row must not lose the rest
            logger.warning(f"Could not persist enrichment for job {job.get('id')}: {e}")

    _emit(on_progress,
          f"Recovered pay for {comp_found} · industry for {industry_found} job(s)")
    logger.info(f"  LLM enrichment: pay {comp_found}, industry {industry_found} / {len(pending)}")
    return {"candidates": len(pending), "compensation": comp_found, "industry": industry_found}
