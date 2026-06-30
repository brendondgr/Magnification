"""Lightweight verification that the docs/ source-of-truth and agent pointer
files are consistent.

Run: ``uv run pytest tests/docs/test_skill_pointers.py``

These tests do not import the application; they only assert that the
initialization scaffolding (canonical docs, skills, and agent pointers) exists
and that every pointer references a real canonical target.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

SKILLS = [
    "global-project-rules",
    "planner",
    "repository-structure",
    "website-architecture",
    "accessibility-mobile",
]

CANONICAL_DOCS = [
    "documentation.md",
    "structure.md",
    "workflow.md",
    "checklist.md",
    "architecture.md",
    "routes.md",
    "api-contract.md",
    "component-map.md",
    "data-flow.md",
    "deployment.md",
    "design-system.md",
]

GLOBAL_RULES = "docs/skills/global-project-rules/SKILL.md"


@pytest.mark.parametrize("doc", CANONICAL_DOCS)
def test_canonical_doc_exists(doc: str) -> None:
    path = ROOT / "docs" / doc
    assert path.is_file(), f"missing canonical doc: docs/{doc}"
    assert path.read_text(encoding="utf-8").strip(), f"empty canonical doc: docs/{doc}"


@pytest.mark.parametrize("skill", SKILLS)
def test_canonical_skill_exists(skill: str) -> None:
    skill_md = ROOT / "docs" / "skills" / skill / "SKILL.md"
    assert skill_md.is_file(), f"missing canonical skill: {skill}"
    text = skill_md.read_text(encoding="utf-8")
    # frontmatter name must match the folder name
    assert f"name: {skill}" in text, f"frontmatter name mismatch in {skill}/SKILL.md"


def test_plans_dir_exists() -> None:
    assert (ROOT / "docs" / "plans").is_dir()


# Pointer files per tool. Cursor uses flat .mdc files.
@pytest.mark.parametrize("skill", SKILLS)
def test_claude_pointer(skill: str) -> None:
    _assert_pointer(ROOT / ".claude" / "skills" / skill / "SKILL.md")


@pytest.mark.parametrize("skill", SKILLS)
def test_codex_pointer(skill: str) -> None:
    _assert_pointer(ROOT / ".agents" / "skills" / skill / "SKILL.md")


@pytest.mark.parametrize("skill", SKILLS)
def test_cursor_pointer(skill: str) -> None:
    _assert_pointer(ROOT / ".cursor" / "rules" / f"{skill}.mdc")


def _assert_pointer(path: Path) -> None:
    assert path.is_file(), f"missing pointer file: {path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8")
    assert GLOBAL_RULES in text, f"pointer does not reference global rules: {path.relative_to(ROOT)}"


@pytest.mark.parametrize("skill", SKILLS)
def test_pointers_reference_real_canonical_skill(skill: str) -> None:
    target = f"docs/skills/{skill}/SKILL.md"
    assert (ROOT / target).is_file(), f"canonical target missing for {skill}"
