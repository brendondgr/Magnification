# Cover Letter Multi-Agent System — Design Plan

**Stack:** Python + LangGraph
**Autonomy model:** Semi-automatic (runs end-to-end, pauses at a small number of checkpoints when confidence is low or the user opts in)
**Status:** Design only — no implementation

---

## 1. Design philosophy

A cover letter fails in one of two ways: it's *generic* (could be sent to any company) or it's *dishonest* (claims experience the candidate doesn't have). The architecture is built to defeat both. We separate **strategy** (what to say) from **prose** (how to say it) from **voice** (how it sounds), so each can be reasoned about and re-run independently. A single lightweight orchestrator owns the goal and state; specialist worker nodes do the actual work.

Everything runs on a shared, structured context object so no agent ever invents facts.

---

## 2. Layered architecture

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — Orchestrator (LangGraph graph + shared state) │
│  routes, holds state, decides checkpoints & stop cond.   │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — Worker agents (nodes)                         │
│  Researcher · Strategist · Writer · Voice · Critic       │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 0 — Shared context / grounding                   │
│  parsed career history · JD · company facts · prefs     │
│  Truthfulness guardrail reads from here                 │
└─────────────────────────────────────────────────────────┘
```

### Layer 0 — Context / Grounding (built once, read by all)
Parse and normalize before any generation happens:
- **Career history** → structured JSON: roles, achievements (each with a metric where possible), skills, dates.
- **Job description** → requirements, keywords, seniority, implicit priorities.
- **Company facts** → mission, values, recent news, product (from research node or user-supplied).
- **User preferences** → tone (formal ↔ warm), length cap, hard "do-not-say" list, writing-style sample.

This is the single source of truth. The Truthfulness agent later validates every claim against it.

### Layer 1 — Orchestrator
A LangGraph `StateGraph`. It does **not** write prose. It:
- routes state between worker nodes,
- evaluates the Critic's score against a threshold,
- decides whether to loop, stop, or **interrupt** for a human checkpoint,
- merges worker outputs into the final letter.

### Layer 2 — Worker agents
| Agent | Job | Key output |
|---|---|---|
| **Company Researcher** | Gather mission, values, recent news, role emphasis | `company_facts` |
| **Strategist (Angle)** | Pick the 2–3 strongest candidate↔role connection points ("why you / why them") | `thesis` (ranked hooks) |
| **Narrative Writer** | Draft the letter around the thesis | `draft` |
| **Voice/Style** | Match tone, user's writing style, enforce length | `styled_draft` |
| **Critic** | Score against JD + flag *generic* sentences; return actionable fixes | `score` + `critiques[]` |
| **Truthfulness** | Reject any claim not traceable to Layer 0 | `pass/fail` + violations |

Decoupling the **Strategist** from the **Writer** is the single most important design choice — it's what prevents generic letters, because the "what to say" is decided and (optionally) approved before a word of prose exists.

---

## 3. Control flow (LangGraph graph)

```
      ┌──────────────┐
      │  ingest       │  build Layer 0 context
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │  research     │  Company Researcher
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │  strategize   │  Strategist → thesis
      └──────┬───────┘
             ▼
      ◇ CHECKPOINT 1 ◇  (semi-auto: pause only if low confidence
             │           OR user enabled "approve angle")
             ▼
      ┌──────────────┐
      │  write        │  Narrative Writer → draft
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │  style        │  Voice/Style → styled_draft
      └──────┬───────┘
             ▼
      ┌──────────────┐
      │  critique     │  Critic + Truthfulness (parallel fan-out)
      └──────┬───────┘
             ▼
        ◇ decision ◇
     score ≥ threshold  &&  truthful?
        │ yes                 │ no
        ▼                     ▼
   ┌─────────┐          loop back to write
   │ CHECKPT │          (max 2–3 cycles, then
   │   2      │           force CHECKPOINT 2)
   └────┬────┘
        ▼
     FINAL LETTER
```

### Semi-auto checkpoints (only two, kept minimal)
1. **After Strategist** — approve/edit the *angle* before prose is written. Cheapest place to correct direction. Auto-skipped when the Strategist's confidence is high; always shown if the user toggles "review angle."
2. **Before finalize** — if the Critic loop hits its cap without clearing the threshold, or the Truthfulness agent flags a violation, surface to the user rather than shipping a weak/false letter.

Everything else runs automatically. This matches "semi-auto: some checkpoints if needed."

### The refinement loop
Writer → Critic scores → if below threshold, feed `critiques[]` back into Writer → repeat. Cap at 2–3 iterations to bound latency and cost. This iterative scoring loop is what modern LangGraph implementations use to beat one-shot generation.

---

## 4. LangGraph implementation notes (design-level)

- **State object** (`TypedDict`): `context`, `company_facts`, `thesis`, `draft`, `styled_draft`, `score`, `critiques`, `iteration`, `truthful`. Nodes read/return partial state; LangGraph merges it.
- **Nodes** = the six worker agents + `ingest`. Each is a function `(state) -> partial_state`.
- **Conditional edges** implement the score decision and loop cap.
- **`interrupt()`** (LangGraph's human-in-the-loop primitive) implements both checkpoints — the graph pauses, surfaces state to the UI, resumes on user input.
- **Checkpointer** (e.g. `MemorySaver` / a DB saver) persists state across interrupts so a user can approve an angle hours later.
- **Parallel fan-out**: run Critic and Truthfulness concurrently, then join.
- **Model routing**: cheap/fast model for research + style, stronger model for Strategist + Writer + Critic. The orchestrator assigns per node.
- **Optional RAG layer**: retrieve over a store of the user's real past projects so the Writer can pull in relevant true achievements the base resume omits — richer letters, still grounded.

---

## 5. Frontend / UI mapping

Every worker agent gets a user-facing surface. If an agent has no UI affordance, question whether it deserves to be its own agent.

1. **Live pipeline view** — show stages (Research → Strategize → Write → Style → Critique) lighting up in sequence. Fills wait time and builds trust by exposing the reasoning.
2. **Angle approval card (Checkpoint 1)** — display the Strategist's 2–3 ranked hooks as editable cards; user can reorder, edit, or reject before prose is written.
3. **Personalization dial** — a conservative ↔ bold slider mapped to how aggressively the Strategist reaches for distinctive hooks.
4. **Streaming draft** — Writer output appears token-by-token, section by section.
5. **Critic panel** — match score, a "genericness" flag list (click a flagged sentence to jump to it), length indicator.
6. **Provenance tooltips** — hover any claim → see which real experience it came from. This surfaces the Truthfulness layer directly.
7. **Re-run at any layer** — buttons like "try a warmer tone" (re-run Style only) or "different angle" (re-run Strategist only), instead of regenerating the whole letter. Maps 1:1 to the modular node design.
8. **Tone/length controls** — feed the Voice agent's preferences without a new generation.

---

## 6. Open questions to resolve next
- Source of company facts: live web search node, user paste, or a company-info connector?
- Where does the writing-style sample come from (upload past letters, or a style questionnaire)?
- Score threshold + max loop count — tune empirically.
- Storage: where does the persistent checkpointer live (local vs. hosted DB)?

---

## References
- Multi-agent orchestrator-worker patterns (2026): https://www.digitalapplied.com/blog/agent-architecture-patterns-taxonomy-2026 · https://www.paiteq.com/blog/multi-agent-orchestration-patterns/ · https://www.truefoundry.com/blog/multi-agent-architecture
- Career-aware tailoring via multi-source RAG (LangGraph-style pipeline): https://arxiv.org/pdf/2605.05257
- Autonomous multi-agent resume/letter systems: https://medium.com/@dekhane.aishwarya/architecting-an-autonomous-multi-agent-system-for-resume-analysis-and-optimization-1cb5887993da
