"""Probe: can ANY x-gap threshold separate word boundaries from intra-word kerning?

`_SPACE_FACTOR` is a single global constant: a space is inserted when
`x0(next) - x1(prev) > factor * size(next)`. That rule can only work if the ratio
distribution at real word boundaries sits entirely above the distribution inside words.

PDFium's own text page already knows the answer for each boundary, because it emits a
space character there -- either read from the content stream or GENERATED from font
metrics. So PDFium's stream is used here as the LABEL, and the geometry as the FEATURE.
This is not circular: the question is not "is PDFium right", it is "is the geometry the
neutral layer sees sufficient to recover the same decision with one constant".

Reported per document:
  * the ratio distribution for word boundaries and for intra-word adjacencies
  * the overlap region, and the best achievable error at any threshold
  * what the shipped 0.25 costs

Read-only. Imports nothing from `src/deltatrack`.

Run:
    .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_space_separability.py \
        tests/corpus/114-hr-2029/4_reported-in-senate.pdf --pages 40
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

SHIPPED_FACTOR = 0.25
# Same baseline tolerance the neutral layer uses, so adjacency is judged on the same
# notion of "one printed line" the reconstruction works with.
BASELINE_TOL = 0.6


def _chars(textpage, page_obj):
    """Per-index (cp, generated, x0, x1, origin_y, size) for one page, stream order."""
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out = []
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        if not R.FPDFText_GetCharBox(
            raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)
        ):
            continue
        ox, oy = ctypes.c_double(), ctypes.c_double()
        if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
            continue
        mat = R.FS_MATRIX()
        if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        gen = R.FPDFText_IsGenerated(raw, i) == 1
        size = R.FPDFText_GetFontSize(raw, i) * math.sqrt(mat.a * mat.a + mat.b * mat.b)
        out.append((cp, gen, left.value, right.value, oy.value, size))
    return out


def pairs_for_page(chars):
    """Yield (ratio, is_word_boundary) for adjacent INK pairs on the same printed line.

    Ink = a character PDFium placed with real geometry and that is not whitespace.
    A pair is a word boundary when the only things between the two ink characters are
    space characters (of either kind); it is intra-word when they are directly adjacent.
    Pairs separated by a line break are skipped -- the space rule never sees those.
    """
    ink = []  # (index_in_chars, x0, x1, origin_y, size)
    sep = {}  # (a,b) ink-pair -> saw a space between them
    prev = None
    saw_space = False
    for cp, _gen, x0, x1, oy, size in chars:
        if cp in (10, 13):  # line break: reset adjacency
            prev, saw_space = None, False
            continue
        if cp == 32:
            saw_space = True
            continue
        ink.append((x0, x1, oy, size))
        if prev is not None:
            sep[len(ink) - 1] = saw_space
        prev = len(ink) - 1
        saw_space = False

    for j in range(1, len(ink)):
        if j not in sep:
            continue
        px0, px1, poy, _ps = ink[j - 1]
        x0, _x1, oy, size = ink[j]
        if abs(oy - poy) > BASELINE_TOL:  # different printed lines
            continue
        if size <= 0:
            continue
        yield (x0 - px1) / size, sep[j]


def score(doc_pairs):
    """Best achievable threshold and its error count, plus what 0.25 costs."""
    bnd = sorted(r for r, w in doc_pairs if w)
    intra = sorted(r for r, w in doc_pairs if not w)
    if not bnd or not intra:
        return None
    # A threshold t inserts a space when ratio > t. Errors = boundaries with ratio <= t
    # (missed space) + intra-word with ratio > t (spurious space). Sweep every candidate.
    cands = sorted({round(r, 6) for r in bnd + intra})
    best = None
    for t in cands:
        miss = sum(1 for r in bnd if r <= t)
        spur = sum(1 for r in intra if r > t)
        if best is None or miss + spur < best[1]:
            best = (t, miss + spur, miss, spur)
    miss25 = sum(1 for r in bnd if r <= SHIPPED_FACTOR)
    spur25 = sum(1 for r in intra if r > SHIPPED_FACTOR)
    return {
        "word_boundaries": len(bnd),
        "intra_word": len(intra),
        "boundary_ratio_min": round(bnd[0], 4),
        "boundary_ratio_p01": round(bnd[max(0, len(bnd) // 100)], 4),
        "boundary_ratio_median": round(bnd[len(bnd) // 2], 4),
        "intra_ratio_median": round(intra[len(intra) // 2], 4),
        "intra_ratio_p99": round(intra[min(len(intra) - 1, len(intra) * 99 // 100)], 4),
        "intra_ratio_max": round(intra[-1], 4),
        "separable": bnd[0] > intra[-1],
        "overlap_boundaries_below_intra_max": sum(1 for r in bnd if r <= intra[-1]),
        "best_threshold": round(best[0], 4),
        "best_threshold_errors": best[1],
        "best_threshold_missed_spaces": best[2],
        "best_threshold_spurious_spaces": best[3],
        "shipped_0.25_missed_spaces": miss25,
        "shipped_0.25_spurious_spaces": spur25,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=None, help="limit pages per document")
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args()

    results = {}
    pooled: list[tuple[float, bool]] = []
    for path in args.pdfs:
        doc = pdfium.PdfDocument(path)
        pairs: list[tuple[float, bool]] = []
        try:
            n = len(doc) if args.pages is None else min(args.pages, len(doc))
            for p in range(n):
                pg = doc[p]
                tp = pg.get_textpage()
                try:
                    pairs.extend(pairs_for_page(_chars(tp, pg)))
                finally:
                    tp.close()
                    pg.close()
        finally:
            doc.close()
        s = score(pairs)
        results[path] = s
        pooled.extend(pairs)
        if s:
            print(f"\n## {path}  (pages={n})")
            print(f"  word boundaries={s['word_boundaries']}  intra-word={s['intra_word']}")
            print(
                f"  boundary gap/size:  min={s['boundary_ratio_min']}  "
                f"p01={s['boundary_ratio_p01']}  median={s['boundary_ratio_median']}"
            )
            print(
                f"  intra-word gap/size: median={s['intra_ratio_median']}  "
                f"p99={s['intra_ratio_p99']}  max={s['intra_ratio_max']}"
            )
            print(f"  linearly separable by ONE threshold: {s['separable']}")
            print(
                f"  best possible threshold {s['best_threshold']} still errs on "
                f"{s['best_threshold_errors']} pairs "
                f"({s['best_threshold_missed_spaces']} missed, {s['best_threshold_spurious_spaces']} spurious)"
            )
            print(
                f"  shipped 0.25 errs on {s['shipped_0.25_missed_spaces']} missed + "
                f"{s['shipped_0.25_spurious_spaces']} spurious"
            )

    if len(args.pdfs) > 1:
        s = score(pooled)
        results["__pooled__"] = s
        print(f"\n## POOLED over {len(args.pdfs)} documents")
        print(json.dumps(s, indent=1))

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
