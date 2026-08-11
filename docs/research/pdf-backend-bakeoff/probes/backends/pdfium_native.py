"""Backend adapter: PDFium via pypdfium2 (the incumbent), emitting the neutral contract.

This adapter is the calibration reference for Trap 1. It reads exactly the same FFI
entry points `parsers/pdf_text._page_glyph_sizes` uses, but it emits glyph facts rather
than PDFium-shaped text, so the incumbent goes through the same neutral reconstruction
every challenger does. If PDFium does not score near ceiling through that layer, the
layer is wrong and no other result is trustworthy.

One deliberate difference from the production sidecar: the per-glyph font name is read
here (`FPDFText_GetFontInfo`), which production does not use yet. It is in the contract
because the source-signal inventory names font role as the highest-value unadopted PDF
signal, and a bake-off that ignored it could pick a backend that forecloses it.
"""

from __future__ import annotations

import ctypes
import math
import time
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

_FONT_BUF = 256
# Minimum box width (points) for a glyph to count as ink rather than a structural
# marker. PDFium's 0x0A/0x0D breaks measure exactly 0.0 wide; the narrowest real GPO
# glyph on this corpus (the soft hyphen) measures ~3.0.
_INK_WIDTH = 0.5
# A glyph is upright when its text matrix carries no rotation/skew component.
_UPRIGHT_EPS = 1e-6


def _font_name(raw, i: int, buf, flags) -> str:
    n = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
    if n <= 0:
        return ""
    # FPDFText_GetFontInfo writes a NUL-terminated byte string and returns its length
    # including the terminator.
    return bytes(buf[: max(n - 1, 0)]).decode("utf-8", "replace")


def extract(pdf_path: Path, limit: int | None = None):
    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
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
                for i in range(max(n, 0)):
                    # GLYPH API deliberately, NOT textpage.get_text_range().
                    # Production reads codepoints from the bulk text string, but that is
                    # PDFium's TEXT api and it silently repairs what the glyph api cannot
                    # name: the GPO soft hyphen reads 0x02 here and U+FFFE there. Letting
                    # this adapter reach for the text string would hand PDFium a fallback
                    # no challenger has, and the bake-off would be scoring the fallback
                    # instead of the glyph facts.
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
                    # Backend-neutral undecodable-glyph rule, applied identically by every
                    # adapter: a control codepoint with a ZERO-width box is a structural
                    # marker (PDFium emits 0x0A/0x0D line breaks this way) and is dropped;
                    # a control codepoint with REAL INK is a glyph the backend failed to
                    # name, and is carried as U+FFFD so the loss is visible to the scorer
                    # rather than silently swallowed. The rule keys on ink, never on a
                    # codepoint value, so it favours no backend.
                    if cp < 0x20:
                        if right.value - left.value < _INK_WIDTH:
                            continue
                        cp = 0xFFFD
                        undecodable += 1
                    size = pdfium_raw.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    font = _font_name(raw, i, buf, flags)
                    if not font:
                        empty_fonts += 1
                    # mat.f is the TEXT-OBJECT ORIGIN y -- the true baseline, identical
                    # for every glyph on a printed line. The char-box bottom is not: a
                    # descender sits ~0.2x-size below it, splitting one printed line into
                    # two clusters. Production tolerates that because its sidecar only
                    # needs the margin-number -> geometry map, and a descender-only
                    # fragment simply fails the line-number match and is dropped. A layer
                    # that RECONSTRUCTS text from glyphs cannot tolerate it.
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
                        )
                    )
                width, height = page_obj.get_size()
            finally:
                textpage.close()
                page_obj.close()
            glyph_total += len(glyphs)
            pages.append(_page(p + 1, width, height, glyphs))
    finally:
        doc.close()
    summary = {
        "backend": "pdfium-native",
        "pages": len(pages),
        "glyphs": glyph_total,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return pages, summary


def _page(number, width, height, glyphs):
    from contract import PdfPage

    return PdfPage(number, float(width), float(height), glyphs)
