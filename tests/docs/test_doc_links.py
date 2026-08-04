"""Every relative path a Markdown doc points at must exist.

Stale docs usually rot one link at a time: a file gets renamed or deleted and the
references linger for months. This walks every tracked Markdown file and resolves
the repo-relative paths it mentions -- both Markdown links and inline `code`
spans that look like paths -- so a delete or rename fails here instead of
misleading the next reader.
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Docs under docs/plans/ are a historical record: they intentionally reference
# files that were later renamed or removed. Everything else must resolve.
SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", "logs", "data", "worktrees"}
SKIP_PREFIXES = ("docs/plans/",)

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Only code spans that look like a path (they contain a separator) are checked --
# a bare `models.py` is a module reference, not a link.
CODE_PATH = re.compile(
    r"`([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.(?:md|py|json|svg|png|toml|sh|service|timer|js|html))`"
)

# Paths that are created at runtime rather than committed, plus the brace-expansion
# shorthand the checklist uses to group a family of plans.
RUNTIME_PATHS = {"config/document_guidance.json"}


def _markdown_files():
    for path in sorted(PROJECT_ROOT.rglob("*.md")):
        rel = path.relative_to(PROJECT_ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if str(rel).startswith(SKIP_PREFIXES):
            continue
        yield rel


def _candidate_targets(text):
    for match in MD_LINK.finditer(text):
        yield match.group(1)
    for match in CODE_PATH.finditer(text):
        yield match.group(1)


def _resolvable(doc_rel, target):
    """Resolve a target against the doc's directory, the repo root, or as a path tail.

    Docs often name a file the way the code imports it -- `recommend/enrichment.py`
    rather than `utils/backend/recommend/enrichment.py`. A suffix match still fails
    when the file is renamed or deleted, which is what this test is for.
    """
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or target in RUNTIME_PATHS:
        return True
    if target.startswith(("http://", "https://", "mailto:", "<")):
        return True
    if "{" in target or "*" in target:  # brace/glob shorthand, not a real link
        return True
    if "/" not in target and "." not in target:  # prose or a template placeholder
        return True
    if (PROJECT_ROOT / doc_rel.parent / target).exists():
        return True
    if (PROJECT_ROOT / target).exists():
        return True
    return any(
        str(p.relative_to(PROJECT_ROOT)).endswith("/" + target)
        for p in PROJECT_ROOT.glob("**/" + Path(target).name)
        if not any(part in SKIP_DIRS for part in p.relative_to(PROJECT_ROOT).parts)
    )


@pytest.mark.parametrize("doc_rel", list(_markdown_files()), ids=str)
def test_doc_paths_resolve(doc_rel):
    text = (PROJECT_ROOT / doc_rel).read_text(encoding="utf-8")
    broken = sorted({t for t in _candidate_targets(text) if not _resolvable(doc_rel, t)})
    assert not broken, f"{doc_rel} references paths that do not exist: {broken}"
