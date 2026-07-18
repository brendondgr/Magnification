# Analyze Matches — LLM Fit Reasoning-Token Exhaustion

## 1. Introduction

"Analyze Matches" was reported to fit **only ~2 jobs per run**, leaving ~165 of 167
non-ignored jobs with "no LLM fitting." Investigation shows the recommendation
pipeline's coverage/gap-fill logic is **correct** — with `llm_fraction = 1.0` it selects
every job still missing a verdict — but the individual LLM verdict calls are **silently
failing** for the configured endpoint. The endpoint (`localhost:4000`, model `skynet`, a
reasoning/"thinking" model) spends its **entire `max_tokens` budget (4092) on hidden
reasoning tokens and never emits the final JSON answer**: the response comes back with
`finish_reason: "length"` and `content: null` (or a truncated, unparseable JSON fragment).
`chat_json` then fails to parse it, `chat_many` maps that item to `None`, and the verdict
is dropped. Only the occasional job whose reasoning happens to finish early yields a
parseable answer — hence "only ~2 land per run," and each subsequent click retries the
still-missing remainder, slowly and unreliably.

The fix is to **suppress model "thinking" for the structured JSON calls** the
recommendation/extraction pipeline makes. Empirically, adding
`chat_template_kwargs={"enable_thinking": false}` to the request makes this exact endpoint
return clean JSON in ~0.6s (`finish_reason: "stop"`, ~100 completion tokens) instead of
timing out on 4092 reasoning tokens — a measured jump from **3/10 → 9-10/10** verdicts per
batch and ~20× faster. The change is centralized in the OpenAI-compatible client, exposed
as an endpoint config toggle (`disable_thinking`, default on), and made
endpoint-agnostic with a graceful fallback so endpoints that reject the parameter still
work.

## 2. Gaps & Unanswered Questions

- **Which suppression parameter?** Tested against the live endpoint: `reasoning_effort:
  "low"` and `response_format: {"type":"json_object"}` did **not** stop the reasoning
  exhaustion; `chat_template_kwargs: {"enable_thinking": false}` (the vLLM/Qwen/Gemma
  convention) **did**. *Decision*: use `chat_template_kwargs.enable_thinking=false`.
- **Default on or off?** The user's single, local-first endpoint is a thinking model that
  is broken without suppression, and thinking adds no value to score/skill/compensation
  extraction. *Assumption*: default `disable_thinking = true`, with a graceful fallback so
  an endpoint that 400s on the unknown field auto-drops it (no breakage for real OpenAI /
  other servers).
- **Scope: all calls or only JSON calls?** Reasoning exhaustion produces `content: null`
  for *any* call on this endpoint, so suppression is applied at the client level to every
  request when the toggle is on (also unblocks the separately-tracked "hanging" cover-letter
  generation on this endpoint). *Assumption*: apply client-wide, gated by the toggle.
- **Retry semantics.** A rare transient still returns empty content. *Assumption*: retry a
  call once when `content` is empty/`None` (or `finish_reason == "length"` with empty
  content); do not loop further.

## 3. Hierarchical Step-by-Step Instructions

### Step 1: Plan doc + worktree
- **Locations**: `docs/plans/llm-fit-reasoning-exhaustion.md`; worktree
  `.claude/worktrees/fix-llm-fit-reasoning-exhaustion` on branch
  `fix-llm-fit-reasoning-exhaustion`.
- **Rationale**: Capture the root-cause diagnosis and the chosen fix before touching code,
  and isolate the work from the shared main checkout (other agents may switch its branch).
- **Action**: Undergo the verification/validation process for this phase (plan reviewed,
  worktree active, `import app` clean from the worktree using the shared venv). Once
  validated, commit stating: `LLM Fit Reasoning Exhaustion (1/5) Complete: root-cause plan doc + worktree`.

### Step 2: Client thinking-suppression + resilience
- **Locations**:
  - `utils/backend/llm/config.py` — add `disable_thinking: True` to
    `DEFAULT_LLM_ENDPOINT` (auto-whitelisted via `_ALLOWED_KEYS`).
  - `utils/backend/llm/client.py` — `OpenAIClient.__init__`/`from_config` read
    `disable_thinking`; `chat()` injects `chat_template_kwargs={"enable_thinking": False}`
    into the payload when enabled and not caller-overridden; on an HTTP 400 that names the
    unknown field, retry once without it and cache `self._thinking_param_ok = False` so it
    isn't re-sent; after a successful call, if `content` is empty/`None` (or
    `finish_reason == "length"` with empty content), retry the request once.
- **Rationale**: Centralizing the fix in the client fixes every structured call
  (verdict, skills, compensation, keywords, generation) at once, and the fallback keeps
  non-thinking / strict endpoints working.
