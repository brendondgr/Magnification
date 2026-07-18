"""
The cover-letter "house style" — a single runtime source of truth for how every generated
cover letter should be structured and written.

This module distills an external cover-letter Office Skill (the *Winning Formula* + its writing
rules) into compact prompt-ready constants. It is imported by ``agents/prompts.py`` and folded into
the strategize / write / critique system prompts, so the structure is enforced on **every**
generation — a first-pass letter and an Application-Mode refine/regenerate alike, regardless of
which template the user selected. Keeping the guidance here (not inline in each prompt) means all
consumers reference the same rules and the house style is edited in exactly one place.

Nothing here contradicts the existing anti-parroting / anti-AI-voice rules in ``prompts.py``; this
adds the missing *structure* and *quantification* discipline on top of them.
"""

# ==================== the Winning Formula (document structure) ====================

# The four-part structure every letter must follow. The Value Proposition is the body and carries
# the weight (two developed paragraphs); the other three are a paragraph each. This maps onto the
# seeded template slots as: hook → {{hook}}, value proposition → {{why_you}}, why-this-company →
# {{why_them}}, strong close → {{close}}.
WINNING_FORMULA = (
    "STRUCTURE — follow this four-part Winning Formula (one page, ~350 words, 3-4 paragraphs):\n"
    "1. OPENING HOOK (1 short paragraph): grab attention immediately and name the specific role. "
    "Lead with a concrete achievement, a genuine connection, or a referral — never 'I am writing "
    "to apply for...'. Show real, specific enthusiasm for THIS role, not a template opener.\n"
    "2. VALUE PROPOSITION (2 paragraphs — the core of the letter): match the candidate's real "
    "experience to what the role needs. Give specific, QUANTIFIED accomplishments (numbers, scale, "
    "outcomes) and show you understand the problems this team is solving. This is where most of the "
    "words go.\n"
    "3. WHY THIS COMPANY (1 paragraph): show genuine, researched interest in this specific "
    "employer — connect the candidate's stated values/goals to the company's work. Answer why HERE "
    "and why NOW, grounded only in what the candidate actually cares about.\n"
    "4. STRONG CLOSE (1 paragraph): restate interest, make a clear call to action (a conversation), "
    "and end with forward-looking enthusiasm — confident, not presumptuous."
)

# ==================== the writing rules ====================

WRITING_RULES = (
    "WRITING RULES:\n"
    "- QUANTIFY achievements: prefer 'grew sales 45% YoY, adding $2M' over 'increased sales'; "
    "'led a 12-person team across 3 time zones' over 'managed a team'. Use the candidate's REAL "
    "numbers only — never invent metrics.\n"
    "- Strong openers only: a concrete achievement, a genuine connection to the company's work, or "
    "a referral. Never open with 'I am writing to apply', 'I believe I would be a great fit', or "
    "'To whom it may concern'.\n"
    "- Show company research: reference something specific and real about the employer's work; do "
    "not fabricate news, funding, or product facts you cannot infer.\n"
    "- Avoid the classic mistakes: (a) do not just restate the résumé — add insight; (b) do not be "
    "generic — every line should be specific to this candidate and this role; (c) focus on what the "
    "candidate OFFERS, not what they want; (d) keep it to one page; (e) stay positive — no negative "
    "or apologetic framing; (f) never guess or misstate the company name."
)


def skill_guidance() -> str:
    """Return the composed house-style block for embedding in a generation prompt.

    A single compact string (formula + rules) so the strategize/write/critique prompts can all
    reference the same guidance. Non-empty by construction.
    """
    return WINNING_FORMULA + "\n\n" + WRITING_RULES
