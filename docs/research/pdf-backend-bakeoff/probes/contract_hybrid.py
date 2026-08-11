"""The ENRICHED contract: an ordered character stream with geometry, not a glyph bag.

`contract.PdfPage` carries glyphs as an unordered set of positioned marks, on the
principle that ordering and spacing are generic PDF-layout decisions the consuming
project should make for itself. This contract tests the opposite principle: that
ordering and word spacing are decisions the PDF ENGINE is better positioned to make,
because it can see the encoding and text-object structure that positions alone do not
carry, and that DeltaTrack's job begins at GPO/legislative interpretation.

The two differences from `contract.Glyph` are the whole experiment:

  1. `chars` is ORDERED. Index order is the engine's reading order, and it is
     load-bearing rather than incidental.
  2. A char may be GENERATED -- synthesised by the engine rather than read from the
     content stream. A generated char has a real codepoint and a real baseline and
     NOTHING ELSE: `x0`, `x1`, `size` and the vertical box are None, because measuring
     them found only placeholders (zero-area box, identity matrix, size 1.0, empty font
     name). They are None rather than filled so that any downstream use of a generated
     char's geometry fails loudly instead of quietly consuming a placeholder.

A backend that cannot supply the ordering or the generated flag cannot emit this
contract, which is the point: it makes the dependency explicit rather than implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

CHAR_FIELDS = (
    "unicode",
    "generated",  # engine-synthesised (word space, line break), not read from the page
    "baseline",  # y of FPDFText_GetCharOrigin; PRESENT for generated chars
    "x0",  # None when generated
    "x1",  # None when generated
    "size",  # None when generated
    "vbox",  # (bottom, top) or None when generated
    "font",  # "" when generated or unresolved
    "upright",
)
CP, GEN, BASELINE, X0, X1, SIZE, VBOX, FONT, UPRIGHT = range(9)

HybridChar = tuple[int, bool, float | None, float | None, float | None, float | None, tuple | None, str, bool]


@dataclass
class HybridPage:
    page_number: int  # 1-based
    width: float
    height: float
    chars: list[HybridChar]
