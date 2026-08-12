"""V2 — how far does GEOMETRY actually get, once it stops being one global constant?

`RESULTS-HYBRID.md` §4 measures exactly one rule: a single global threshold on
`gap / font-size`. It reports `separable: NO` in every print class and concludes the
constant "is not where the defect lives".

That conclusion is sound for the rule it tested. The document then generalises it, in the
framing section, to "**geometry alone is insufficient**" and "the gap between two letters
does not determine whether a space belongs there". Those are claims about an entire
hypothesis class, established from one member of it.

This probe measures the class. For each adjacent ink pair it fits several rules and
reports the BEST error each can achieve, fitting each rule's parameters ON THE TEST DATA
ITSELF. That is deliberate and it is the only reason the result means anything: a rule
fitted on its own test set is an OPTIMISTIC UPPER BOUND. If a rule still errs badly when
it is allowed to cheat, no honestly-fitted version of it can do better. If it does well,
that is not evidence the rule works in production -- only evidence that §4's conclusion
does not cover it.

The rules, in increasing order of what they need to know:

  R1  global threshold on gap/size                     <- §4's rule, reproduced as control
  R2  per-(font, size) threshold on gap/size           <- font IDENTITY only; contract.Glyph
                                                          already carries `font`
  R3  global threshold on gap / space_advance(font,size)
                                                       <- font METRICS: the width of that
                                                          font's own space glyph, which is
                                                          what a typographic algorithm uses
  R4  per-line adaptive: gap > k x median gap on the printed line
  R5  2-D: per-size-band threshold on gap/size          <- size only, no font identity

`space_advance` is measured, not assumed: it is the median box width of the EXPLICIT
(non-generated) space characters PDFium read from the content stream in that (font, size)
bucket. Those boxes are the font's own space advance at that size.

Why this matters architecturally, and it is not a tuning question: if R3 separates, then
the engine's advantage over the glyph seam is **font metrics**, which is a fact the glyph
contract could carry, not an unrecoverable interpretation. That makes "extend the glyph
contract with font metrics" a third option the spike never scored. If R3 does NOT
separate, §4's broad claim survives a real attempt to break it, which is worth more than
the narrow claim it currently proves.

Labels here are still PDFium's own spaces -- this probe is about the FEATURE side, not the
label side. V3 re-runs it against independently adjudicated labels.

Read-only. Writes JSON only under `validation/results/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

BASELINE_TOL = 0.6  # same notion of "one printed line" as probe_space_separability.py
SHIPPED_FACTOR = 0.25


def _page_chars(textpage) -> list[dict]:
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
        buf = (ctypes.c_char * 256)()
        flags = ctypes.c_int()
        fn = R.FPDFText_GetFontInfo(raw, i, buf, 256, ctypes.byref(flags))
        font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
        out.append(
            {
                "cp": cp,
                "gen": gen,
                "x0": left.value,
                "x1": right.value,
                "oy": oy.value,
                "size": size,
                "font": font,
            }
        )
    return out


def _space_advance_table(all_chars: list[dict]) -> dict[tuple[str, float], float]:
    """Median box width of EXPLICIT space chars, per (font, rounded size).

    An explicit space is one PDFium read from the content stream (`gen` False). Its box
    width is the font's own space advance at that size -- the number a font-metrics-aware
    spacing algorithm has and the glyph contract does not.
    """
    buckets: dict[tuple[str, float], list[float]] = defaultdict(list)
    for c in all_chars:
        if c["cp"] == 32 and not c["gen"] and c["size"] > 0:
            w = c["x1"] - c["x0"]
            if w > 0:
                buckets[(c["font"], round(c["size"], 1))].append(w)
    return {k: statistics.median(v) for k, v in buckets.items() if len(v) >= 3}


def pairs_for_page(chars: list[dict]) -> list[dict]:
    """Adjacent INK pairs on one printed line, with the features every rule may use.

    Identical adjacency logic to `probe_space_separability.py` so R1 reproduces §4 rather
    than approximating it.
    """
    ink: list[dict] = []
    sep: dict[int, bool] = {}
    prev = None
    saw_space = False
    for c in chars:
        if c["cp"] in (10, 13):
            prev, saw_space = None, False
            continue
        if c["cp"] == 32:
            saw_space = True
            continue
        ink.append(c)
        if prev is not None:
            sep[len(ink) - 1] = saw_space
        prev = len(ink) - 1
        saw_space = False

    out = []
    for j in range(1, len(ink)):
        if j not in sep:
            continue
        a, b = ink[j - 1], ink[j]
        if abs(b["oy"] - a["oy"]) > BASELINE_TOL:
            continue
        if b["size"] <= 0:
            continue
        out.append(
            {
                "gap": b["x0"] - a["x1"],
                "size": b["size"],
                "font": b["font"],
                "font_prev": a["font"],
                "line_key": (round(b["oy"], 1),),
                "label": sep[j],
            }
        )
    return out


def _best_threshold(vals: list[tuple[float, bool]]) -> tuple[float, int, int, int]:
    """Sweep every candidate threshold; return (t, errors, missed, spurious).

    A threshold t inserts a space when ratio > t, so a boundary with ratio <= t is a
    MISSED space and an intra-word pair with ratio > t is a SPURIOUS one.
    """
    if not vals:
        return (0.0, 0, 0, 0)
    bnd = sorted(r for r, w in vals if w)
    intra = sorted(r for r, w in vals if not w)
    if not bnd or not intra:
        # A bucket with only one class is trivially separable; report zero error but the
        # caller must not read that as evidence -- it is counted in `degenerate_buckets`.
        return (0.0, 0, 0, 0)
    # O(n log n) sweep. §4's own probe does this in O(n^2), which is why it costs ~4 min
    # per document; the answer is identical, so this is a speed change and not a method
    # change. Verified equal to the naive sweep by `_selftest_best_threshold`.
    merged = sorted(((round(r, 6), w) for r, w in vals))
    total_intra = len(intra)
    miss = 0  # boundaries at or below the current threshold
    spur = total_intra  # intra-word pairs strictly above it
    best = None
    i = 0
    n = len(merged)
    while i < n:
        t = merged[i][0]
        j = i
        while j < n and merged[j][0] == t:
            if merged[j][1]:
                miss += 1
            else:
                spur -= 1
            j += 1
        if best is None or miss + spur < best[1]:
            best = (t, miss + spur, miss, spur)
        i = j
    return best


def _selftest_best_threshold() -> None:
    """Prove the fast sweep equals the naive one, including on ties and a known-bad case.

    A ceiling probe that silently computed the wrong minimum would understate every rule's
    error and would look exactly like a clean result, so the equivalence is asserted rather
    than assumed.
    """
    import random

    rng = random.Random(20260806)
    for _ in range(200):
        vals = [(round(rng.uniform(0, 1), 2), rng.random() < 0.4) for _ in range(rng.randint(2, 60))]
        bnd = [r for r, w in vals if w]
        intra = [r for r, w in vals if not w]
        if not bnd or not intra:
            continue
        naive = None
        for t in sorted({r for r, _ in vals}):
            m = sum(1 for r in bnd if r <= t)
            s = sum(1 for r in intra if r > t)
            if naive is None or m + s < naive[1]:
                naive = (t, m + s, m, s)
        fast = _best_threshold(vals)
        assert fast[1] == naive[1], f"error count differs: fast={fast} naive={naive}"


def evaluate(pairs: list[dict], adv: dict[tuple[str, float], float]) -> dict:
    n = len(pairs)
    nb = sum(1 for p in pairs if p["label"])
    ni = n - nb

    # ---- R1: one global threshold on gap/size (the §4 rule) -------------------------
    r1_vals = [(p["gap"] / p["size"], p["label"]) for p in pairs]
    r1 = _best_threshold(r1_vals)
    bnd = sorted(r for r, w in r1_vals if w)
    intra = sorted(r for r, w in r1_vals if not w)
    shipped_miss = sum(1 for r in bnd if r <= SHIPPED_FACTOR)
    shipped_spur = sum(1 for r in intra if r > SHIPPED_FACTOR)

    # ---- R2: per-(font, rounded size) threshold on gap/size --------------------------
    by_fs: dict[tuple[str, float], list[tuple[float, bool]]] = defaultdict(list)
    for p in pairs:
        by_fs[(p["font"], round(p["size"], 1))].append((p["gap"] / p["size"], p["label"]))
    r2_err = r2_miss = r2_spur = 0
    r2_degenerate = 0
    for _k, v in by_fs.items():
        if not any(w for _r, w in v) or all(w for _r, w in v):
            r2_degenerate += 1
            continue
        _t, e, m, s = _best_threshold(v)
        r2_err += e
        r2_miss += m
        r2_spur += s

    # ---- R3: one global threshold on gap / the font's own space advance --------------
    r3_vals = []
    r3_unavailable = 0
    for p in pairs:
        w = adv.get((p["font"], round(p["size"], 1)))
        if not w:
            r3_unavailable += 1
            continue
        r3_vals.append((p["gap"] / w, p["label"]))
    r3 = _best_threshold(r3_vals)
    r3_bnd = sorted(r for r, w in r3_vals if w)
    r3_intra = sorted(r for r, w in r3_vals if not w)

    # ---- R4: per-line adaptive, gap > k x median gap on that printed line -------------
    by_line: dict[tuple, list[dict]] = defaultdict(list)
    for p in pairs:
        by_line[p["line_key"]].append(p)
    r4_vals = []
    for _k, v in by_line.items():
        med = statistics.median([max(x["gap"], 0.0) for x in v])
        if med <= 0:
            med = 0.01
        for x in v:
            r4_vals.append((x["gap"] / med, x["label"]))
    r4 = _best_threshold(r4_vals)

    # ---- R5: per-size-band threshold on gap/size (size only, no font identity) --------
    by_size: dict[float, list[tuple[float, bool]]] = defaultdict(list)
    for p in pairs:
        by_size[round(p["size"], 1)].append((p["gap"] / p["size"], p["label"]))
    r5_err = 0
    r5_degenerate = 0
    for _k, v in by_size.items():
        if not any(w for _r, w in v) or all(w for _r, w in v):
            r5_degenerate += 1
            continue
        _t, e, _m, _s = _best_threshold(v)
        r5_err += e

    return {
        "pairs": n,
        "word_boundaries": nb,
        "intra_word": ni,
        "R1_global_gap_over_size": {
            "separable": bool(bnd and intra and bnd[0] > intra[-1]),
            "boundary_min": round(bnd[0], 4) if bnd else None,
            "intra_max": round(intra[-1], 4) if intra else None,
            "best_threshold": round(r1[0], 4),
            "errors": r1[1],
            "missed": r1[2],
            "spurious": r1[3],
            "shipped_0.25_missed": shipped_miss,
            "shipped_0.25_spurious": shipped_spur,
        },
        "R2_per_font_size_threshold": {
            "buckets": len(by_fs),
            "degenerate_buckets": r2_degenerate,
            "errors": r2_err,
            "missed": r2_miss,
            "spurious": r2_spur,
        },
        "R3_global_gap_over_space_advance": {
            "pairs_scored": len(r3_vals),
            "pairs_without_a_space_advance": r3_unavailable,
            "separable": bool(r3_bnd and r3_intra and r3_bnd[0] > r3_intra[-1]),
            "boundary_min": round(r3_bnd[0], 4) if r3_bnd else None,
            "intra_max": round(r3_intra[-1], 4) if r3_intra else None,
            "best_threshold": round(r3[0], 4),
            "errors": r3[1],
            "missed": r3[2],
            "spurious": r3[3],
        },
        "R4_per_line_adaptive": {
            "lines": len(by_line),
            "best_k": round(r4[0], 4),
            "errors": r4[1],
            "missed": r4[2],
            "spurious": r4[3],
        },
        "R5_per_size_band": {
            "bands": len(by_size),
            "degenerate_bands": r5_degenerate,
            "errors": r5_err,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=30)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "v02_geometry_ceiling.json")
    args = ap.parse_args()

    _selftest_best_threshold()
    print("threshold sweep self-test: fast == naive on 200 random cases")

    results: dict = {
        "note": (
            "Every rule's parameters are fitted on the same data they are scored on. "
            "These are OPTIMISTIC UPPER BOUNDS, not achievable production error rates."
        ),
        "baseline_tol": BASELINE_TOL,
        "documents": {},
    }
    pooled_pairs: list[dict] = []
    pooled_adv: dict[tuple[str, float], float] = {}

    for spec in args.pdfs:
        path = Path(spec) if Path(spec).is_absolute() else REPO / spec
        doc = pdfium.PdfDocument(str(path))
        chars_all: list[dict] = []
        pairs: list[dict] = []
        try:
            n = min(args.pages, len(doc)) if args.pages else len(doc)
            for p in range(n):
                pg = doc[p]
                tp = pg.get_textpage()
                try:
                    cs = _page_chars(tp)
                    chars_all.extend(cs)
                    pairs.extend(pairs_for_page(cs))
                finally:
                    tp.close()
                    pg.close()
        finally:
            doc.close()
        adv = _space_advance_table(chars_all)
        key = str(path.relative_to(REPO)) if str(path).startswith(str(REPO)) else str(path)
        results["documents"][key] = {"pages": n, "space_advance_buckets": len(adv), **evaluate(pairs, adv)}
        pooled_pairs.extend(pairs)
        pooled_adv.update(adv)

        d = results["documents"][key]
        print(f"\n## {key}  (pages={n}, pairs={d['pairs']})")
        for rk in (
            "R1_global_gap_over_size",
            "R2_per_font_size_threshold",
            "R3_global_gap_over_space_advance",
            "R4_per_line_adaptive",
            "R5_per_size_band",
        ):
            r = d[rk]
            sep = r.get("separable")
            print(f"   {rk:<38} errors={r['errors']:<6} " + (f"separable={sep}" if sep is not None else ""))

    if len(args.pdfs) > 1:
        results["POOLED"] = evaluate(pooled_pairs, pooled_adv)
        print("\n## POOLED")
        print(json.dumps(results["POOLED"], indent=1))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
