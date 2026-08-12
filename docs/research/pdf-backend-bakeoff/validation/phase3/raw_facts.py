"""Unrounded facts, straight from each backend API, before the contract packs them.

WHY THIS EXISTS. `h04` reported "max |Δ advance| = 0.0 pt" over 390,582 endpoints. Every
adapter rounds `advance` to four decimal places on the way into `contract_extended`, so
what that measured was equality **at the contract's 1e-4 pt precision**, not equality of
the values the engines actually returned. Those are different claims and only the weaker
one was evidenced.

This module re-reads the same glyphs keeping full precision, so `h06` can compare the raw
values. It deliberately does NOT modify any adapter:

    phase2/pdfium_extended.py    is frozen phase-2 work and is not touched
    phase3/pdfminer_extended.py  and pymupdf_extended.py are left byte-identical so the
                                 committed h03/h04 result files stay reproducible

which means the extraction loops are duplicated here. Duplication is the failure mode this
module has to defend against, so every raw record carries the tuple its adapter would have
produced, and `check(...)` asserts element-by-element that the two agree. If this module
drifts from an adapter the assertion fires; it cannot quietly measure a different
population and report agreement.

Read-only. Writes nothing.
"""

from __future__ import annotations

import ctypes
import math
import sys
from pathlib import Path

