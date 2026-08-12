"""Shared text normalization for recall tests.

Comparison across recall tests is whitespace-normalized substring matching:
permissive on purpose, since the goal is recall (did the text survive?), not
byte-exact reproduction.
"""

from __future__ import annotations

import re
import unicodedata

from deltatrack.parsers.pdf_text import normalize_glyphs

_WS = re.compile(r"\s+")
# Real compounds like `Child-Rescue` that wrap at a line boundary surface as
# `Child- Rescue` after extraction. The `parse_lines` lowercase guard preserves
# the hyphen but can't tell a soft wrap from a compound at the wrap point, so a
# space leaks in. Positional disambiguation was attempted (see git history) but
# couldn't reliably distinguish all-caps soft hyphens from compounds. Collapse
# the artifact at compare-time only — the diff layer is unaffected.
_WRAPPED_COMPOUND = re.compile(r"(\w)- (\w)")


def normalize_for_recall(text: str) -> str:
    """Glyph-normalize, collapse whitespace, and rejoin wrapped compounds."""
    canonical = _WS.sub(" ", normalize_glyphs(text)).strip()
    return _WRAPPED_COMPOUND.sub(r"\1-\2", canonical)


# Cross-format canonicalization, for comparing bill XML prose against extracted PDF
# text (test_pdf_xml_prose_recall.py). The two formats agree on the words and disagree
# on everything around them, so each rule below erases one such disagreement. All four
# are safe for a RECALL question -- none of them can hide a dropped or altered word,
# which is the only failure this comparison exists to catch.
#
#  - Marks: `Moise` for `Moïse`. GPO's XML carries a precomposed accented letter; the
#    PDF renders the accent as a SEPARATE spacing character after the base letter, so
#    `Guantánamo` extracts as `Guanta´namo` (U+00B4) and `Moïse` as `Moı¨se` (U+0131
#    U+00A8). Decomposing and dropping combining marks handles the XML side; the PDF
#    side needs the spacing diacritics dropped and dotless i/j restored. The extracted
#    text keeping that broken spelling is a real defect in its own right -- it is what
#    a reader sees and searches -- but it is a rendering-fidelity bug tracked
#    separately as #537, not a recall failure, so it is folded away here. Note that
#    folding it here means nothing in the suite will surface it again; #537 is the
#    only place it lives.
#  - Quotes: XML wraps quoted terms in `<quote>` elements that itertext() renders as
#    bare quote characters, in positions the PDF sets differently.
#  - Hyphens: three unrelated artifacts collapse into one rule -- a soft wrap in the
#    PDF (`appro- priations`), spaced hyphens in XML citations (`97 - 377`), and
#    hyphens the two formats simply disagree about (`else-where` vs `elsewhere`, an
#    XML-side artifact in 114-hr-2029). Removing hyphens entirely settles all three.
#    A hyphen genuinely lost by extraction is therefore invisible here; that is a
#    rendering-fidelity question, tracked by the golden prints, not a recall one.
#  - Case: an amendment instruction quoting a HEADING carries it in the XML's title
#    case and in the PDF's small caps, so `striking joint ventures` reads as
#    `striking JOINT VENTURES` (119-hr-1, the whole of its residue). Matching modulo
#    case is what test_pdf_division_recall.py already does with division names.
#  - Space around punctuation: an artifact of joining XML inline elements, e.g.
#    `Provided , That` for the PDF's `Provided, That`; and of a PDF line wrapping
#    after a slash, e.g. `Ill/ Injured` for `Ill/Injured`.
_MARKS = re.compile(r"[̀-ͯ]")
_SPACING_DIACRITICS = re.compile(r"[´¨`¯¸ˆ-˝]")
_DOTLESS = str.maketrans({"ı": "i", "ȷ": "j"})
_QUOTES = re.compile(r"[‘’“”\"']")
_HYPHENS = re.compile(r"\s*[-‐-―]\s*")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:)\]])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")
_SPACE_AROUND_SLASH = re.compile(r"\s*/\s*")


def normalize_for_cross_format(text: str) -> str:
    """Canonicalize XML prose and PDF text onto common ground for substring recall.

    Deliberately more aggressive than :func:`normalize_for_recall`, which compares
    extracted text against a hand-written fixture in the same conventions. Here the
    two sides come from different producers, so the punctuation, accent, and hyphen
    conventions must be erased before a substring test means anything. See the
    rule-by-rule rationale above.
    """
    canonical = _MARKS.sub("", unicodedata.normalize("NFD", normalize_for_recall(text)))
    canonical = _SPACING_DIACRITICS.sub("", canonical).translate(_DOTLESS)
    canonical = _HYPHENS.sub("", _QUOTES.sub("", canonical))
    canonical = _SPACE_AROUND_SLASH.sub("/", canonical)
    canonical = _SPACE_AFTER_OPEN.sub(r"\1", _SPACE_BEFORE_PUNCT.sub(r"\1", canonical))
    return _WS.sub(" ", canonical).strip().casefold()
