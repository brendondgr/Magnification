"""
Unit tests for the LaTeX assembly layer (``agents/latex.py``) and the compiler
(``pdf_compile.py``).

The escaping/builder tests are pure and always run. The compile tests are guarded by
``pdflatex`` being installed (skipped otherwise) and assert that our builders produce a document
that actually compiles — including the adversarial characters an LLM routinely emits (``& % _ $``,
``C++``) and the ``[Your Name]`` signature line that once broke the ``\\`` line-break.
"""

import shutil

import pytest

from utils.backend.agents import latex

_HAS_PDFLATEX = shutil.which("pdflatex") is not None
_needs_tex = pytest.mark.skipif(not _HAS_PDFLATEX, reason="pdflatex not installed")


# ==================== escaping ====================

def test_escape_latex_specials():
    out = latex.escape_latex("Cut cost 30% & scale R&D $5 for a_b #1 {x}")
    for bad in ("&", "%", "$", "#", "_", "{", "}"):
        # every special must be backslash-escaped (never bare)
        assert f" {bad}" not in out.replace("\\" + bad, "")
    assert r"\%" in out and r"\&" in out and r"\_" in out


def test_escape_latex_preserves_paragraphs_collapses_wrap():
    out = latex.escape_latex("line one\nwrapped\n\npara two")
    assert "\n\n" in out                    # paragraph break kept
    assert "line one wrapped" in out        # single newline collapsed to a space


def test_escape_latex_linebreaks_are_bracket_safe():
    # A hard break followed by a "[...]" line must NOT let \\ eat it as an optional arg.
    out = latex.escape_latex("Sincerely,\n[Your Name]", linebreaks=True)
    assert r"\\{}" in out


def test_md_to_latex_bullets_and_headings():
    out = latex.md_to_latex("## Role\n- did a thing\n- **bold** thing\n\nprose")
    assert r"\begin{itemize}" in out and r"\item" in out
    assert r"\textbf{" in out


def test_none_is_safe():
    assert latex.escape_latex(None) == ""
    assert latex.md_to_latex(None) == ""


# ==================== builders ====================

def test_build_cover_letter_has_document_scaffold():
    tex = latex.build_cover_letter_tex({
        "candidate": {"name": "Jane Doe", "contact": "jane@x.com"},
        "styled_draft": "Dear Team,\n\nHello.\n\nSincerely,\nJane Doe",
    })
    assert tex.startswith("\\documentclass")
    assert "\\begin{document}" in tex and "\\end{document}" in tex
    assert "Jane Doe" in tex


def test_build_resume_lays_out_sections():
    tex = latex.build_resume_tex({
        "candidate": {"name": "Jane Doe"},
        "resume_slots": {"candidate_name": "Jane Doe", "contact_line": "x@y.com",
                         "summary": "Engineer.", "experience": "- Built things",
                         "skills": "Python, C++", "education": ""},
    })
    assert "\\section*{Summary}" in tex
    assert "\\section*{Experience}" in tex
    assert "\\section*{Education}" not in tex   # empty section omitted


def test_placeholder_name_not_rendered_as_header():
    # "[Your Name]" / "default" are placeholders → no bold header line for them.
    tex = latex.build_cover_letter_tex({"candidate": {"name": "[Your Name]"},
                                        "styled_draft": "Dear Team,\n\nHi."})
    assert r"\bfseries [Your Name]" not in tex


# ==================== compile (guarded) ====================

def _compile_ok(tmp_path, tex, name):
    import subprocess
    (tmp_path / f"{name}.tex").write_text(tex, encoding="utf-8")
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-no-shell-escape", f"{name}.tex"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60)
    return (tmp_path / f"{name}.pdf").exists(), proc.stdout


@_needs_tex
def test_cover_letter_compiles_with_adversarial_content(tmp_path):
    tex = latex.build_cover_letter_tex({
        "candidate": {"name": "Jane Doe", "contact": "jane@x.com\n(555) 100-2000"},
        "styled_draft": "Dear Hiring Manager,\n\nI cut cost 30% at R&D Labs & shipped C++ "
                        "(100% uptime) for team_x.\n\nSincerely,\n[Your Name]",
    })
    ok, log = _compile_ok(tmp_path, tex, "cover")
    assert ok, log[-1500:]


@_needs_tex
def test_resume_compiles_with_bullets_and_symbols(tmp_path):
    tex = latex.build_resume_tex({
        "candidate": {"name": "Jane Doe"},
        "resume_slots": {"candidate_name": "Jane Doe", "contact_line": "x@y.com | Austin, TX",
                         "summary": "5+ yrs, 99.9% uptime.",
                         "experience": "## Acme\n- Cut spend 30% via C_opt & caching\n- **PyTorch** at scale",
                         "skills": "Python, C++, R&D", "education": "- B.S. CS"},
    })
    ok, log = _compile_ok(tmp_path, tex, "resume")
    assert ok, log[-1500:]


@_needs_tex
def test_compile_pdf_caches_and_errors(tmp_path, monkeypatch):
    from utils.backend import pdf_compile
    monkeypatch.setattr(pdf_compile, "_CACHE_DIR", tmp_path)
    tex = latex.build_cover_letter_tex({"candidate": {"name": "Jane Doe"},
                                        "styled_draft": "Dear Team,\n\nHello.\n\nBest,\nJane"})
    p1 = pdf_compile.compile_pdf(123, tex)
    assert p1.exists() and p1.read_bytes()[:5] == b"%PDF-"
    # Same source → cache hit returns the same path.
    assert pdf_compile.compile_pdf(123, tex) == p1
    # Broken LaTeX raises with a log tail.
    with pytest.raises(pdf_compile.LatexCompileError):
        pdf_compile.compile_pdf(124, "\\documentclass{article}\\begin{document}\\undefinedcmd")