_here = Path(__file__).resolve()
for _p in (_here.parents[1] / "phase2", _here.parents[2] / "probes"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_FONT_BUF = 256
_INK_WIDTH = 0.5
_UPRIGHT_EPS = 1e-6


def _pdfium(path: Path, pages: list[int]) -> dict[int, list[dict]]:
    """Byte-for-byte the loop in `phase2/pdfium_extended.py`, without the rounding.

    NOTE which fields that adapter already leaves raw: `origin_x` is `ox.value` unrounded,
    while `size` and `advance` are rounded to 4 dp. The other two adapters round their
    origin. That asymmetry is itself a candidate explanation for h03/h04's reported origin
    gaps, and h06 tests it.
    """
    import pypdfium2 as pdfium
    import pypdfium2.raw as R

    doc = pdfium.PdfDocument(str(path))
    out: dict[int, list[dict]] = {}
    buf = (ctypes.c_char * _FONT_BUF)()
    flags = ctypes.c_int()
    try:
        for pno in pages:
            page_obj = doc[pno - 1]
            textpage = page_obj.get_textpage()
            recs: list[dict] = []
            try:
                raw = textpage.raw
                n = R.FPDFText_CountChars(raw)
                obj_font: dict[int, tuple] = {}
                width_cache: dict[tuple, float | None] = {}
                for i in range(max(n, 0)):
                    cp = R.FPDFText_GetUnicode(raw, i)
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    if not R.FPDFText_GetCharBox(
                        raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
                    ):
                        continue
                    mat = R.FS_MATRIX()
                    if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
                        continue
                    ox, oy = ctypes.c_double(), ctypes.c_double()
                    if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
                        continue
                    if cp < 0x20:
                        if right.value - left.value < _INK_WIDTH:
                            continue
                        cp = 0xFFFD
                    size = R.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    fn = R.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
                    font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
                    obj = R.FPDFText_GetTextObject(raw, i)
                    obj_key = ctypes.cast(obj, ctypes.c_void_p).value if obj else 0
                    advance = None
                    if obj_key:
                        if obj_key not in obj_font:
                            f = R.FPDFTextObj_GetFont(obj)
                            obj_font[obj_key] = (ctypes.cast(f, ctypes.c_void_p).value if f else 0, f)
                        fk, fh = obj_font[obj_key]
                        if fk:
                            ck = (fk, cp)
                            if ck not in width_cache:
                                w = ctypes.c_float()
                                ok = R.FPDFFont_GetGlyphWidth(fh, cp, 1000.0, ctypes.byref(w))
                                width_cache[ck] = (w.value / 1000.0) if (ok and w.value > 0) else None
                            em = width_cache[ck]
                            advance = None if em is None else em * size
                    upright = abs(mat.b) < _UPRIGHT_EPS and mat.a > 0
                    recs.append(
                        {
                            "cp": cp,
                            "origin_x": ox.value,
                            "baseline": mat.f,
                            "size": size,
                            "advance": advance,
                            "upright": upright,
                            "packed": (
                                cp,
                                left.value,
                                bottom.value,
                                right.value,
                                top.value,
                                mat.f,
                                round(size, 4),
                                font,
                                upright,
                                ox.value,
                                None if advance is None else round(advance, 4),
                            ),
                        }
                    )
            finally:
                textpage.close()
                page_obj.close()
            out[pno] = recs
    finally:
        doc.close()
    return out


def _pdfminer(path: Path, pages: list[int]) -> dict[int, list[dict]]:
    """Byte-for-byte the loop in `phase3/pdfminer_extended.py`, without the rounding."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    out: dict[int, list[dict]] = {}
    for idx, layout in enumerate(extract_pages(str(path), laparams=None, page_numbers=[p - 1 for p in pages])):
        pno = pages[idx]
        recs: list[dict] = []
        stack = list(layout)
        while stack:
            obj = stack.pop()
            if isinstance(obj, LTChar):
                cp = obj.get_text()
                if cp.startswith("(cid:") and cp.endswith(")"):
                    cp = "�"
                for ch in cp:
                    if ord(ch) < 0x20:
                        continue
                    font = getattr(obj, "fontname", "") or ""
                    if len(font) > 7 and font[6] == "+":
                        font = font[7:]
                    advance = abs(obj.width) or None
                    upright = bool(getattr(obj, "upright", True))
                    recs.append(
                        {
                            "cp": ord(ch),
                            "origin_x": obj.x0,
                            "baseline": obj.matrix[5],
                            "size": obj.size,
                            "advance": advance,
                            "upright": upright,
                            "packed": (
                                ord(ch),
                                round(obj.x0, 4),
                                round(obj.y0, 4),
                                round(obj.x1, 4),
                                round(obj.y1, 4),
                                round(obj.matrix[5], 4),
                                round(obj.size, 4),
                                font,
                                upright,
                                round(obj.x0, 4),
                                None if advance is None else round(advance, 4),
                            ),
                        }
                    )
            elif hasattr(obj, "__iter__"):
                stack.extend(obj)
        out[pno] = recs
    return out


def _pymupdf(path: Path, pages: list[int]) -> dict[int, list[dict]]:
    """Byte-for-byte the loop in `phase3/pymupdf_extended.py`, without the rounding."""
    import pymupdf

    doc = pymupdf.open(str(path))
    out: dict[int, list[dict]] = {}
    try:
        for pno in pages:
            page = doc[pno - 1]
            height = page.rect.height
            recs: list[dict] = []
            for span in page.get_texttrace():
                font = span.get("font", "") or ""
                d = span.get("dir", (1.0, 0.0))
                upright = abs(d[1]) < 1e-6 and d[0] > 0
                size = span.get("size", 0.0)
                for ch in span.get("chars", ()):
                    cp, _gid, origin, bbox = ch[0], ch[1], ch[2], ch[3]
                    if cp < 0x20:
                        cp = 0xFFFD
                    x0, y0, x1, y1 = bbox
                    advance = bbox[2] - origin[0]
                    if advance <= 0:
                        advance = None
                    recs.append(
                        {
                            "cp": cp,
                            "origin_x": origin[0],
                            "baseline": height - origin[1],
                            "size": size,
                            "advance": advance,
                            "upright": upright,
                            "packed": (
                                cp,
                                round(x0, 4),
                                round(height - y1, 4),
                                round(x1, 4),
                                round(height - y0, 4),
                                round(height - origin[1], 4),
                                round(size, 4),
                                font,
                                upright,
                                round(origin[0], 4),
                                None if advance is None else round(advance, 4),
                            ),
                        }
                    )
            out[pno] = recs
    finally:
        doc.close()
    return out


_READERS = {"pdfium": _pdfium, "pdfminer": _pdfminer, "pymupdf": _pymupdf}


def raw_pages(backend: str, path: Path, pages: list[int]) -> dict[int, list[dict]]:
    return _READERS[backend](path, pages)


def check(backend: str, raw: dict[int, list[dict]], adapter_pages: list) -> None:
    """Assert this module reproduces its adapter exactly, glyph for glyph.

    The whole value of a raw sidecar is that it is the same population. If a loop here ever
    drifts from the adapter it duplicates, this fires rather than letting h06 compare two
    different sets of glyphs and call them equal.
    """
    for page in adapter_pages:
        mine = raw.get(page.page_number)
        assert mine is not None, f"{backend}: page {page.page_number} missing from the raw read"
        assert len(mine) == len(page.glyphs), (
            f"{backend} page {page.page_number}: raw read has {len(mine)} glyphs, adapter has {len(page.glyphs)}"
        )
        for i, (r, g) in enumerate(zip(mine, page.glyphs)):
            assert r["packed"] == g, f"{backend} page {page.page_number} glyph {i}: raw sidecar diverged from adapter"
