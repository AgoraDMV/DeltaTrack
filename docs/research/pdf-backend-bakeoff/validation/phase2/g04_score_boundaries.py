"""G4 — extended glyph vs hybrid on the frozen, independently adjudicated sample.

Scores the extended-glyph path against the SAME 72 pairs phase 1 froze, adjudicated from
rendered crops before any key was opened. Nothing about the sample is re-drawn: the pairs
are matched into `v04_key.json` by (document, page, prev x1, next x0), and the run asserts
that every one of the 72 is found. A silent partial match would flatter whichever path
happened to cover the easy pairs.

Columns:

    pdfium      the engine's own space decision (what the hybrid consumes)
    hybrid      identical to pdfium BY CONSTRUCTION -- reconstruct_hybrid applies no
                spacing rule of its own. Shown so the identity stays visible.
    glyph       the shipped rule, ink-gap > 0.25 x size
    extended    `reconstruct_extended.wants_space`, over pen origins and advances PDFium
                supplied about itself
    pdfminer    pdfminer's own decision, from phase 1

The adjudication is unchanged and is not reopened. The intra-adjudicator inconsistency
phase 1 found (six identical '1'|'1' stimuli answered 3-3) is carried forward with both of
its sensitivity analyses, still labelled post-hoc.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(HERE))

from reconstruct_extended import wants_space  # noqa: E402

P1 = HERE.parents[0] / "results"
BASELINE_TOL = 0.6
SHIPPED_FACTOR = 0.25
PATHS = ("pdfium", "hybrid", "glyph", "extended", "pdfminer")


def _page_pairs(path: Path, page_no: int) -> dict[tuple, dict]:
    """Adjacent ink pairs on one page, keyed by (prev_x1, next_x0) as v04 recorded them."""
    doc = pdfium.PdfDocument(str(path))
    try:
        pg = doc[page_no - 1]
        tp = pg.get_textpage()
        raw = tp.raw
        n = R.FPDFText_CountChars(raw)
        buf = (ctypes.c_char * 256)()
        flags = ctypes.c_int()
        objf: dict[int, tuple] = {}
        wcache: dict[tuple, float | None] = {}
        chars = []
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
            scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
            size = R.FPDFText_GetFontSize(raw, i) * scale
            fn = R.FPDFText_GetFontInfo(raw, i, buf, 256, ctypes.byref(flags))
            font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
            adv = None
            obj = R.FPDFText_GetTextObject(raw, i)
            k = ctypes.cast(obj, ctypes.c_void_p).value if obj else 0
            if k:
                if k not in objf:
                    f = R.FPDFTextObj_GetFont(obj)
                    objf[k] = (ctypes.cast(f, ctypes.c_void_p).value if f else 0, f)
                fk, fh = objf[k]
                if fk:
                    ck = (fk, cp)
                    if ck not in wcache:
                        w = ctypes.c_float()
                        ok = R.FPDFFont_GetGlyphWidth(fh, cp, 1000.0, ctypes.byref(w))
                        wcache[ck] = (w.value / 1000.0) if (ok and w.value > 0) else None
                    em = wcache[ck]
                    adv = None if em is None else em * size
            chars.append(
                {
                    "cp": cp,
                    "gen": R.FPDFText_IsGenerated(raw, i) == 1,
                    "x0": left.value,
                    "x1": right.value,
                    "ox": ox.value,
                    "oy": oy.value,
                    "size": size,
                    "font": font,
                    "adv": adv,
                    "upright": abs(mat.b) < 1e-6 and mat.a > 0,
                }
            )
        tp.close()
        pg.close()
    finally:
        doc.close()

    ink, sep = [], {}
    prev, saw = None, False
    for c in chars:
        if c["cp"] in (10, 13):
            prev, saw = None, False
            continue
        if c["cp"] == 32:
            saw = True
            continue
        if not c["upright"]:
            continue
        ink.append(c)
        if prev is not None:
            sep[len(ink) - 1] = saw
        prev = len(ink) - 1
        saw = False

    out: dict[tuple, dict] = {}
    for j in range(1, len(ink)):
        if j not in sep:
            continue
        a, b = ink[j - 1], ink[j]
        if abs(b["oy"] - a["oy"]) > BASELINE_TOL or b["size"] <= 0:
            continue
        out[(round(a["x1"], 2), round(b["x0"], 2))] = {"a": a, "b": b, "pdfium_space": sep[j]}
    return out


def _ext_glyph(c: dict):
    """Pack a char record into the extended contract's positional tuple."""
    return (
        c["cp"],
        c["x0"],
        0.0,
        c["x1"],
        0.0,
        c["oy"],
        c["size"],
        c["font"],
        c["upright"],
        c["ox"],
        c["adv"],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "g04_boundary_scores.json")
    args = ap.parse_args()

    key = json.loads((P1 / "v04_key.json").read_text())
    adj = json.loads((P1 / "v04_adjudication.json").read_text())["answers"]
    items = key["items"]

    by_doc_page: dict[tuple, list] = defaultdict(list)
    for it in items:
        by_doc_page[(it["doc"], it["page"])].append(it)

    decided: dict[str, dict] = {}
    missing = []
    for (rel, page_no), its in sorted(by_doc_page.items()):
        pairs = _page_pairs(REPO / rel, page_no)
        for it in its:
            k = (round(it["prev_x1"], 2), round(it["next_x0"], 2))
            p = pairs.get(k)
            if p is None:
                missing.append(it["id"])
                continue
            a, b = p["a"], p["b"]
            decided[it["id"]] = {
                "pdfium": p["pdfium_space"],
                "hybrid": p["pdfium_space"],
                "glyph": it["glyph_threshold_space"],
                "extended": wants_space(_ext_glyph(a), _ext_glyph(b)),
                "pdfminer": it["pdfminer_space"],
                "stratum": it["stratum"],
                "advance_missing": a["adv"] is None or b["adv"] is None,
            }

    # A partial match would silently change which pairs each path is scored on.
    assert not missing, f"{len(missing)} frozen pairs could not be re-located: {missing}"

    scored, unreadable = [], []
    for cid, a in adj.items():
        if a["v"] == "UNREADABLE":
            unreadable.append(cid)
            continue
        scored.append((cid, decided[cid], a["v"] == "BOUNDARY"))

    def tally(rows, path):
        tp = fp = tn = fn = na = 0
        for _cid, d, truth in rows:
            v = d[path]
            if v is None:
                na += 1
                continue
            if v and truth:
                tp += 1
            elif v:
                fp += 1
            elif truth:
                fn += 1
            else:
                tn += 1
        n = tp + fp + tn + fn
        return {
            "n": n,
            "not_available": na,
            "accuracy": round((tp + tn) / n, 4) if n else None,
            "missed_boundaries": fn,
            "spurious_boundaries": fp,
            "boundary_recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
        }

    # The inconsistent class phase 1 identified, carried forward unchanged.
    inconsistent = {"B30", "B32", "B36", "B42", "B55", "B60"}
    dropped = [r for r in scored if r[0] not in inconsistent]

    out = {
        "sample": "phase 1 frozen v04 sample, adjudication unchanged",
        "relocated": len(decided),
        "unreadable": unreadable,
        "overall": {p: tally(scored, p) for p in PATHS},
        "inconsistent_class_dropped_POST_HOC": {p: tally(dropped, p) for p in PATHS},
        "by_stratum": {},
        "extended_vs_pdfium_disagreements": [],
        "pairs_with_a_missing_advance": sum(1 for d in decided.values() if d["advance_missing"]),
    }
    by_s: dict[str, list] = defaultdict(list)
    for row in scored:
        by_s[row[1]["stratum"]].append(row)
    for s, rows in sorted(by_s.items()):
        out["by_stratum"][s] = {"n": len(rows), **{p: tally(rows, p)["accuracy"] for p in PATHS}}
    for cid, d, truth in scored:
        if d["extended"] != d["pdfium"]:
            out["extended_vs_pdfium_disagreements"].append(
                {
                    "id": cid,
                    "stratum": d["stratum"],
                    "truth": "BOUNDARY" if truth else "NO_BOUNDARY",
                    "pdfium": d["pdfium"],
                    "extended": d["extended"],
                    "glyph": d["glyph"],
                }
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))

    print(f"relocated {out['relocated']}/72 frozen pairs; {len(unreadable)} unreadable excluded\n")
    print(f"{'path':<10} {'acc':>7} {'missed':>7} {'spurious':>9} {'recall':>7}")
    for p in PATHS:
        t = out["overall"][p]
        print(
            f"{p:<10} {str(t['accuracy']):>7} {t['missed_boundaries']:>7} "
            f"{t['spurious_boundaries']:>9} {str(t['boundary_recall']):>7}"
        )
    print("\ninconsistent class dropped (POST-HOC):")
    for p in PATHS:
        t = out["inconsistent_class_dropped_POST_HOC"][p]
        print(
            f"{p:<10} {str(t['accuracy']):>7} {t['missed_boundaries']:>7} "
            f"{t['spurious_boundaries']:>9} {str(t['boundary_recall']):>7}"
        )
    print("\nby stratum:")
    print(f"{'stratum':<22} {'n':>3} " + " ".join(f"{p:>9}" for p in PATHS))
    for s, d in out["by_stratum"].items():
        print(f"{s:<22} {d['n']:>3} " + " ".join(f"{str(d[p]):>9}" for p in PATHS))
    print(f"\nextended vs pdfium disagreements ({len(out['extended_vs_pdfium_disagreements'])}):")
    for d in out["extended_vs_pdfium_disagreements"]:
        print(f"   {d['id']} {d['stratum']:<20} truth={d['truth']:<12} pdfium={d['pdfium']} extended={d['extended']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
