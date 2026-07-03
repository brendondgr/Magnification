# Research-Track Portfolio Adjustments

For portfolios targeting PhD-adjacent research internships (industry AI research labs, applied science roles) rather than general SWE hiring. Layer these adjustments on top of the standard templates — don't replace them.

## The core difference

SWE hiring pipelines optimize for: can this person ship production code fast, cleanly, and independently. Research-track reviewers optimize for: does this person understand why the problem is hard, can they position their work against existing literature, and is there a coherent line of inquiry across their work (not just a pile of impressive but disconnected projects).

This changes what to lead with.

## Pick a thesis, not a highlight reel

If there are multiple active projects, don't pin them with equal weight. Identify which 1–2 compose into a coherent narrative (e.g., a construction/pipeline layer + a querying/analysis layer that operate on the same underlying problem) and lead with those. A reviewer should see the throughline in under a minute. Everything else is secondary evidence of range, not the headline.

State the throughline explicitly in the profile README or portfolio site, in one sentence: "X builds the graphs that Y queries" is more useful to a reviewer than four unconnected one-liners.

## Frame the gap, not just the build

For each lead project, the README's overview paragraph should answer: *what existing approach does this improve on, and why does that gap matter?* This is different from a SWE README, which mainly answers *what does this do and how do I run it.*

Concretely: instead of "A knowledge graph system using Neo4j and Gremlin," write something like "Live cross-engine querying across property-graph and RDF-style backends — most existing federation work assumes a single engine or requires offline translation." One sentence is enough; the dissertation/paper carries the depth.

## Architecture over UI

A reviewer evaluating research potential will weight a clear system diagram or pipeline breakdown higher than a polished screenshot. If the project has a non-trivial pipeline (multi-stage processing, agentic orchestration, multi-backend writes, etc.), prioritize a diagram or a labeled component list over a UI walkthrough. Visual design matters less than functionality and code quality for this audience — a well-documented backend can outweigh a beautiful but shallow frontend.

## Benchmark and literature grounding

Where relevant, name the benchmark, dataset, or literature gap the project positions against (e.g., a named benchmark family, a taxonomy from prior work). This signals the person reads the field, not just the docs for their chosen framework. Keep it to one clause — this isn't the place for a lit review, just a pointer that shows awareness.

## The portfolio site vs. GitHub split

For research-track applicants, a personal portfolio site (Astro, Jekyll, whatever) carries more narrative weight than the GitHub profile README, because it's the layer where the cross-project thesis gets explained in prose that individual repo READMEs can't fully carry. GitHub should stay tight and point outward; the portfolio site is where the "here's my research direction and how these projects compose into it" story lives.

## What NOT to over-optimize for

- Deployment/live-demo pressure is lower for research-track work — a rigorously documented pipeline that isn't deployed is fine; don't manufacture a demo that adds no signal.
- Stack breadth matters less than depth in the specific techniques relevant to the target lab (e.g., agentic orchestration, retrieval methods, graph/ML infra) — resist the urge to list every tool touched.
