---
name: portfolio-readme
description: Creates and audits GitHub portfolio material — profile READMEs, per-project READMEs, and repo pinning/organization strategy — optimized for how recruiters and technical reviewers actually evaluate GitHub profiles. Use this skill whenever the user asks to write, improve, or review a README; asks how to make a repo or profile "look good," "portfolio-ready," or "hireable"; asks what to pin; asks for help before a job/internship/PhD-internship application; or mentions showcasing projects to recruiters, hiring managers, or research reviewers. Trigger even if the user just says "clean up this repo" or "write docs for this project" — README quality is almost always part of what they need. Has two modes: standard (SWE/new-grad hiring) and research (PhD/research-lab internships, e.g. applying to industry research labs) — ask or infer which applies before writing.
---

# Portfolio README Skill

Helps produce GitHub portfolio material that actually gets read: profile READMEs, project READMEs, and repo curation/pinning strategy. Optimized against how recruiters and technical reviewers actually behave — they spend 30–90 seconds per profile and 30 seconds to 2 minutes per repo, so structure and scannability matter more than exhaustiveness.

## Step 0: Determine the track

Two audiences need different treatment. Ask the user, or infer from context (target roles, project type, CV signals):

- **Standard track** — SWE / new-grad / bootcamp hiring. Optimize for: live demos, clean UX, breadth-with-depth-in-2-3-stacks, deployment proof.
- **Research track** — PhD / research-lab internships (e.g. applying to AI research labs, applied science roles). Optimize for: novelty/rigor framing, architecture over UI polish, a clear throughline across multiple projects (a "thesis"), and literature-gap positioning.

If ambiguous, ask one question before proceeding: "Is this for general software engineering roles, or for research-track positions (PhD internships, research labs)?" Don't guess silently if the answer would change the README structure significantly.

Load `references/research-portfolio-guide.md` for track-specific adjustments when research track applies.

## Step 1: Gather project context

Before writing anything, get (from the repo itself if possible — read package.json/pyproject.toml/requirements.txt, scan file structure, check existing commits/docstrings — otherwise ask):

- What the project does and what problem it solves or concept it demonstrates
- Tech stack (be specific — "React + Supabase, 400 stars, used by 3 companies" beats "React")
- Whether it's deployed / has a live demo or needs one
- 1–2 genuine technical challenges solved (not generic ones)
- For research track: what specific gap, benchmark, or prior-work limitation this addresses

Don't fabricate metrics, stars, deployment status, or challenges. If the user hasn't given you real details, ask rather than invent plausible-sounding ones.

## Step 2: Write the project README

Use `references/project-readme-template.md` as the structural template. Core sections, in order:

1. **One-paragraph overview** — what it is and why it exists
2. **Tech stack** — specific, not exhaustive
3. **Live demo link** (if applicable) — put this near the top, not buried
4. **Screenshot or GIF** (if UI-relevant) — visual proof beats a code walkthrough for non-technical reviewers
5. **Setup/run instructions** — real, tested steps including env vars
6. **Key features** (3–5, not a full changelog)
7. **Challenges & design decisions** — 1–2 genuine ones, shows judgment not just execution
8. **Architecture note or diagram** (research track: prioritize this over screenshots)
9. Optional: roadmap/future work — signals forward thinking, keep short

Keep it scannable: short paragraphs, headers, whitespace. Avoid reconstructing the whole codebase in prose — a reviewer wants orientation, not a transcript.

## Step 3: Write or update the profile README (if requested)

Use `references/profile-readme-template.md`. This is the repo named exactly after the GitHub username — GitHub renders its README as a banner on the profile page. Keep this one tight:

- One-line bio: what they actually build, not a job title
- 3–5 core technologies (not a exhaustive list — more than that reads as breadth-without-depth)
- Pinned repos (3–6) each with a real one-line description, not a restated title
- One current-project line — signals momentum
- One outbound link, chosen deliberately (personal site > scattered links)
- Optional: single stats widget. Skip animated badge carousels — they read as noise.

## Step 4: Pinning and repo curation advice

When asked to review a whole profile/repo list:

- Recommend pinning 3–6 repos max, chosen for variety of skill + relevance to target roles, not just "best" in isolation
- Flag anything that looks like an unfinished tutorial clone, empty scaffold, or assignment-named repo (`lab-3`, `hw2`) for archiving or making private — these actively hurt more than an absent repo would
- Check commit cadence only if asked — steady weekly activity reads better than sporadic bursts, but don't fabricate a commit history recommendation without knowing their actual pattern
- For research track: recommend leading with the 1–2 repos that form a coherent narrative/thesis (e.g., a construction pipeline + a querying/analysis layer) over pinning every active project with equal weight

## Output

- If working inside a repo (Claude Code / Codex CLI with file access), write the README directly to the file and show a summary of what changed.
- If asked for advice only, give the structured recommendation in chat without necessarily writing a file.
- Never invent live demo links, star counts, or user numbers — leave a placeholder and flag it clearly if the user hasn't supplied real data.
