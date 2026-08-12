"""Backend adapter: PyMuPDF emitting the EXTENDED glyph contract, from its OWN API.

CEILING REFERENCE ONLY, exactly as `probes/backends/pymupdf_backend.py` is: PyMuPDF is
AGPL-3.0 and is not a shippable candidate (`../../LICENSING.md`). It is scored so the
portability claim is tested against something, not so it can be adopted.

    origin_x   get_texttrace() char origin[0]
    advance    get_texttrace() char bbox[2] - origin[0]

WHY THAT IS A REAL FONT ADVANCE AND NOT AN INK WIDTH. PyMuPDF's documentation calls
`chars[i][3]` a bbox, which is what put this field under review. `jm_trace_text_span` in
the installed `pymupdf/__init__.py` settles it:

    adv = fz_advance_glyph(span.font(), gid, wmode);   adv *= fsize
    x0 = char_orig.x;   x1 = x0 + adv
    char_bbox = fz_make_rect(x0, y0, x1, y1)

The rectangle is CONSTRUCTED from the glyph advance, at the pen origin. `h01` tests the
consequence rather than trusting the reading: `bbox[0] == origin[0]` to 0.0 pt on every
character of every sampled document, which no ink box can satisfy, and the value agrees
with `Font.glyph_advance` on the EMBEDDED font program extracted by PyMuPDF itself at a
rate of 1.0. Two PyMuPDF routes to the same metric, no other engine consulted.

WHY NOT `get_text("rawdict")`, which the neutral adapter uses. rawdict gives a per-char
origin and bbox but is MuPDF's assembled structured text -- it has already decided where
spaces go. `get_texttrace()` is the raw device trace: the marks as drawn, in stream order,
with no inserted characters. That is the correct seam for a contract whose whole point is
that the word-boundary decision is made above it.

    rot = fz_make_matrix(dir.x, dir.y, -dir.y, dir.x, 0, 0)

is applied to the char box about the origin, so `bbox[2] - origin[0]` is the advance
exactly when the span is upright. Non-upright spans are marked `upright=False` and the
consumer drops them, which is the same rule every other adapter applies; their advance is
still emitted, as the x-projection, and is not used.

COORDINATES. MuPDF is y-DOWN from the page top; the contract is PDF page space, y-up. Both
the boxes and the baseline are flipped against the page height, byte-for-byte the rule in
`probes/backends/pymupdf_backend.py`.
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
    import pymupdf
    from contract_extended import ExtPdfPage

    doc = pymupdf.open(str(pdf_path))
    out = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
    no_advance = 0
    t0 = time.perf_counter()
    try:
        if pages is not None:
            wanted = [p - 1 for p in pages]
        else:
            n = doc.page_count if limit is None else min(limit, doc.page_count)
            wanted = list(range(n))
        for p in wanted:
            page = doc[p]
            height = page.rect.height
            glyphs = []
            for span in page.get_texttrace():
                font = span.get("font", "") or ""
                d = span.get("dir", (1.0, 0.0))
                upright = abs(d[1]) < 1e-6 and d[0] > 0
                size = span.get("size", 0.0)
                for ch in span.get("chars", ()):
                    cp, _gid, origin, bbox = ch[0], ch[1], ch[2], ch[3]
                    if cp < 0x20:
                        # The neutral adapters' undecodable rule: ink that could not be
                        # named becomes the same U+FFFD carrier everywhere. GPO's soft
                        # hyphen is U+0002 and reaches here.
                        cp = 0xFFFD
                        undecodable += 1
                    if not font:
                        empty_fonts += 1
                    x0, y0, x1, y1 = bbox
                    fy0, fy1 = height - y1, height - y0
                    advance = bbox[2] - origin[0]
                    if advance <= 0:
                        advance = None
                        no_advance += 1
                    glyphs.append(
                        (
                            cp,
                            round(x0, 4),
                            round(fy0, 4),
                            round(x1, 4),
                            round(fy1, 4),
                            round(height - origin[1], 4),
                            round(size, 4),
                            font,
                            upright,
                            round(origin[0], 4),
                            None if advance is None else round(advance, 4),
                        )
                    )
            glyph_total += len(glyphs)
            out.append(ExtPdfPage(p + 1, float(page.rect.width), float(height), glyphs))
    finally:
        doc.close()
    summary = {
        "backend": "pymupdf-extended",
        "pages": len(out),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "glyphs_without_an_advance": no_advance,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
        "license_role": "ceiling-reference-only (AGPL-3.0)",
    }
    return out, summary
