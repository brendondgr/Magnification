"""
Compile a generated LaTeX document to a PDF, with a small on-disk cache.

The generation graphs persist LaTeX (``agents/latex.py``); the Application-Mode review pane wants a
rendered PDF. This module bridges the two: it runs ``pdflatex`` on the stored source and caches the
result under the shared data root, keyed by a hash of the exact source, so repeated previews of an
unchanged draft never recompile and a refine (new source → new hash) recompiles once.

``pdflatex`` runs with shell-escape **disabled** and a wall-clock timeout, in a throwaway working
directory whose aux files are discarded. A compile failure raises :class:`LatexCompileError` with
the tail of the TeX log so the API can surface a useful message instead of a blank pane.
"""

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger

from .paths import get_project_root

_CACHE_DIR = get_project_root() / "data" / "generated_pdfs"
_ENGINE = "pdflatex"
_TIMEOUT_SEC = 40


class LatexCompileError(RuntimeError):
    """Raised when ``pdflatex`` fails or is unavailable. ``log`` holds the tail of the TeX log."""

    def __init__(self, message: str, log: str = ""):
        super().__init__(message)
        self.log = log


def _source_hash(tex: str) -> str:
    return hashlib.sha1(tex.encode("utf-8", "replace")).hexdigest()[:12]


def _cache_path(doc_id: int, digest: str) -> Path:
    return _CACHE_DIR / f"doc_{doc_id}_{digest}.pdf"


def _prune_stale(doc_id: int, keep: Path) -> None:
    """Drop older PDFs for this doc (previous revisions) so the cache stays one-file-per-doc."""
    for old in _CACHE_DIR.glob(f"doc_{doc_id}_*.pdf"):
        if old != keep:
            try:
                old.unlink()
            except OSError:
                pass


def _log_tail(work: Path, stdout: str, limit: int = 1600) -> str:
    log_file = work / "doc.log"
    text = ""
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = stdout or ""
    return text[-limit:]


def compile_pdf(doc_id: int, tex: str, *, force: bool = False) -> Path:
    """Return the path to the compiled PDF for ``tex``, compiling (and caching) if needed.

    Cache hit (same source hash) returns instantly. ``force`` recompiles even on a hit. Raises
    :class:`LatexCompileError` if the engine is missing or the source fails to compile.
    """
    if not (tex or "").strip():
        raise LatexCompileError("Document has no LaTeX source to compile.")
    if shutil.which(_ENGINE) is None:
        raise LatexCompileError(f"{_ENGINE} is not installed; cannot render a PDF preview.")

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = _source_hash(tex)
    out = _cache_path(doc_id, digest)
    if out.exists() and not force:
        return out

    with tempfile.TemporaryDirectory(prefix="mag_tex_") as tmp:
        work = Path(tmp)
        (work / "doc.tex").write_text(tex, encoding="utf-8")
        try:
            proc = subprocess.run(
                [_ENGINE, "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", "doc.tex"],
                cwd=work, capture_output=True, text=True, timeout=_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            raise LatexCompileError(f"PDF compile timed out after {_TIMEOUT_SEC}s.")

        pdf = work / "doc.pdf"
        if proc.returncode != 0 or not pdf.exists():
            tail = _log_tail(work, proc.stdout)
            logger.warning(f"pdflatex failed for doc {doc_id} (rc={proc.returncode}).")
            raise LatexCompileError("LaTeX failed to compile.", log=tail)

        shutil.move(str(pdf), str(out))

    _prune_stale(doc_id, keep=out)
    return out


def cached_pdf(doc_id: int, tex: str) -> Optional[Path]:
    """Return the cached PDF path if one exists for this exact source, else ``None`` (no compile)."""
    p = _cache_path(doc_id, _source_hash(tex))
    return p if p.exists() else None
