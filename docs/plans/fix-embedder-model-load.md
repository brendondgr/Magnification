# Fix: "Could not load model BAAI/bge-small-en-v1.5 from any source" on Analyze Matches

## Symptom

Clicking **Analyze Matches** in the app fails with:

> Failed
> Could not load model BAAI/bge-small-en-v1.5 from any source.

## Root cause

`utils/backend/recommend/service.analyze_jobs` → `_ensure_embeddings` →
`embedder.get_model()` constructs `fastembed.TextEmbedding("BAAI/bge-small-en-v1.5")`.
On first use fastembed downloads the model (public repo `qdrant/bge-small-en-v1.5-onnx-q`)
from HuggingFace. Two environment realities made that fail:

1. **A stale/invalid stored HuggingFace token** (`~/.cache/huggingface/token`). fastembed's
   download goes through `huggingface_hub`, which *implicitly* attaches the cached token. The
   Hub rejects it ("OAuth token signature verification failed"), the authenticated download
   401s, and after the fallback source also fails fastembed raises
   `Could not load model ... from any source`. The model repo is **public** and needs no auth,
   so the token should never have been sent. Verified: disabling the implicit token
   (`HF_HUB_DISABLE_IMPLICIT_TOKEN=1`) makes the anonymous download succeed.
2. **Ephemeral cache dir.** fastembed's default cache is `os.path.join(tempfile.gettempdir(),
   "fastembed_cache")` = `/tmp/fastembed_cache`, which is wiped on reboot — so the ~130 MB
   model re-downloads every boot, and any download hiccup reproduces the failure. The project
   docs already claim the model "caches under `~/.cache`", which was not actually true.

`get_model()` raises, `_ensure_embeddings` does not catch it, and the background analyze task
reports the raw message as **Failed**.

## Fix (single location: `utils/backend/recommend/embedder.py`)

1. **Force anonymous HF access** for the model load. `HF_HUB_DISABLE_IMPLICIT_TOKEN` is bound
   into `huggingface_hub.constants` at import time, so setting the env var late is unreliable;
   set both the env var (for freshness / subprocesses) **and** the already-imported constant
   defensively, right before constructing `TextEmbedding`. A user who has a *valid* token and
   an `HF_TOKEN` env var is unaffected — only the implicit cached-token path is suppressed, and
   the model is public so no token is needed either way.
2. **Persistent cache dir.** Resolve a stable cache directory (`FASTEMBED_CACHE_PATH` if set,
   else `~/.cache/fastembed`) and pass it as `cache_dir=`, so the model downloads once and
   survives reboots.

## Validation

- New offline unit test (`tests/recommend/test_embedder_load.py`): `get_model` disables the
  implicit token + resolves a persistent cache dir; `_resolve_cache_dir` honors
  `FASTEMBED_CACHE_PATH`. No network needed (fastembed construction is monkeypatched).
- Live proof: with the invalid token present and no env overrides, `embedder.get_model()` /
  `embed_text("hello")` succeeds (downloads once to `~/.cache/fastembed`, reuses thereafter).
- `import app` clean; offline `tests/recommend` + `tests/database` subsets green.
- Drive **Analyze Matches** end-to-end against the running app and confirm it completes
  (no "Could not load model" failure).

## Docs

- `docs/workflow.md` — correct the cache location note (`~/.cache/fastembed`, overridable via
  `FASTEMBED_CACHE_PATH`) and record the anonymous-download behavior.
- `docs/checklist.md` — Definition of Done for this fix.
