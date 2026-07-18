"""
LaTeX assembly for generated documents (cover letter + résumé).

The graphs produce *substance* (styled letter prose, tailored résumé sections); this module wraps
that substance into a clean, ATS-friendly, **always-compilable** LaTeX document. The design bet
(mirroring the rest of the agent layer) is determinism over flair: rather than ask an LLM to emit
LaTeX — which routinely breaks on an unescaped ``& % _ $`` — the model writes plain prose and this
module escapes it and lays it out. Every builder therefore works fully offline and never raises on
adversarial content.

Only base + very common packages are used (``geometry``, ``titlesec``, ``enumitem``, ``parskip``,
``hyperref``, ``lmodern``), so ``pdflatex`` compiles without a network fetch.
"""

import re
from typing import Any, Dict, List

# ==================== escaping ====================

# Order matters: backslash first so we don't double-escape the replacements we introduce.
_ESCAPES = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
    ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
    ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}"),
]


def escape_latex(text: Any, *, linebreaks: bool = False) -> str:
    """Escape LaTeX specials in ``text``.

    Paragraph breaks (blank lines) are preserved. When ``linebreaks`` is True a single newline
    inside a paragraph becomes a ``\\\\`` hard break (used for contact / signature blocks); otherwise
    single newlines collapse to spaces (normal prose reflow).
    """
    s = "" if text is None else str(text)
    # Normalize newlines, then protect paragraph breaks with a sentinel while we escape.
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    paras = re.split(r"\n\s*\n", s)
    out_paras: List[str] = []
    for para in paras:
        chunk = para
        for a, b in _ESCAPES:
            chunk = chunk.replace(a, b)
        if linebreaks:
            # ``\\{}`` not ``\\``: the trailing empty group stops LaTeX from reading a following
            # ``[...]`` (e.g. a "[Your Name]" signature line) as the break's optional length arg.
            chunk = chunk.replace("\n", " \\\\{}\n")
        else:
            chunk = re.sub(r"\s*\n\s*", " ", chunk)
        out_paras.append(chunk.strip())
    return "\n\n".join(p for p in out_paras if p)


# ==================== markdown → latex (small, conservative subset) ====================

_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _inline(text: str) -> str:
    """Escape a single line, then re-apply the **bold** whitelist (its markers survive escaping)."""
    esc = escape_latex(text)
    return _BOLD_RE.sub(lambda m: r"\textbf{" + m.group(1) + "}", esc)


def md_to_latex(text: str) -> str:
    """Convert the small Markdown subset our nodes emit (headings, ``-`` bullets, ``**bold**``,
    blank-line paragraphs) into LaTeX. Anything unrecognized is escaped as a paragraph."""
    lines = ("" if text is None else str(text)).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: List[str] = []
    buf: List[str] = []          # pending prose lines → one paragraph
    bullets: List[str] = []      # pending list items

    def flush_prose():
        if buf:
            blocks.append(_inline(" ".join(buf).strip()))
            buf.clear()

    def flush_bullets():
        if bullets:
            items = "\n".join(r"  \item " + b for b in bullets)
            blocks.append("\\begin{itemize}\n" + items + "\n\\end{itemize}")
            bullets.clear()

    for line in lines:
        if not line.strip():
            flush_prose(); flush_bullets(); continue
        mb = _BULLET_RE.match(line)
        mh = _HEADING_RE.match(line)
        if mb:
            flush_prose(); bullets.append(_inline(mb.group(1).strip()))
        elif mh:
            flush_prose(); flush_bullets()
            blocks.append(r"\textbf{" + _inline(mh.group(1).strip()) + r"}\par")
        else:
            flush_bullets(); buf.append(line.strip())
    flush_prose(); flush_bullets()
    return "\n\n".join(b for b in blocks if b)


# ==================== document builders ====================

_PLACEHOLDER_NAMES = {"", "[your name]", "default"}


def _clean_name(state: Dict[str, Any]) -> str:
    name = ((state.get("candidate") or {}).get("name") or "").strip()
    return "" if name.lower() in _PLACEHOLDER_NAMES else name


_COVER_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{parskip}
\usepackage{microtype}
\usepackage[hidelinks]{hyperref}
\setlength{\parskip}{0.7em}
\pagestyle{empty}
\begin{document}
"""


def build_cover_letter_tex(state: Dict[str, Any]) -> str:
    """Wrap the styled letter prose into a compilable single-column letter."""
    body_text = (state.get("smoothed_draft") or state.get("styled_draft")
                 or state.get("draft") or "")
    name = _clean_name(state)
    contact = ((state.get("candidate") or {}).get("contact") or "").strip()

    parts = [_COVER_PREAMBLE]
    header = []
    if name:
        header.append(r"{\Large\bfseries " + escape_latex(name) + r"}")
    if contact:
        header.append(r"{\small " + escape_latex(contact, linebreaks=True) + r"}")
    if header:
        parts.append("\\noindent " + r"\\[2pt]".join(header) + "\n\n\\vspace{1.2em}\n")

    parts.append(escape_latex(body_text, linebreaks=True))
    parts.append("\n\\end{document}\n")
    return "".join(parts)


_RESUME_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[margin=0.75in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{parskip}
\usepackage[hidelinks]{hyperref}
\titleformat{\section}{\large\bfseries}{}{0em}{}[{\titlerule[0.8pt]}]
\titlespacing{\section}{0pt}{1.1em}{0.4em}
\setlist[itemize]{leftmargin=1.25em,itemsep=1pt,topsep=2pt,parsep=0pt}
\setlength{\parskip}{0.4em}
\pagestyle{empty}
\begin{document}
"""

# Which résumé slots hold free-form (possibly bulleted) blocks vs. a plain line.
_RESUME_SECTIONS = [("summary", "Summary", False), ("experience", "Experience", True),
                    ("skills", "Skills", False), ("education", "Education", True)]


def build_resume_tex(state: Dict[str, Any]) -> str:
    """Lay the tailored résumé slots into a clean single-column, ATS-friendly résumé."""
    slots = state.get("resume_slots") or {}
    name = _clean_name(state) or (slots.get("candidate_name") or "").strip()
    contact = (slots.get("contact_line") or "").strip()

    parts = [_RESUME_PREAMBLE, r"\begin{center}"]
    parts.append(r"{\LARGE\bfseries " + escape_latex(name or "Résumé") + r"}")
    if contact:
        parts.append(r"\\[3pt]{\small " + escape_latex(contact, linebreaks=True) + r"}")
    parts.append("\\end{center}\n\n")

    for key, heading, rich in _RESUME_SECTIONS:
        val = (slots.get(key) or "").strip()
        if not val:
            continue
        parts.append(r"\section*{" + heading + "}\n")
        parts.append((md_to_latex(val) if rich else escape_latex(val)) + "\n\n")

    parts.append("\\end{document}\n")
    return "".join(parts)


def build_tex(kind: str, state: Dict[str, Any]) -> str:
    """Dispatch to the right builder for a generation ``kind``."""
    return build_resume_tex(state) if kind == "resume" else build_cover_letter_tex(state)
