"""Backend adapter: PyMuPDF (AGPL-3.0), emitting the neutral contract.

CEILING REFERENCE ONLY. Per the spec's answered licensing question, this backend is run
and scored in full but is not a shippable candidate: DeltaTrack will not take on an AGPL
compliance obligation for what it distributes to congressional offices, or pass one to
BillTrax downstream, absent a separate explicit licensing decision. Its score exists to
say what the best achievable number on this corpus looks like, which is what prices the
gap against the best shippable backend.

`get_text("rawdict")` is the per-character view: spans carry a font name and size, and
each char carries its own bbox and origin (the true baseline, which most backends do not
expose separately from the box bottom).
"""

from __future__ import annotations

import time
from pathlib import Path


def extract(pdf_path: Path, limit: int | None = None):
    import pymupdf
    from contract import PdfPage

    doc = pymupdf.open(str(pdf_path))
    pages = []
    glyph_total = 0
    empty_fonts = 0
    t0 = time.perf_counter()
    try:
        n_pages = doc.page_count if limit is None else min(limit, doc.page_count)
        for p in range(n_pages):
            page = doc[p]
            height = page.rect.height
            raw = page.get_text("rawdict")
            glyphs = []
            for block in raw.get("blocks", ()):
                for line in block.get("lines", ()):
                    for span in line.get("spans", ()):
                        font = span.get("font", "") or ""
                        d = line.get("dir", (1.0, 0.0))
                        upright = abs(d[1]) < 1e-6 and d[0] > 0
                        size = span.get("size", 0.0)
                        for ch in span.get("chars", ()):
                            cp = ch.get("c", "")
                            if not cp or ord(cp) < 0x20:
                                continue
                            if not font:
                                empty_fonts += 1
                            x0, y0, x1, y1 = ch["bbox"]
                            # PyMuPDF reports y downward from the page top; the contract
                            # is PDF page space (y up), so flip against page height.
                            fy0, fy1 = height - y1, height - y0
                            baseline = height - ch["origin"][1]
                            glyphs.append(
                                (
                                    ord(cp),
                                    round(x0, 4),
                                    round(fy0, 4),
                                    round(x1, 4),
                                    round(fy1, 4),
                                    round(baseline, 4),
                                    round(size, 4),
                                    font,
                                    upright,
                                )
                            )
            glyph_total += len(glyphs)
            pages.append(PdfPage(p + 1, page.rect.width, height, glyphs))
    finally:
        doc.close()
    summary = {
        "backend": "pymupdf",
        "pages": len(pages),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
        "license_role": "ceiling-reference-only (AGPL-3.0)",
    }
    return pages, summary
