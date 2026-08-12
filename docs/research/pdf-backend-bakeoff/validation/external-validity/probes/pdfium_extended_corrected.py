"""X's character facts: the EXTENDED glyph contract, corrected. RESULT-BEARING.

    frozen rule        PRE-REGISTRATION X-2 -- "no glyph with codepoint 32 exists in the
                       contract, on any page"; A21/A23 -- carry `source_char_index`
    executable here    the per-character loop drops every U+0020 and records PDFium's own
                       char index beside each surviving glyph
    test               `x2_verify.py` (X2-a and X2-b), `x13_x_arm.py`
    evidence           `results/x2_contract_assertions.json`

WHAT WAS WRONG WITH `validation/phase2/pdfium_extended.py`, MEASURED NOT ASSERTED. Its
undecodable-glyph rule keys on `cp < 0x20`, so U+0020 fell straight through it. On six pages
of `114-hr-2029/4` it emitted **1142 glyphs with codepoint 32 out of 7382 (15.5 %)** -- 947
of them PDFium's own INVENTED spaces. That is the phase-3 D2 finding: the adapter satisfied
the docstring's letter while passing the engine's word-boundary decision straight through,
which is the one thing the X design exists not to do. X2-a fails on that adapter today.

WHY DROPPING U+0020 IS THE RIGHT CORRECTION AND NOT A CODEPOINT HACK. X-2 states the
principle: a space carries no ink, and the contract is "facts about marks that are on the
page". Excluding U+0020 outright is also the design's answer to `FPDFText_IsGenerated` --
it removes engine-invented spaces WITHOUT consulting that Experimental predicate, which the
neutral-contract design exists to avoid. Every word boundary is then decided above the seam,
by `reconstruct_extended_corrected.wants_space`, which is the hypothesis under test.

`include_engine_spaces=True` re-admits them. It exists solely so `x2_verify` can EXECUTE
X2-b -- re-admitting the engine's spaces must change no reconstructed line -- rather than
asserting it. Nothing in the scoring path may pass it.

RECORDED, because it is a real consequence and not this module's to resolve: PDFium reports
a positive-area ink box for a real U+0020 (about 3.6 pt wide, 0.014 pt tall, against 8.44 pt
for a capital), so the neutral skeleton's geometric eligibility rule admits it while this
contract does not. Those gids are therefore skeleton members that X can never emit. See
`x12_skeleton_eligibility.py`; it needs an amendment, not a silent threshold here.
"""

from __future__ import annotations

import ctypes
import math
import time
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

_FONT_BUF = 256
_INK_WIDTH = 0.5
_UPRIGHT_EPS = 1e-6

# Field order is the wire format. `source_char_index` is APPENDED, so every consumer that
# unpacks the first eleven positions is unaffected.
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
    "origin_x",
    "advance",
    "source_char_index",
)
CP, X0, Y0, X1, Y1, BASELINE, SIZE, FONT, UPRIGHT, ORIGIN_X, ADVANCE, SCI = range(12)


@dataclass
class ExtPdfPageCorrected:
    page_number: int  # 1-based
    width: float
    height: float
    glyphs: list[tuple]


def _font_name(raw, i: int, buf, flags) -> str:
    n = pdfium_raw.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
    if n <= 0:
        return ""
    return bytes(buf[: max(n - 1, 0)]).decode("utf-8", "replace")


def extract(pdf_path: Path, limit: int | None = None, readmit: str = "none"):
    """`readmit` re-admits U+0020 for X2-b ONLY. Never pass anything but "none" when scoring.

    "none"       the frozen X-2 contract: no U+0020 at all
    "generated"  re-admit only spaces PDFium INVENTED (`FPDFText_IsGenerated`)
    "all"        re-admit every U+0020, including real content-stream spaces

    The two non-default modes exist because "the engine's spaces" in X2-b is ambiguous
    between them and the two readings give OPPOSITE gate outcomes on development material.
    See `results/x2_contract_assertions.json` and amendment A24.
    """
    if readmit not in ("none", "generated", "all"):
        raise ValueError(f"readmit must be none/generated/all, not {readmit!r}")
    doc = pdfium.PdfDocument(str(pdf_path))
    pages = []
    glyph_total = 0
    empty_fonts = 0
    undecodable = 0
    no_advance = 0
    zero_advance = 0
    dropped_spaces = 0
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
                obj_font: dict[int, tuple] = {}
                width_cache: dict[tuple, float | None] = {}
                for i in range(max(n, 0)):
                    cp = pdfium_raw.FPDFText_GetUnicode(raw, i)

                    # X-2, and the whole correction. Placed BEFORE any geometry call so a
                    # space cannot influence anything downstream, not even a cache key.
                    if cp == 32:
                        keep = readmit == "all" or (
                            readmit == "generated" and pdfium_raw.FPDFText_IsGenerated(raw, i) == 1
                        )
                        if not keep:
                            dropped_spaces += 1
                            continue

                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    if not pdfium_raw.FPDFText_GetCharBox(
                        raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
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
                                # A returned TRUE with width 0 is a failed reverse map, not
                                # a zero-width glyph. Carried as None so downstream cannot
                                # mistake unknown for zero.
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
                            i,
                        )
                    )
                width, height = page_obj.get_size()
            finally:
                textpage.close()
                page_obj.close()
            glyph_total += len(glyphs)
            pages.append(ExtPdfPageCorrected(p + 1, float(width), float(height), glyphs))
    finally:
        doc.close()
    summary = {
        "backend": "pdfium-extended-corrected",
        "pages": len(pages),
        "glyphs": glyph_total,
        "u0020_dropped": dropped_spaces,
        "readmit_mode": readmit,
        "empty_font_names": empty_fonts,
        "undecodable_glyphs": undecodable,
        "glyphs_without_an_advance": no_advance,
        "zero_advance_reverse_map_failures": zero_advance,
        "extract_ms": round((time.perf_counter() - t0) * 1000),
    }
    return pages, summary
