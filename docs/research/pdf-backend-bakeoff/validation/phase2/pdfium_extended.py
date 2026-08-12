"""Backend adapter: PDFium emitting the EXTENDED glyph contract.

A deliberate minimal edit of `probes/backends/pdfium_native.py`. Every rule is copied
byte-for-byte -- the `_INK_WIDTH` undecodable-glyph rule, the U+FFFD carrier, `mat.f` as
the baseline, the upright test, the font-name read. Two fields are added and nothing else,
so a difference in results is attributable to them.

    origin_x   FPDFText_GetCharOrigin                                     [not Experimental]
    advance    FPDFText_GetTextObject -> FPDFTextObj_GetFont
               -> FPDFFont_GetGlyphWidth                                  [3x Experimental]

WHAT THIS ADAPTER DOES NOT DO, and it is the whole point of the design: it never reads
`get_text_range()`, never asks whether a character was generated, and never consumes a
space the engine decided to insert. It asks only for facts about marks that are on the
page. The word-boundary decision is made above the seam, in `reconstruct_extended.py`.

THE ONE KNOWN GAP, measured in `g01_pdfium_advance_gate.py`. `FPDFFont_GetGlyphWidth`
takes a Unicode codepoint and reverse-maps it with `CharCodeFromUnicode`, which fails on
GPO's soft hyphen (U+0002) and returns TRUE with a width of 0. A zero advance is carried
as `None`, not as 0.0, so a consumer cannot silently treat "unknown" as "zero width".
"""

from __future__ import annotations

import ctypes
import math
import time
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

_FONT_BUF = 256
_INK_WIDTH = 0.5
_UPRIGHT_EPS = 1e-6


def _font_name(raw, i: int, buf, flags) -> str:
    n = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
    if n <= 0:
        return ""
    return bytes(buf[: max(n - 1, 0)]).decode("utf-8", "replace")


def extract(pdf_path: Path, limit: int | None = None):
    from contract_extended import ExtPdfPage

    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
    no_advance = 0
    zero_advance = 0
    buf = (ctypes.c_char * _FONT_BUF)()
    flags = ctypes.c_int()
    t0 = time.perf_counter()
    try:
        n_pages = len(doc) if limit is None else min(limit, len(doc))
        for p in range(n_pages):
            page_obj = doc[p]
            textpage = page_obj.get_textpage()
            try:
                raw = textpage.raw
                n = pdfium_raw.FPDFText_CountChars(raw)
                glyphs = []
                # Cached per page: FPDFText_GetTextObject returns the same object for
                # every character of a run, and the font handle for every character of a
                # text object. Without this the chain dominates extraction cost.
                obj_font: dict[int, tuple] = {}
                width_cache: dict[tuple, float | None] = {}
                for i in range(max(n, 0)):
                    cp = pdfium_raw.FPDFText_GetUnicode(raw, i)
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    if not pdfium_raw.FPDFText_GetCharBox(
                        raw,
                        i,
                        ctypes.byref(left),
                        ctypes.byref(right),
                        ctypes.byref(bottom),
                        ctypes.byref(top),
                    ):
                        continue
                    mat = pdfium_raw.FS_MATRIX()
                    if not pdfium_raw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
                        continue
                    ox, oy = ctypes.c_double(), ctypes.c_double()
                    if not pdfium_raw.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
                        continue
                    # Byte-for-byte the neutral undecodable-glyph rule from
                    # backends/pdfium_native.py. Keys on ink, never on a codepoint value.
                    if cp < 0x20:
                        if right.value - left.value < _INK_WIDTH:
                            continue
                        cp = 0xFFFD
                        undecodable += 1
                    size = pdfium_raw.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    font = _font_name(raw, i, buf, flags)
                    if not font:
                        empty_fonts += 1

                    obj = pdfium_raw.FPDFText_GetTextObject(raw, i)
                    obj_key = ctypes.cast(obj, ctypes.c_void_p).value if obj else 0
                    advance = None
                    if obj_key:
                        if obj_key not in obj_font:
                            f = pdfium_raw.FPDFTextObj_GetFont(obj)
                            obj_font[obj_key] = (ctypes.cast(f, ctypes.c_void_p).value if f else 0, f)
                        fk, fh = obj_font[obj_key]
                        if fk:
                            ck = (fk, cp)
                            if ck not in width_cache:
                                w = ctypes.c_float()
                                ok = pdfium_raw.FPDFFont_GetGlyphWidth(fh, cp, 1000.0, ctypes.byref(w))
                                # A returned TRUE with width 0 is a failed reverse map,
                                # not a zero-width glyph. Carried as None so downstream
                                # cannot mistake unknown for zero.
                                width_cache[ck] = (w.value / 1000.0) if (ok and w.value > 0) else None
                                if ok and w.value == 0:
                                    zero_advance += 1
                            em = width_cache[ck]
                            advance = None if em is None else em * size
                    if advance is None:
                        no_advance += 1

                    glyphs.append(
                        (
                            cp,
                            left.value,
                            bottom.value,
                            right.value,
                            top.value,
                            mat.f,
                            round(size, 4),
                            font,
                            abs(mat.b) < _UPRIGHT_EPS and mat.a > 0,
                            ox.value,
                            None if advance is None else round(advance, 4),
                        )
                    )
                width, height = page_obj.get_size()
            finally:
                textpage.close()
                page_obj.close()
            glyph_total += len(glyphs)
            pages.append(ExtPdfPage(p + 1, float(width), float(height), glyphs))
    finally:
        doc.close()
    summary = {
        "backend": "pdfium-extended",
        "pages": len(pages),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "glyphs_without_an_advance": no_advance,
        "zero_advance_reverse_map_failures": zero_advance,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return pages, summary
