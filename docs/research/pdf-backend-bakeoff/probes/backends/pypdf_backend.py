"""Backend adapter: pypdf (BSD-3, pure Python), emitting the neutral contract.

The spec's "cheap long shot". pypdf has no per-character geometry API; the closest thing
is the `visitor_text` callback on `extract_text`, which fires per text-showing operator
and hands back the current transformation matrix, the text matrix, the font dictionary
and the font size. That gives a per-RUN origin, not a per-character box, so this adapter
must synthesize character advances from font widths.

It is included to be measured, not because it is expected to win: the synthesis below is
an approximation with no width information for fonts whose /Widths array is missing, and
the run origin is the only real position datum. If it fails, that failure is the finding.
"""

from __future__ import annotations

import time
from pathlib import Path


def extract(pdf_path: Path, limit: int | None = None):
    from contract import PdfPage
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages = []
    glyph_total = 0
    empty_fonts = 0
    t0 = time.perf_counter()
    n_pages = len(reader.pages) if limit is None else min(limit, len(reader.pages))
    for p in range(n_pages):
        page = reader.pages[p]
        glyphs: list = []
        state: dict = {"empty": 0}

        def visitor(text, cm, tm, font_dict, font_size, _g=glyphs, _s=state):
            if not text or not text.strip():
                return
            # tm is the text matrix [a b c d e f]; (e, f) is the run origin in page
            # space and sqrt(a^2 + b^2) the horizontal scale.
            x = tm[4]
            y = tm[5]
            scale = (tm[0] ** 2 + tm[1] ** 2) ** 0.5
            size = (font_size or 0.0) * (scale or 1.0)
            name = ""
            if isinstance(font_dict, dict):
                name = str(font_dict.get("/BaseFont", "") or "")
                if name.startswith("/"):
                    name = name[1:]
                if len(name) > 7 and name[6] == "+":
                    name = name[7:]
            if not name:
                _s["empty"] += len(text)
            # No per-character widths are available here, so advance uniformly across
            # the run. This is the approximation that decides whether pypdf is viable.
            advance = size * 0.5 if size else 5.0
            for k, ch in enumerate(text):
                if ord(ch) < 0x20:
                    continue
                cx = x + k * advance
                _g.append(
                    (
                        ord(ch),
                        round(cx, 4),
                        round(y, 4),
                        round(cx + advance, 4),
                        round(y + size, 4),
                        round(y, 4),
                        round(size, 4),
                        name,
                        abs(tm[1]) < 1e-6 and tm[0] > 0,
                    )
                )

        page.extract_text(visitor_text=visitor)
        empty_fonts += state["empty"]
        glyph_total += len(glyphs)
        box = page.mediabox
        pages.append(PdfPage(p + 1, float(box.width), float(box.height), glyphs))
    summary = {
        "backend": "pypdf",
        "pages": len(pages),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
        "geometry_note": "per-run origin only; character advances synthesized",
    }
    return pages, summary
