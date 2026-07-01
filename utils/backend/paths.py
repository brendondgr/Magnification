"""
Shared project-root resolution for Magnification.

Every gitignored runtime file (the SQLite database, the JSON config files under
``config/``) must live in exactly one place, shared by the main checkout and every
git worktree. Resolving the project root as a plain `__file__`-relative path breaks
this: git worktrees are separate directories on disk that do NOT share gitignored /
untracked files, so a `__file__`-relative root computed from inside a worktree points
at that worktree's own (empty) `data/`/`config/` instead of the main checkout's.

`get_project_root()` fixes this by resolving the git *common* directory (shared by the
main checkout and every worktree it owns) and returning its parent. When git is
unavailable (e.g. a non-git/packaged install), it falls back to a `__file__`-relative
computation identical to the old per-module logic.
"""

import subprocess
from functools import lru_cache
from pathlib import Path

# This file lives at utils/backend/paths.py; parents[2] is the project root.
_FALLBACK_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Return the single project root shared by the main checkout and all worktrees."""
    this_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=this_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        common_dir = (this_dir / result.stdout.strip()).resolve()
        if common_dir.is_dir() and common_dir.parent.is_dir():
            return common_dir.parent
    except (OSError, subprocess.SubprocessError):
        pass
    return _FALLBACK_ROOT
