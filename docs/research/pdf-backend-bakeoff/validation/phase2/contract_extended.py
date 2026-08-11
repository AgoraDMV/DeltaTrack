"""The EXTENDED glyph contract: `contract.Glyph` plus two low-level facts.

`contract.PdfPage` carries glyphs as positioned marks: box, baseline, size, font, upright.
`validation/FINDINGS.md` §1 showed that the word-boundary decision the glyph seam gets
wrong is a deterministic function of two facts the contract does NOT carry, and that both
are facts rather than interpretations:

    origin_x    the PEN position of the character, not the left edge of its ink. The
                shipped `_SPACE_FACTOR` rule measures ink-edge to ink-edge, which is the
                wrong quantity: side bearings vary per glyph and per font.
    advance     the font's own advance width for this character at this size. This is a
                font METRIC and cannot be derived from an ink box at all.

Everything else is unchanged from `contract.Glyph`, deliberately, so that a difference in
results is attributable to the two added fields and nothing else.

WHY THIS IS STILL A NEUTRAL CONTRACT. Both fields are asked of each backend in its own
terms, and each backend answers from its own API (measured in `g03_backend_fields.py`,
by value rather than by field name):

    PDFium        FPDFText_GetCharOrigin      FPDFText_GetTextObject
                                              -> FPDFTextObj_GetFont
                                              -> FPDFFont_GetGlyphWidth
    pdfminer.six  LTChar.x0                   LTChar.width
    PyMuPDF       get_texttrace() origin      get_texttrace() advance box
    PDF.js        --                          --   (item granularity, ~13 chars per item)

No backend is asked to reproduce another's conventions, which is the property the
bake-off's design rule exists to protect and the property the hybrid contract gives up.

WHAT IS NOT CLAIMED. That three of four backends expose these fields does not make the
RULE that consumes them neutral. See `reconstruct_extended.py`: the spacing algorithm is
a port of PDFium's heuristic and is DeltaTrack's to own and maintain.
"""

from __future__ import annotations

from dataclasses import dataclass

# Field order is the wire format, as in contract.py. The two new fields are appended so
# an existing consumer that unpacks the first nine positions is unaffected.
GLYPH_FIELDS = (
    "unicode",
    "x0",
    "y0",
    "x1",
    "y1",
    "baseline",
    "font_size",
    "font_id",
    "upright",
    "origin_x",  # pen position, NOT the ink left edge
    "advance",  # font advance width at this size, in points; None when unavailable
)
CP, X0, Y0, X1, Y1, BASELINE, SIZE, FONT, UPRIGHT, ORIGIN_X, ADVANCE = range(11)

ExtGlyph = tuple[int, float, float, float, float, float, float, str, bool, float, float | None]


@dataclass
class ExtPdfPage:
    page_number: int  # 1-based
    width: float
    height: float
    glyphs: list[ExtGlyph]