- **Action**: Undergo the verification/tests/validation process for this phase
  (`tests/llm/test_client.py`: kwarg is sent when on, omitted when off, 400→drop-and-retry,
  empty-content retry; `import app` clean). Once validated, commit stating:
  `LLM Fit Reasoning Exhaustion (2/5) Complete: client suppresses model thinking for structured calls with graceful fallback`.

### Step 3: Options UI toggle
- **Locations**: `utils/frontend/templates/index.html` — LLM Endpoint section: add a
  "Disable model thinking (reasoning)" toggle; wire it into the endpoint state,
  `configToSave`/`applyConfig` load/save, and the embedded default (`disable_thinking:true`).
  Confirm `GET/POST /api/options/llm-endpoint` round-trips the new key (no route change
  needed — `_ALLOWED_KEYS` is derived from the default).
- **Rationale**: Give the user a visible, reversible control so they can turn thinking back
  on for an endpoint where it works, matching how every other runtime knob is exposed.
- **Action**: Undergo the verification/validation process for this phase (frontend wiring
  test asserts the toggle tokens are present; live round-trip: save `false` → reload → the
  toggle reflects it, then restore `true`). Once validated, commit stating:
  `LLM Fit Reasoning Exhaustion (3/5) Complete: Options toggle for model thinking`.

### Step 4: Docs + live end-to-end verification
- **Locations**: `docs/workflow.md` (reasoning-model note under the recommendation/LLM
  section), `docs/api-contract.md` (options `llm-endpoint` config gains `disable_thinking`),
  `docs/documentation.md` (status line), `docs/checklist.md` (this Definition of Done),
  `docs/plans/llm-fit-reasoning-exhaustion.md` (mark results). Live run of "Analyze Matches"
  against the real endpoint.
- **Rationale**: Docs must move with the code (project rule), and the whole point is that a
  real run now fits **all** the missing jobs, not ~2.
- **Action**: Undergo the verification/tests/validation process for this phase (offline
  subsets `tests/llm`, `tests/recommend`, `tests/test_frontend_wiring.py` green; live
  Analyze Matches fills every remaining missing verdict in one pass; **do not POST config to
  the running app** during verification). Once validated, commit stating:
  `LLM Fit Reasoning Exhaustion (4/5) Complete: docs + live all-jobs fit verified`.

### Step 5: Merge to main
- **Locations**: branch `fix-llm-fit-reasoning-exhaustion` → `main`.
- **Rationale**: Deliver the fix.
- **Action**: Merge to `main`, re-run the offline subset + `import app` on `main`. Once
  validated, commit/merge stating:
  `LLM Fit Reasoning Exhaustion (5/5) Complete: merged to main`.

## 4. Deliverables Table

| Deliverable | Description | Location (File/Path) |
| --- | --- | --- |
| Plan doc | This root-cause + phased plan | `docs/plans/llm-fit-reasoning-exhaustion.md` |
| Endpoint config key | `disable_thinking` default True | `utils/backend/llm/config.py` |
| Client suppression + fallback + retry | Inject `chat_template_kwargs.enable_thinking=false`; 400 fallback; empty-content retry | `utils/backend/llm/client.py` |
| Client unit tests | Kwarg on/off, 400 drop-and-retry, empty-content retry | `tests/llm/test_client.py` |
| Options toggle | "Disable model thinking" control + wiring | `utils/frontend/templates/index.html` |
| Frontend wiring test | Assert toggle tokens present | `tests/test_frontend_wiring.py` |
| Verdict-shape resilience | `_coerce_verdict` unwraps nested `{"score":{...}}` + numeric strings | `utils/backend/recommend/service.py` |
| Docs | workflow / api-contract / documentation / checklist updates | `docs/*.md` |

## 5. Results (delivered)

- **Measured fix:** on the live endpoint a batch of 10 missing verdicts went from **3/10 in
  52s** (baseline) to **9-10/10 in ~2s** with `enable_thinking=false`. `reasoning_effort:low`
  and `response_format:json_object` did **not** resolve it.
- **Live end-to-end:** the real "Analyze Matches" gap-fill drove the shared DB from **155/167
  to 167/167** jobs with an LLM fit across a few ~2.4s passes (vs the reported "2 fits in 68s").
- **Follow-on found in verification:** the last stubborn job failed not on reasoning but on a
  malformed `{"score": {"score": N, ...}}` shape; `service._coerce_verdict` now unwraps one
  nesting level + accepts numeric strings (rejects bools, clamps 0–100), and `_llm_rerank`
  uses it — closing the gap to 167/167.
