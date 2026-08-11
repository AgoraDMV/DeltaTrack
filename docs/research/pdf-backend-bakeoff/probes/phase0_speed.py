"""Phase 0 gate 4: pdfminer.six speed on the largest corpus bills, vs the PDFium incumbent.

The spec's kill condition: "if one document takes tens of seconds it is out on Phase 5
grounds". Native timing is the floor; Pyodide adds the measured 1.6x-1.9x WASM penalty on
top, so a native number is multiplied by that band before comparing against the gate.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/phase0_speed.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

WASM_PENALTY = (1.6, 1.9)  # measured in the delivery spike


def page_count(path: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    try:
        return len(doc)
    finally:
        doc.close()


def time_pdfium(path: Path, limit: int | None = None) -> tuple[float, int, int]:
    """Full incumbent extraction (glyph sidecar included) over `limit` pages."""
    import ctypes
    import math

    import pypdfium2 as pdfium
    import pypdfium2.raw as raw_api

    doc = pdfium.PdfDocument(str(path))
    n_pages = len(doc) if limit is None else min(limit, len(doc))
    glyphs = 0
    t0 = time.perf_counter()
    try:
        for i in range(n_pages):
            page = doc[i]
            tp = page.get_textpage()
            try:
                text = tp.get_text_range()
                n = raw_api.FPDFText_CountChars(tp.raw)
                glyphs += max(n, 0)
                for j in range(max(n, 0)):
                    left, right, bottom, top = (ctypes.c_double() for _ in range(4))
                    if not raw_api.FPDFText_GetCharBox(
                        tp.raw,
                        j,
                        ctypes.byref(left),
                        ctypes.byref(right),
                        ctypes.byref(bottom),
                        ctypes.byref(top),
                    ):
                        continue
                    mat = raw_api.FS_MATRIX()
                    if not raw_api.FPDFText_GetMatrix(tp.raw, j, ctypes.byref(mat)):
                        continue
                    math.sqrt(mat.a * mat.a + mat.b * mat.b)
                _ = text
            finally:
                tp.close()
                page.close()
    finally:
        doc.close()
    return time.perf_counter() - t0, n_pages, glyphs


def time_pdfminer(path: Path, limit: int | None = None) -> tuple[float, int, int]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    glyphs = 0
    pages = 0
    t0 = time.perf_counter()
    # laparams=None disables layout analysis (the part ADR 0002 rejected); we only want
    # glyph facts, so this is both faster and the honest configuration for this bake-off.
    for layout in extract_pages(str(path), laparams=LAParams()):
        pages += 1
        stack = list(layout)
        while stack:
            obj = stack.pop()
            if isinstance(obj, LTChar):
                glyphs += 1
            elif hasattr(obj, "__iter__"):
                stack.extend(obj)
        if limit is not None and pages >= limit:
            break
    return time.perf_counter() - t0, pages, glyphs


def main() -> None:
    corpus = REPO / "tests" / "corpus"
    pdfs = sorted(corpus.glob("*/*.pdf"), key=lambda p: -p.stat().st_size)
    sample = int(sys.argv[1]) if len(sys.argv) > 1 else 25

    print(f"{'document':<48} {'pages':>6} {'pdfium_s':>9} {'pdfminer_s':>11} {'ratio':>7}")
    for pdf in pdfs[:3]:
        total = page_count(pdf)
        t_incumbent, n, g_i = time_pdfium(pdf, sample)
        t_challenger, n2, g_m = time_pdfminer(pdf, sample)
        label = f"{pdf.parent.name}/{pdf.name}"
        ratio = t_challenger / t_incumbent if t_incumbent else float("inf")
        print(f"{label:<48} {total:>6} {t_incumbent:>9.2f} {t_challenger:>11.2f} {ratio:>6.1f}x")
        print(
            f"  sampled {n}/{n2} pages; glyphs pdfium={g_i} pdfminer={g_m}; "
            f"projected full doc: pdfium {t_incumbent / n * total:.1f}s "
            f"pdfminer {t_challenger / n2 * total:.1f}s "
            f"(pyodide {t_challenger / n2 * total * WASM_PENALTY[0]:.0f}-"
            f"{t_challenger / n2 * total * WASM_PENALTY[1]:.0f}s)"
        )


if __name__ == "__main__":
    main()
