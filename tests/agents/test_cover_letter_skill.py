"""
Tests for the distilled cover-letter house-style module (``agents/cover_letter_skill.py``).

These lock the *content* of the Winning Formula and writing rules so a future edit that silently
drops a section (e.g. the two-paragraph value proposition or the quantify-achievements rule) fails
loudly. The prompt-wiring tests (``test_cover_letter_quality.py``) verify these actually reach the
LLM nodes; this file verifies the source-of-truth module itself.
"""

from utils.backend.agents import cover_letter_skill as skill


def test_winning_formula_has_all_four_parts():
    f = skill.WINNING_FORMULA.lower()
    assert "opening hook" in f
    assert "value proposition" in f
    assert "why this company" in f
    assert "strong close" in f
    # The value proposition is the two-paragraph body — the structural heart of the skill.
    assert "2 paragraph" in f


def test_writing_rules_cover_quantify_and_mistakes():
    r = skill.WRITING_RULES.lower()
    assert "quantify" in r
    assert "$2m" in r                      # a concrete quantified example survives edits
    assert "restate the résumé" in r or "restate the resume" in r
    assert "one page" in r
    assert "company name" in r             # the classic wrong-company mistake


def test_skill_guidance_composes_formula_and_rules():
    g = skill.skill_guidance()
    assert g.strip()
    assert skill.WINNING_FORMULA in g
    assert skill.WRITING_RULES in g
