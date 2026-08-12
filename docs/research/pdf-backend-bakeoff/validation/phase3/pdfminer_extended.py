"""Backend adapter: pdfminer.six emitting the EXTENDED glyph contract, from its OWN API.

A deliberate minimal edit of `probes/backends/pdfminer_backend.py`. Every rule is copied
byte-for-byte -- `laparams=None`, the `(cid:N)` -> U+FFFD collapse, the ligature split, the
subset-tag strip, `matrix[5]` as the baseline. Two fields are added and nothing else.

    origin_x   LTChar.x0
    advance    abs(LTChar.width)

WHY THOSE TWO, stated with the semantics `h01_advance_semantics.py` established from the
INSTALLED SOURCE rather than from the attribute names:

  `layout.py` builds the character box as `(0, descent+rise, self.adv, ...)` and then
  applies `self.matrix`. So the box is an ADVANCE BOX -- pdfminer never computes ink
  bounds at all -- and after the transform:

      x0     is the pen origin
      width  is the advance IN PAGE SPACE

  `LTChar.adv` is `textwidth * fontsize * scaling`, i.e. the advance in TEXT space, which
  is what `pdfdevice.render_string_horizontal` walks the pen with. It equals the page-space
  advance only when the text matrix has unit horizontal scale. On this corpus GPO sets
  `Tf 1` and carries the size in `Tm`, so `matrix[0]` is 8-14 and `.adv` is 8-14x too
  small. h01 confirms `.adv x matrix[0] == .width` exactly, on every document.

  Phase 2's `g03` reached the right FIELD by a wrong REASON ("`.adv` is in em units"). The
  field is unchanged here; the reason is corrected, because the reason is what a reader
  would carry to a corpus where GPO's convention does not hold.

NOTHING IS BORROWED. No PDFium value is read, and no other engine is consulted for a font
metric. If pdfminer cannot answer, the glyph carries `advance=None` and the consumer's
documented fallback applies.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_here = Path(__file__).resolve()
for _p in (_here.parents[1] / "phase2", _here.parents[2] / "probes"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def extract(pdf_path: Path, limit: int | None = None, pages: list[int] | None = None):
    from contract_extended import ExtPdfPage
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    out = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
    no_advance = 0
    t0 = time.perf_counter()
    page_numbers = None if pages is None else [p - 1 for p in pages]
    for idx, layout in enumerate(extract_pages(str(pdf_path), laparams=None, page_numbers=page_numbers)):
        if limit is not None and idx >= limit:
            break
        page_no = idx + 1 if pages is None else pages[idx]
        glyphs = []
        stack = list(layout)
        while stack:
            obj = stack.pop()
            if isinstance(obj, LTChar):
                cp = obj.get_text()
                if cp.startswith("(cid:") and cp.endswith(")"):
                    cp = "�"
                    undecodable += 1
                for ch in cp:
                    if ord(ch) < 0x20:
                        continue
                    font = getattr(obj, "fontname", "") or ""
                    if len(font) > 7 and font[6] == "+":
                        font = font[7:]
                    if not font:
                        empty_fonts += 1
                    advance = abs(obj.width)
                    if not advance:
                        # A zero-width box is "pdfminer has no advance for this", not a
                        # zero advance; carried as None so the consumer cannot mistake one
                        # for the other. Same contract rule as pdfium_extended.py.
                        advance = None
                        no_advance += 1
                    glyphs.append(
                        (
                            ord(ch),
                            round(obj.x0, 4),
                            round(obj.y0, 4),
                            round(obj.x1, 4),
                            round(obj.y1, 4),
                            round(obj.matrix[5], 4),
                            round(obj.size, 4),
                            font,
                            bool(getattr(obj, "upright", True)),
                            round(obj.x0, 4),
                            None if advance is None else round(advance, 4),
                        )
                    )
            elif hasattr(obj, "__iter__"):
                stack.extend(obj)
        glyph_total += len(glyphs)
        _, _, w, h = layout.bbox
        out.append(ExtPdfPage(page_no, float(w), float(h), glyphs))
    summary = {
        "backend": "pdfminer-extended",
        "pages": len(out),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "glyphs_without_an_advance": no_advance,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return out, summary
