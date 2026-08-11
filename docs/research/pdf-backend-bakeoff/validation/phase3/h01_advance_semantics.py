"""H1 — what does each backend's "advance" actually MEAN?

Phase 2's `g03_backend_fields.py` established that three backends expose a value which
predicts the next character's pen-origin delta. That is a necessary condition and it is
not a sufficient one: two different quantities can both satisfy it on a corpus that never
separates them. This probe reads the INSTALLED SOURCE of each library, states the
semantics the source implies, and then tests that statement by value.

WHAT IS BEING RE-OPENED, and why each is a real risk:

  pdfminer.six 20260107
      `g03` recorded "LTChar.adv is in EM units, not points". Read literally that is a
      claim about the library. `pdfminer/layout.py` says

          self.adv = textwidth * fontsize * scaling

      where `textwidth` is the font's em width. So `adv` is the advance in TEXT SPACE --
      em x Tf size x horizontal scaling -- and `pdfdevice.render_string_horizontal` uses
      exactly that value to walk the pen. It is "em units" only when the Tf size is 1,
      which is a property of the FILE, not of the library. This corpus may well be such a
      file, in which case g03's field choice is right and its stated reason is wrong --
      a distinction that matters because the reason is what a reader would carry to
      another corpus.

  PyMuPDF 1.28.0
      `g03` treats `get_texttrace()` chars[i][3] as an "advance box". PyMuPDF's own
      documentation calls it a bbox, so the review flagged this as possibly a character
      INK box, which would make `bbox[2] - origin[0]` an ink width and not a font metric.
      `jm_trace_text_span` in `pymupdf/__init__.py` decides it:

          adv = fz_advance_glyph(font, gid, wmode);  adv *= fsize
          x0 = char_orig.x;  x1 = x0 + adv
          char_bbox = fz_make_rect(x0, y0, x1, y1)

      i.e. the rectangle is built FROM the advance, at the origin. If that reading is
      right then bbox[0] == origin[0] exactly for every upright character, which an ink
      box can never satisfy (left side bearings are non-zero for nearly every glyph).

  PDFium 5.12.1 / 152.0.7947.0
      `FPDFFont_GetGlyphWidth(font, cp, size, &w)` is documented as the glyph's width at
      that size. Carried through unchanged; re-measured here so all three appear on one
      page under the same test.

THE NEGATIVE CONTROLS, because "it predicts the origin delta" is exactly the kind of
assertion that passes vacuously:

  C1  bbox[0] == origin[0] for PyMuPDF upright chars. Fails loudly if chars[3] is ink.
  C2  the same claim tested PER CHARACTER CLASS. A period's ink is about a third of its
      advance; if a backend's field tracked ink, the '.' and 'l' rows would separate from
      the 'm' and 'W' rows. Aggregate rates hide that; these do not.
  C3  pdfminer's `.adv` and `.width` are BOTH scored. If they agree, this corpus cannot
      distinguish them and the probe says so rather than crediting either.
  C4  the horizontal text-matrix scale is reported per document, which is the quantity
      that decides whether `.adv` is in points or in em.
  C5  PyMuPDF's trace advance is compared against `Font.glyph_advance` on the EMBEDDED
      font program, extracted from the PDF itself -- PyMuPDF checked against PyMuPDF, no
      other engine consulted.

Read-only. Writes JSON only under `validation/phase3/results/`.
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]

TOL_PT = 0.5
BASELINE_TOL = 0.6

# Every document the frozen phase-1 sample draws from, so the semantics are established on
# the same files the cross-backend scoring will use and not on one convenient page.
DOCUMENTS = [
    ("tests/corpus/114-hr-2029/4_reported-in-senate.pdf", 99),
    ("tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf", 26),
    ("tests/corpus/116-hr-1865/6_enrolled-bill.pdf", 1),
    ("tests/corpus/118-s-4795/1_reported-in-senate.pdf", 5),
    ("tests/data/CRPT-118srpt198.pdf", 1),
]

# C2's classes. Narrow ink / wide advance on the left, ink ~= advance on the right.
INK_LIGHT = set(".,;:'`-il1jt ")
INK_HEAVY = set("mwMWHNOQ")


def _consistency(records: list[dict], field: str) -> dict:
    """Does `field` predict the next character's pen-origin delta on the same line?

    Identical arithmetic to g03 so the numbers are comparable, plus a per-class split.
    """
    ok = bad = 0
    per_class: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    samples = []
    for a, b in zip(records, records[1:]):
        if a["origin_x"] is None or b["origin_x"] is None or a.get(field) is None:
            continue
        if abs(a["origin_y"] - b["origin_y"]) > BASELINE_TOL:
            continue
        adv = a[field]
        delta = b["origin_x"] - a["origin_x"]
        if delta <= 0:
            continue
        if delta > adv + 1.5:
            continue
        hit = abs(delta - adv) <= TOL_PT
        ok, bad = (ok + hit, bad + (not hit))
        cls = "ink_light" if a["ch"] in INK_LIGHT else ("ink_heavy" if a["ch"] in INK_HEAVY else "other")
        per_class[cls][0 if hit else 1] += 1
        if not hit and len(samples) < 6:
            samples.append({"ch": a["ch"], field: round(adv, 3), "observed_delta": round(delta, 3)})
    n = ok + bad
    return {
        "field": field,
        "tight_pairs_tested": n,
        "predicts_origin_delta": ok,
        "rate": round(ok / n, 4) if n else None,
        "by_ink_class": {
            k: {"n": v[0] + v[1], "rate": round(v[0] / (v[0] + v[1]), 4) if (v[0] + v[1]) else None}
            for k, v in sorted(per_class.items())
        },
        "mismatch_samples": samples,
    }


# --------------------------------------------------------------------------- pdfminer


def read_pdfminer(path: Path, page: int) -> dict:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    pg = next(iter(extract_pages(str(path), page_numbers=[page - 1], laparams=LAParams())))
    recs = []
    scales, ratios = [], []
    for o in walk(pg):
        if not isinstance(o, LTChar):
            continue
        t = o.get_text()
        if not t.strip():
            continue
        a, _b, _c, d, _e, f = o.matrix
        scales.append(a)
        if o.adv:
            ratios.append(abs(o.width) / o.adv)
        recs.append(
            {
                "ch": t,
                "origin_x": o.x0,
                "origin_y": f,
                "adv": o.adv,  # text-space advance
                "width": abs(o.width),  # transformed advance-box width = page space
                # The identity under test: transforming the text-space advance by the text
                # matrix must give the page-space advance, i.e. this column must match
                # `.width` exactly. If it does, `.adv` is not "wrong", it is unTRANSFORMED.
                "adv_x_matrix_a": o.adv * abs(a),
                "size": o.size,
                "matrix_a": a,
                "matrix_d": d,
            }
        )
    # C4: `.adv` is in points only when the horizontal text-matrix scale is 1.
    return {
        "records": recs,
        "text_matrix_a": {
            "distinct": sorted({round(s, 4) for s in scales})[:8],
            "median": round(statistics.median(scales), 4) if scales else None,
        },
        "width_over_adv": {
            "median": round(statistics.median(ratios), 4) if ratios else None,
            "min": round(min(ratios), 4) if ratios else None,
            "max": round(max(ratios), 4) if ratios else None,
        },
    }


# ---------------------------------------------------------------------------- PyMuPDF


def read_pymupdf(path: Path, page: int) -> dict:
    import pymupdf

    d = pymupdf.open(str(path))
    recs = []
    origin_is_bbox_x0 = []  # C1
    fonts_seen: dict[str, int] = {}
    try:
        pg = d[page - 1]
        for span in pg.get_texttrace():
            dirv = span.get("dir", (1.0, 0.0))
            upright = abs(dirv[1]) < 1e-6 and dirv[0] > 0
            fonts_seen[span.get("font", "")] = fonts_seen.get(span.get("font", ""), 0) + 1
            for ch in span.get("chars", []):
                ucs, _gid, origin, bbox = ch[0], ch[1], ch[2], ch[3]
                if not chr(ucs).strip():
                    continue
                if upright:
                    origin_is_bbox_x0.append(abs(bbox[0] - origin[0]))
                recs.append(
                    {
                        "ch": chr(ucs),
                        "gid": _gid,
                        "font": span.get("font", ""),
                        # MuPDF is y-DOWN. Sign is irrelevant to a same-line test, but the
                        # adapter has to flip it, so it is recorded here in raw form.
                        "origin_x": origin[0],
                        "origin_y": origin[1],
                        "advance_box": bbox[2] - origin[0],
                        "bbox_width": bbox[2] - bbox[0],
                        "size": span.get("size", 0.0),
                        "upright": upright,
                    }
                )
        # C5: check the trace advance against the EMBEDDED font's own metric, using only
        # PyMuPDF. Any font that cannot be instantiated is reported, not skipped silently.
        embedded = {}
        for f in pg.get_fonts(full=False):
            xref, basefont = f[0], f[3]
            # get_texttrace reports MuPDF's font name, which drops the six-letter subset
            # tag get_fonts keeps. Both spellings are registered so the join cannot fail
            # for a naming reason and then be read as "the metric disagrees".
            names = {basefont, basefont.split("+")[-1]}
            try:
                fd = d.extract_font(xref)
                buf = fd[3] if isinstance(fd, tuple) and len(fd) > 3 else None
                if not buf:
                    ent = {"instantiable": False, "why": "no embedded font program"}
                else:
                    ent = {"instantiable": True, "font": pymupdf.Font(fontbuffer=buf)}
            except Exception as exc:  # noqa: BLE001
                ent = {"instantiable": False, "why": f"{type(exc).__name__}: {exc}"}
            for nm in names:
                embedded[nm] = ent
    finally:
        d.close()

    checked = agree = 0
    disagree_samples = []
    for r in recs:
        base = r["font"]
        ent = embedded.get(base) or embedded.get(base.split("+")[-1])
        if not ent or not ent.get("instantiable"):
            continue
        fo = ent["font"]
        try:
            em = fo.glyph_advance(ord(r["ch"]))
        except Exception:  # noqa: BLE001
            continue
        if not em:
            continue
        checked += 1
        want = em * r["size"]
        if abs(want - r["advance_box"]) <= 0.05 * max(r["size"], 1.0):
            agree += 1
        elif len(disagree_samples) < 6:
            disagree_samples.append(
                {"ch": r["ch"], "font": base, "trace": round(r["advance_box"], 3), "Font.glyph_advance": round(want, 3)}
            )

    return {
        "records": recs,
        "C1_bbox_x0_equals_origin_x": {
            "upright_chars": len(origin_is_bbox_x0),
            "max_abs_difference_pt": round(max(origin_is_bbox_x0), 9) if origin_is_bbox_x0 else None,
            "verdict": (
                "advance box (built at the origin)"
                if origin_is_bbox_x0 and max(origin_is_bbox_x0) < 1e-6
                else "NOT an advance box -- reopen"
            ),
        },
        "C5_vs_embedded_Font_glyph_advance": {
            "fonts": {k: (v.get("why") or "instantiable") for k, v in embedded.items()},
            "chars_checked": checked,
            "agree_within_5pct_of_size": agree,
            "rate": round(agree / checked, 4) if checked else None,
            "disagree_samples": disagree_samples,
        },
        "spans_by_font": fonts_seen,
    }


# ----------------------------------------------------------------------------- PDFium


def read_pdfium(path: Path, page: int) -> dict:
    import pypdfium2 as pdfium
    import pypdfium2.raw as R

    doc = pdfium.PdfDocument(str(path))
    recs = []
    try:
        pg = doc[page - 1]
        tp = pg.get_textpage()
        raw = tp.raw
        objf: dict[int, tuple] = {}
        cache: dict[tuple, float | None] = {}
        for i in range(max(R.FPDFText_CountChars(raw), 0)):
            cp = R.FPDFText_GetUnicode(raw, i)
            if cp in (32, 10, 13):
                continue
            ox, oy = ctypes.c_double(), ctypes.c_double()
            if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
                continue
            left, right, bottom, top = (ctypes.c_double() for _ in range(4))
            R.FPDFText_GetCharBox(raw, i, *(ctypes.byref(v) for v in (left, right, bottom, top)))
            mat = R.FS_MATRIX()
            if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
                continue
            scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
            size = R.FPDFText_GetFontSize(raw, i) * scale
            obj = R.FPDFText_GetTextObject(raw, i)
            k = ctypes.cast(obj, ctypes.c_void_p).value if obj else 0
            adv = None
            if k:
                if k not in objf:
                    f = R.FPDFTextObj_GetFont(obj)
                    objf[k] = (ctypes.cast(f, ctypes.c_void_p).value if f else 0, f)
                fk, fh = objf[k]
                if fk:
                    ck = (fk, cp)
                    if ck not in cache:
                        w = ctypes.c_float()
                        okc = R.FPDFFont_GetGlyphWidth(fh, cp, 1000.0, ctypes.byref(w))
                        cache[ck] = (w.value / 1000.0) if (okc and w.value > 0) else None
                    adv = None if cache[ck] is None else cache[ck] * size
            recs.append(
                {
                    "ch": chr(cp),
                    "origin_x": ox.value,
                    "origin_y": oy.value,
                    "adv": adv,
                    "ink_width": right.value - left.value,
                    "size": size,
                }
            )
        tp.close()
        pg.close()
    finally:
        doc.close()
    return {"records": recs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HERE / "results" / "h01_advance_semantics.json")
    args = ap.parse_args()

    out: dict = {
        "question": "what quantity is each backend's candidate 'advance', per its INSTALLED source?",
        "test": "the value must predict the next character's pen-origin delta on tight settings (<=0.5 pt)",
        "documents": [],
    }

    for rel, page in DOCUMENTS:
        path = REPO / rel
        if not path.exists():
            print(f"  MISSING {rel}")
            continue
        print(f"\n=== {rel} page {page}")
        entry: dict = {"pdf": rel, "page": page, "backends": {}}

        pm = read_pdfminer(path, page)
        entry["backends"]["pdfminer.six"] = {
            "source_says": "layout.py: self.adv = textwidth * fontsize * scaling  (TEXT space)",
            "text_matrix_a": pm["text_matrix_a"],
            "width_over_adv": pm["width_over_adv"],
            "adv": _consistency(pm["records"], "adv"),
            "width": _consistency(pm["records"], "width"),
            "adv_x_matrix_a": _consistency(pm["records"], "adv_x_matrix_a"),
        }
        e = entry["backends"]["pdfminer.six"]
        # C3: if the two fields cannot be told apart on this file, say so.
        e["C3_fields_separable_here"] = bool(
            pm["width_over_adv"]["median"] is not None and abs(pm["width_over_adv"]["median"] - 1.0) > 0.01
        )
        print(f"  pdfminer  text-matrix a median={pm['text_matrix_a']['median']}  width/adv={pm['width_over_adv']}")
        print(
            f"            .adv   {e['adv']['predicts_origin_delta']}/{e['adv']['tight_pairs_tested']}"
            f" = {e['adv']['rate']}"
        )
        print(
            f"            .width {e['width']['predicts_origin_delta']}/{e['width']['tight_pairs_tested']}"
            f" = {e['width']['rate']}"
        )
        am = e["adv_x_matrix_a"]
        print(f"            .adv x matrix[0] {am['predicts_origin_delta']}/{am['tight_pairs_tested']} = {am['rate']}")

        mu = read_pymupdf(path, page)
        entry["backends"]["pymupdf"] = {
            "source_says": "jm_trace_text_span: adv = fz_advance_glyph(...)*fsize; x1 = origin.x + adv",
            "C1": mu["C1_bbox_x0_equals_origin_x"],
            "C5": mu["C5_vs_embedded_Font_glyph_advance"],
            "advance_box": _consistency(mu["records"], "advance_box"),
        }
        print(
            f"  pymupdf   C1 {mu['C1_bbox_x0_equals_origin_x']['verdict']}"
            f" (max |bbox.x0-origin.x| = {mu['C1_bbox_x0_equals_origin_x']['max_abs_difference_pt']})"
        )
        print(
            f"            C5 vs embedded Font.glyph_advance: {mu['C5_vs_embedded_Font_glyph_advance']['rate']}"
            f" over {mu['C5_vs_embedded_Font_glyph_advance']['chars_checked']}"
        )
        a = entry["backends"]["pymupdf"]["advance_box"]
        print(f"            advance box {a['predicts_origin_delta']}/{a['tight_pairs_tested']} = {a['rate']}")

        pf = read_pdfium(path, page)
        entry["backends"]["pdfium"] = {
            "source_says": "FPDFFont_GetGlyphWidth(font, unicode, size) -- font metric, reverse-mapped charcode",
            "adv": _consistency(pf["records"], "adv"),
            "ink_width_control": _consistency(pf["records"], "ink_width"),
        }
        p = entry["backends"]["pdfium"]
        print(
            f"  pdfium    glyph width {p['adv']['predicts_origin_delta']}/{p['adv']['tight_pairs_tested']}"
            f" = {p['adv']['rate']}"
        )
        # A control on the control: PDFium's INK width must NOT satisfy the same identity.
        # If it does, the test is not discriminating advances from ink at all.
        print(f"            ink-width control (must be LOW) = {p['ink_width_control']['rate']}")

        out["documents"].append(entry)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
