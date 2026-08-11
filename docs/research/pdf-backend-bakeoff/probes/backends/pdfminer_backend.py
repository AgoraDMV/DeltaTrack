"""Backend adapter: pdfminer.six (MIT, pure Python), emitting the neutral contract.

ADR 0002 removed pdfminer.six on the strength of pdfplumber's `extract_text()`, which is
layout analysis and text assembly -- both downstream of this seam. What this adapter uses
is `LTChar`, which carries a per-character bbox, size and PostScript font name, and is
the contract almost exactly. So the question asked here is the one ADR 0002 never asked.

`laparams=None` is deliberate: it disables pdfminer's layout analysis entirely, which is
both faster and the honest configuration for a glyph-facts bake-off. With it enabled we
would be scoring pdfminer's line grouping against DeltaTrack's, which is the pipeline
comparison the spec forbids.
"""

from __future__ import annotations

import time
from pathlib import Path


def extract(pdf_path: Path, limit: int | None = None):
    from contract import PdfPage
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    pages = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
    t0 = time.perf_counter()
    for idx, layout in enumerate(extract_pages(str(pdf_path), laparams=None)):
        if limit is not None and idx >= limit:
            break
        glyphs = []
        stack = list(layout)
        while stack:
            obj = stack.pop()
            if isinstance(obj, LTChar):
                cp = obj.get_text()
                # pdfminer's undecodable-glyph form is the literal string "(cid:123)".
                # Iterating it would emit eight bogus glyphs, so it collapses to the same
                # U+FFFD every other adapter uses for "ink I could not name".
                if cp.startswith("(cid:") and cp.endswith(")"):
                    cp = "�"
                    undecodable += 1
                # LTChar.get_text() is normally one character, but a ligature or a
                # CID-mapped glyph can decode to several. Splitting keeps the contract
                # one-codepoint-per-entry; every part shares the composite's box, which
                # is the honest representation of what the backend actually knows.
                for ch in cp:
                    if ord(ch) < 0x20:
                        continue
                    font = getattr(obj, "fontname", "") or ""
                    # pdfminer prefixes subset fonts with a six-letter tag + "+".
                    if len(font) > 7 and font[6] == "+":
                        font = font[7:]
                    if not font:
                        empty_fonts += 1
                    # matrix[5] is the text-object origin y, i.e. the true baseline.
                    # It agrees with PDFium's mat.f to the point on this corpus.
                    # Note pdfminer's y0/y1 are FONT-METRIC bounds (uniform per line),
                    # not ink bounds like PDFium's -- another reason the contract
                    # clusters on the matrix origin rather than the box.
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
                        )
                    )
            elif hasattr(obj, "__iter__"):
                stack.extend(obj)
        glyph_total += len(glyphs)
        _, _, w, h = layout.bbox
        pages.append(PdfPage(idx + 1, float(w), float(h), glyphs))
    summary = {
        "backend": "pdfminer",
        "pages": len(pages),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return pages, summary
