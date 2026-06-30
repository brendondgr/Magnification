---
name: planner
description: Use this skill when the user asks to create, refine, or evaluate an implementation plan, roadmap, migration plan, or structured sequence of work before coding.
---

# Plan Creation

Use this skill to produce explicit, clear, and hierarchical implementation plans.

## Core Reference

Follow the planning format and quality rules in [planner.md](planner.md).

## When To Use

- The user asks to "create a plan", "plan this out", "make a roadmap", or "break this into steps".
- The user needs a staged implementation approach before code changes.
- The user asks for a plan that can be validated, committed, or handed off phase by phase.

## Output Expectations

- Use clean Markdown with an introduction, gaps and unanswered questions, hierarchical steps, and a deliverables table.
- Include concrete locations such as files, classes, functions, scripts, or directories where work will happen.
- State assumptions for simple gaps and explicitly mark complex unanswered questions that need human input.
- Include validation expectations and commit/push wording for each phase when the plan is meant to guide implementation work.
