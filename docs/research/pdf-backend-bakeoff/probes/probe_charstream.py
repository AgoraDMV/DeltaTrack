"""Probe: dump PDFium's text-page CHARACTER STREAM with per-index geometry and font.

The research question this exists to settle: is PDFium's own indexed character stream
-- the one `FPDFText_GetText` / `get_text_range()` returns, including the spaces PDFium
GENERATES rather than reads from the content stream -- addressable by the same char
index that `FPDFText_GetCharBox` / `GetMatrix` / `GetFontSize` / `GetFontInfo` take?

If yes, a backend adapter can hand DeltaTrack an ordered stream that already carries
PDFium's word-spacing, hyphenation and reading-order decisions, WITH geometry attached,
instead of DeltaTrack re-deriving those from raw glyph positions.

Emits, per char index:
    index -> unicode -> generated? -> hyphen? -> unicode-map-error?
          -> charbox / loose charbox / origin -> font size (raw and matrix-scaled)
          -> font name + flags + weight -> text index

Nothing in `src/deltatrack` is imported or modified. Read-only.

Run:
    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_charstream.py \
        tests/corpus/114-hr-2029/4_reported-in-senate.pdf --page 9 --grep FAMILY
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

_FONT_BUF = 256


def _tri(v: int) -> bool | None:
    """FPDFText_IsGenerated / IsHyphen / HasUnicodeMapError return 1 / 0 / -1."""
    return None if v < 0 else bool(v)


def char_records(textpage, page_obj) -> tuple[list[dict], dict]:
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    buf = (ctypes.c_char * _FONT_BUF)()
    flags = ctypes.c_int()
    recs: list[dict] = []
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)

        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        has_box = bool(
            R.FPDFText_GetCharBox(
                raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
            )
        )
        lb = R.FS_RECTF()
        has_loose = bool(R.FPDFText_GetLooseCharBox(raw, i, ctypes.byref(lb)))
        ox, oy = ctypes.c_double(), ctypes.c_double()
        has_origin = bool(R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)))
        mat = R.FS_MATRIX()
        has_matrix = bool(R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)))

        fs = R.FPDFText_GetFontSize(raw, i)
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b) if has_matrix else float("nan")

        nlen = R.FPDFText_GetFontInfo(raw, i, buf, _FONT_BUF, ctypes.byref(flags))
        font = bytes(buf[: max(nlen - 1, 0)]).decode("utf-8", "replace") if nlen > 0 else ""

        recs.append(
            {
                "i": i,
                "cp": cp,
                "ch": chr(cp) if cp else "",
                "generated": _tri(R.FPDFText_IsGenerated(raw, i)),
                "hyphen": _tri(R.FPDFText_IsHyphen(raw, i)),
                "map_error": _tri(R.FPDFText_HasUnicodeMapError(raw, i)),
                "text_index": R.FPDFText_GetTextIndexFromCharIndex(raw, i),
                "box": [left.value, bottom.value, right.value, top.value] if has_box else None,
                "loose": [lb.left, lb.bottom, lb.right, lb.top] if has_loose else None,
                "origin": [ox.value, oy.value] if has_origin else None,
                "matrix": [mat.a, mat.b, mat.c, mat.d, mat.e, mat.f] if has_matrix else None,
                "font_size_raw": fs,
                "font_size_scaled": fs * scale if has_matrix else None,
                "font": font,
                "font_flags": flags.value if nlen > 0 else None,
                "font_weight": R.FPDFText_GetFontWeight(raw, i),
                "angle": R.FPDFText_GetCharAngle(raw, i),
            }
        )
    w, h = page_obj.get_size()
    return recs, {"count_chars": n, "width": float(w), "height": float(h)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, required=True, help="1-based")
    ap.add_argument("--grep", help="show a window around each occurrence in the text stream")
    ap.add_argument("--window", type=int, default=24)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    doc = pdfium.PdfDocument(args.pdf)
    try:
        page_obj = doc[args.page - 1]
        textpage = page_obj.get_textpage()
        try:
            text_range = textpage.get_text_range()
            recs, meta = char_records(textpage, page_obj)
        finally:
            textpage.close()
            page_obj.close()
    finally:
        doc.close()

    stream = "".join(r["ch"] for r in recs)
    print(f"# {args.pdf} page {args.page}")
    print(f"FPDFText_CountChars      = {meta['count_chars']}")
    print(f"len(get_text_range())    = {len(text_range)}")
    print(f"len(per-index GetUnicode)= {len(stream)}")
    print(f"streams identical        = {text_range == stream}")
    gen = [r for r in recs if r["generated"]]
    hyp = [r for r in recs if r["hyphen"]]
    print(f"generated chars          = {len(gen)}  (codepoints: {sorted({r['cp'] for r in gen})})")
    print(f"hyphen-flagged chars     = {len(hyp)}  (codepoints: {sorted({r['cp'] for r in hyp})})")
    print(f"tri-state unsupported    = {sum(1 for r in recs if r['generated'] is None)}")

    if gen:
        print("\n## geometry of GENERATED characters")
        _describe(gen)
    real_sp = [r for r in recs if r["cp"] == 32 and not r["generated"]]
    if real_sp:
        print("\n## geometry of REAL (content-stream) space characters")
        _describe(real_sp)

    if args.grep:
        print(f"\n## windows around {args.grep!r} in the char stream")
        start = 0
        while True:
            k = stream.find(args.grep, start)
            if k < 0:
                break
            lo, hi = max(0, k - 2), min(len(recs), k + len(args.grep) + args.window)
            print(f"\n--- match at char index {k} ---")
            _table(recs[lo:hi])
            start = k + 1

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps({"meta": meta, "chars": recs}, indent=1))
        print(f"\nwrote {args.json_out}")
    return 0


def _describe(rows: list[dict]) -> None:
    n = len(rows)
    no_box = sum(1 for r in rows if r["box"] is None)
    zero_w = sum(1 for r in rows if r["box"] and abs(r["box"][2] - r["box"][0]) < 1e-9)
    zero_h = sum(1 for r in rows if r["box"] and abs(r["box"][3] - r["box"][1]) < 1e-9)
    no_mat = sum(1 for r in rows if r["matrix"] is None)
    ident = sum(1 for r in rows if r["matrix"] and r["matrix"][:4] == [1.0, 0.0, 0.0, 1.0])
    zero_fs = sum(1 for r in rows if not r["font_size_raw"])
    no_font = sum(1 for r in rows if not r["font"])
    sizes = sorted({round(r["font_size_scaled"], 3) for r in rows if r["font_size_scaled"] is not None})
    print(f"  n={n}  no charbox={no_box}  zero-width box={zero_w}  zero-height box={zero_h}")
    print(f"  no matrix={no_mat}  identity matrix={ident}  font_size_raw==0={zero_fs}  empty font name={no_font}")
    print(f"  distinct scaled sizes={sizes[:8]}{' …' if len(sizes) > 8 else ''}")


def _table(rows: list[dict]) -> None:
    cols = ("idx", "ch", "cp", "gen", "hyp", "x0", "x1", "orig_y", "mat.f", "size", "font")
    print(
        f"{cols[0]:>6} {cols[1]:<4} {cols[2]:>6} {cols[3]:>4} {cols[4]:>4} {cols[5]:>8} "
        f"{cols[6]:>8} {cols[7]:>8} {cols[8]:>8} {cols[9]:>7} {cols[10]:<24}"
    )
    for r in rows:
        b = r["box"] or [float("nan")] * 4
        o = r["origin"] or [float("nan")] * 2
        m = r["matrix"] or [float("nan")] * 6
        ch = repr(r["ch"])[1:-1] if r["ch"] not in ("", " ") else ("SP" if r["ch"] == " " else "?")
        sz = r["font_size_scaled"]
        print(
            f"{r['i']:>6} {ch:<4} {r['cp']:>6} {str(r['generated'])[:4]:>4} {str(r['hyphen'])[:4]:>4} "
            f"{b[0]:>8.2f} {b[2]:>8.2f} {o[1]:>8.2f} {m[5]:>8.2f} "
            f"{(f'{sz:.2f}' if sz is not None else 'NA'):>7} {r['font'][:24]:<24}"
        )


if __name__ == "__main__":
    sys.exit(main())
