# Thinking Token Budget (replace disable_thinking)

Plan owner: agent · Branch: `thinking-budget` (worktree `.claude/worktrees/thinking-budget`).
Supersedes the `disable_thinking` mechanism from `docs/plans/llm-fit-reasoning-exhaustion.md`.

## 1. Introduction

The LLM client currently suppresses reasoning entirely (`disable_thinking`, default on, sends
`chat_template_kwargs={"enable_thinking": False}`) because reasoning models were spending the whole
`max_tokens` budget thinking and returning empty answers. As a result the document generators (and
every other call) do **no** thinking. The user wants bounded thinking instead: a
`thinking_token_budget` sampling parameter (vLLM convention — sent top-level on the request, per the
provided curl/OpenAI examples), **default and minimum 1024**, adjustable in **Options → LLM
Endpoint**.

Decision (user-confirmed): apply to **all LLM calls** — the budget replaces the on/off
`disable_thinking` toggle. To avoid the original exhaustion problem, the client raises the effective
`max_tokens` by the budget (the configured `max_tokens` stays the *answer* budget; thinking gets its
own headroom on top). Endpoints that don't understand `thinking_token_budget` (e.g. hosted OpenAI)
still work: a `400` drops the param, restores `max_tokens`, and the client stops sending it.

## 2. Gaps & Unanswered Questions

- **Minimum 1024.** *Assumption:* the config value is clamped to `≥ 1024` on save and the UI input
  enforces `min=1024`, so thinking can be tuned up but not disabled (matching "1024 at the very
  least"). The client itself treats `budget > 0` as "send it" (0 would mean off), but the config
  never persists below 1024.
- **max_tokens interaction.** *Assumption:* effective `max_tokens = max_tokens + budget` when the
  budget is active, so a 1024 answer budget with a 1024 thinking budget sends `max_tokens: 2048` —
  the answer still fits after the model finishes thinking.
- **`chat_template_kwargs` override path.** Unused by any caller; removed with the suppression logic
  to keep the client simple.
- **Analyze Matches.** Now thinks (bounded) on verdict/skill/compensation calls; the max_tokens bump
  preserves the answer space, so the reasoning-exhaustion fix's intent (a non-empty answer) holds.
- Commit per phase; **do not push**.

## 3. Steps

### Step 1: Plan doc + worktree
- **Locations**: `docs/plans/thinking-token-budget.md`; branch `thinking-budget`.
- **Action**: Confirm baseline `tests/llm` + `import app` green in the worktree. Commit:
  `Thinking Budget (1/5) Complete: plan doc + worktree`.

### Step 2: Config + client + client tests
- **Locations**: `utils/backend/llm/config.py` (replace `disable_thinking` with
  `thinking_token_budget: 1024`; clamp `≥ 1024` on save); `utils/backend/llm/client.py`
  (`thinking_token_budget` param; send it top-level; bump effective `max_tokens`; `400`-fallback
  drops it + restores `max_tokens` + latches off; remove `chat_template_kwargs`/`_NO_THINKING`);
  rewrite the thinking tests in `tests/llm/test_client.py`.
- **Action**: `tests/llm` green; `import app` clean. Commit: `Thinking Budget (2/5) Complete:
  thinking_token_budget in endpoint config + client (max_tokens headroom + 400 fallback) + tests`.

### Step 3: Options UI
- **Locations**: `utils/frontend/templates/index.html` — replace the "Disable model thinking" toggle
  with a **Thinking token budget** number input (`min=1024`); update `llm` state default, getters
  (`llmThinkingBudget`/`onLlmThinkingBudget`), removing the toggle getters; update
  `tests/test_frontend_wiring.py`.
- **Action**: Wiring test green; verify live from the worktree server (Options → LLM Endpoint shows
  the budget input, defaults to 1024, saves) — snapshot/restore the real endpoint config around any
  live save. Commit: `Thinking Budget (3/5) Complete: Options → LLM Endpoint thinking-budget input`.

### Step 4: Docs + memory + full validation
- **Locations**: `docs/api-contract.md`, `docs/workflow.md`, `docs/documentation.md`,
  `docs/plans/llm-fit-reasoning-exhaustion.md` (superseded note), `docs/checklist.md`; update the
  `reasoning-endpoint-disable-thinking` memory.
- **Action**: Offline `tests/llm` + `tests/test_frontend_wiring.py` + `tests/recommend` +
  `import app` green. Commit: `Thinking Budget (4/5) Complete: docs + memory + validation`.

### Step 5: Merge to main
- **Action**: Merge to `main`, re-validate, remove worktree. Commit: `Thinking Budget (5/5)
  Complete: merged to main`.

## 4. Deliverables

| Deliverable | Location |
| --- | --- |
| Endpoint config field + clamp | `utils/backend/llm/config.py` |
| Client: budget param, max_tokens headroom, 400 fallback | `utils/backend/llm/client.py` |
| Options UI input | `utils/frontend/templates/index.html` |
| Client + wiring tests | `tests/llm/test_client.py`, `tests/test_frontend_wiring.py` |
| Docs + memory | `docs/*.md`, memory `reasoning-endpoint-disable-thinking` |
