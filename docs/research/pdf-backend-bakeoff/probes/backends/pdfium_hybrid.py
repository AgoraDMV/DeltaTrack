"""Backend adapter: PDFium's TEXT PAGE character stream, enriched with per-index geometry.

This is the layer under test. It is NOT a third way of reading glyphs; it is the same
`FPDFText_*` char index used twice -- once for the character PDFium decided belongs
there, once for that character's geometry -- rather than once for geometry only.

WHY THIS IS AVAILABLE AT ALL
----------------------------
PDFium's `CPDF_TextPage` builds one char list per page. `FPDFText_CountChars` counts it,
`FPDFText_GetUnicode(i)` names entry i, and `GetCharBox(i)` / `GetCharOrigin(i)` /
`GetMatrix(i)` / `GetFontSize(i)` / `GetFontInfo(i)` all address the SAME entry i. The
list already contains the characters PDFium synthesised rather than read -- word spaces
it inferred rather than found, and line breaks -- flagged by `FPDFText_IsGenerated(i)`.
Measured on this corpus: `FPDFText_CountChars(page) == len(get_text_range(page))` on
every page tried, and `FPDFText_GetTextIndexFromCharIndex` is the identity, so there is
no index skew to correct.

WHAT GENERATED CHARACTERS CARRY, MEASURED NOT ASSUMED
-----------------------------------------------------
A generated character has NO meaningful box, matrix, font size or font name: the box is
a zero-area point, the matrix is the identity (so `matrix.f`, the baseline the glyph
contract carries, reads 0.0), `GetFontSize x scale` reads exactly 1.0, and the font name
is empty. Exactly one geometric fact survives, and it is the one that matters:
`FPDFText_GetCharOrigin(i)` returns the correct baseline y.

So this adapter does not invent geometry for generated characters. It carries the origin
PDFium gives, marks the character as generated, and leaves the rest absent. Downstream,
generated characters are placed by their neighbours in the stream, never by their box.

THE ONE PLACE THE TEXT AND GLYPH APIS DISAGREE
-----------------------------------------------
`get_text_range()[i]` and `FPDFText_GetUnicode(i)` are the same string except at GPO's
soft hyphen, where the text API says U+FFFE and the glyph API says 0x02. Those indices
are exactly the ones `FPDFText_IsHyphen(i)` flags -- so the soft hyphen is recoverable
from a documented predicate rather than from either private convention, and rather than
from the bake-off's "unnamed ink, line-final" position heuristic. It is emitted here as
U+00AD (SOFT HYPHEN), a neutral name no backend owns.

Emits the enriched contract in `contract_hybrid.py`, in PDFium's own char order.
"""

from __future__ import annotations

import ctypes
import math
import time
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

_FONT_BUF = 256
_UPRIGHT_EPS = 1e-6
_SOFT_HYPHEN = 0x00AD


def _font_name(raw, i: int, buf, flags) -> str:
    n = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
    if n <= 0:
        return ""
    return bytes(buf[: max(n - 1, 0)]).decode("utf-8", "replace")


def extract(pdf_path: Path, limit: int | None = None):
    from contract_hybrid import HybridPage

    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    char_total = 0
    generated_total = 0
    hyphen_total = 0
    map_error_total = 0
    empty_fonts = 0
    unnamed = 0
    index_skew_pages = 0
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
                # Recorded, not assumed: if the text string and the char list ever
                # disagree in length, the index identity this adapter rests on is not
                # holding and the scorer must see that rather than infer soundness.
                if len(textpage.get_text_range()) != max(n, 0):
                    index_skew_pages += 1
                chars = []
                for i in range(max(n, 0)):
                    cp = pdfium_raw.FPDFText_GetUnicode(raw, i)
                    generated = pdfium_raw.FPDFText_IsGenerated(raw, i) == 1
                    hyphen = pdfium_raw.FPDFText_IsHyphen(raw, i) == 1
                    if pdfium_raw.FPDFText_HasUnicodeMapError(raw, i) == 1:
                        map_error_total += 1
                    if hyphen:
                        cp = _SOFT_HYPHEN
                        hyphen_total += 1
                    elif cp < 0x20 and not generated:
                        # Ink PDFium could not name and did not flag as a hyphen. Carried
                        # as U+FFFD so the loss stays visible to the scorer instead of
                        # being silently dropped, the same rule the glyph adapter applies.
                        cp = 0xFFFD
                        unnamed += 1

                    ox, oy = ctypes.c_double(), ctypes.c_double()
                    has_origin = bool(pdfium_raw.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)))
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    has_box = bool(
                        pdfium_raw.FPDFText_GetCharBox(
                            raw,
                            i,
                            ctypes.byref(left),
                            ctypes.byref(right),
                            ctypes.byref(bottom),
                            ctypes.byref(top),
                        )
                    )
                    mat = pdfium_raw.FS_MATRIX()
                    has_matrix = bool(pdfium_raw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)))

                    if generated:
                        # No invented geometry. The origin is real; everything else is a
                        # placeholder PDFium filled in, and passing it downstream would be
                        # the heuristic this probe exists to avoid.
                        generated_total += 1
                        chars.append(
                            (
                                cp,
                                True,
                                oy.value if has_origin else None,
                                ox.value if has_origin else None,
                                None,
                                None,
                                None,
                                "",
                                True,
                            )
                        )
                        continue

                    if not (has_box and has_matrix and has_origin):
                        continue
                    size = pdfium_raw.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    font = _font_name(raw, i, buf, flags)
                    if not font:
                        empty_fonts += 1
                    chars.append(
                        (
                            cp,
                            False,
                            oy.value,
                            left.value,
                            right.value,
                            round(size, 4),
                            (bottom.value, top.value),
                            font,
                            abs(mat.b) < _UPRIGHT_EPS and mat.a > 0,
                        )
                    )
                width, height = page_obj.get_size()
            finally:
                textpage.close()
                page_obj.close()
            char_total += len(chars)
            pages.append(HybridPage(p + 1, float(width), float(height), chars))
    finally:
        doc.close()
    summary = {
        "backend": "pdfium-hybrid",
        "pages": len(pages),
        "chars": char_total,
        "generated_chars": generated_total,
        "hyphen_chars": hyphen_total,
        "unicode_map_errors": map_error_total,
        "unnamed_ink": unnamed,
        "empty_font_names": empty_fonts,
        "index_skew_pages": index_skew_pages,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return pages, summary
