"""V3 — is PDFium's word-space decision recoverable from glyph-layer data?

`RESULTS-HYBRID.md` frames the architectural claim like this:

    "the engine is not applying a better-tuned version of the same rule; it is deciding
     with information the glyph stream does not carry"

and attributes the decision to "the encoding, the text-object structure, and the font's
own metrics".

PDFium's rule is public. From `core/fpdftext/cpdf_textpage.cpp` @ main:

    float NormalizeThreshold(float threshold, int t1, int t2, int t3) {
      if (threshold < t1) return threshold / 2.0f;
      if (threshold < t2) return threshold / 4.0f;
      if (threshold < t3) return threshold / 5.0f;
      return threshold / 6.0f;
    }

    bool GenerateSpace(const CFX_PointF& pos, float last_pos, float this_width,
                       float last_width, float threshold) {
      if (fabs(last_pos + last_width - pos.x) <= threshold) return false;
      float threshold_pos = threshold + last_width;
      float pos_difference = pos.x - last_pos;
      if (fabs(pos_difference) > threshold_pos) return true;
      if (pos.x < 0 && -threshold_pos > pos_difference) return true;
      return pos_difference > this_width + last_width;
    }

    int nLastWidth = GetCharWidth(prev_item.char_code_, prev_font);
    float last_width = fabs(nLastWidth * prev_font_size / 1000);
    int nThisWidth = GetCharWidth(item.char_code_, this_font);
    float this_width = fabs(nThisWidth * this_font_size / 1000);
    float threshold2 = NormalizeThreshold(max(nLastWidth, nThisWidth), 400, 700, 800);
    threshold2 *= fabs(font_size);      // of whichever char was wider
    threshold2 /= 1000;

Two facts follow that the spike's framing does not reflect:

  * The decision is a deterministic function of **pen origins** and **font advance
    widths**. It reads no encoding and no glyph semantics. It is a per-pair adaptive
    geometric threshold -- the same SHAPE as `_SPACE_FACTOR`, with the constant replaced
    by a step function of the adjacent characters' advances.
  * `ProcessInsertObject` runs at **text-object boundaries**. So the rule is gated on
    structure, and the gate is the part of the claim that is actually load-bearing.

What the glyph contract discards is therefore three specific FACTS, not an interpretation:

  1. the pen origin (`FPDFText_GetCharOrigin`) -- `contract.Glyph` carries the INK box, so
     the shipped rule measures ink-edge to ink-edge, never pen to pen;
  2. the font advance width -- a font metric, not derivable from an ink box;
  3. the text-object identity -- which, as G0 below tests, is carried by the text matrix
     the backend already reads and already throws away everything of except `mat.f`.

THE RULES SCORED

  G0  diagnostic: do PDFium's spaces coincide with text-object boundaries at all?
  G1  the shipped rule: ink-gap / size > 0.25                              (control)
  G2  PDFium's rule, advances ESTIMATED from the glyph stream, gated on text-object change
  G3  PDFium's rule, advances read from the FONT (pdfminer `LTChar`), same gate
  G4  G3 without the text-object gate, to price the gate itself

Advances are carried in **em units** (advance / font size) throughout, so that a text
matrix scale cannot desynchronise pdfminer's numbers from PDFium's. The first version of
this probe joined them in points and scored ~82 % spurious on every document, which is
what a units mismatch looks like; that is recorded here rather than quietly fixed.

WHAT A GOOD SCORE WOULD AND WOULD NOT MEAN. Reproducing PDFium is not being right about
word boundaries -- V4/V5 test that with independent labels. This probe answers only
whether the decision is RECOVERABLE from glyph-level facts, which is what the "geometry
alone is insufficient" sentence claims it is not.

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

BASELINE_TOL = 0.6
SHIPPED_FACTOR = 0.25
_OBJ_EPS = 1e-4  # a text-object origin is exact; this only absorbs float round-tripping


def normalize_threshold(threshold: float, t1: int = 400, t2: int = 700, t3: int = 800) -> float:
    """Verbatim port of PDFium's NormalizeThreshold."""
    if threshold < t1:
        return threshold / 2.0
    if threshold < t2:
        return threshold / 4.0
    if threshold < t3:
        return threshold / 5.0
    return threshold / 6.0


def generate_space(pos_x: float, last_pos: float, this_width: float, last_width: float, threshold: float) -> bool:
    """Verbatim port of PDFium's GenerateSpace."""
    if abs(last_pos + last_width - pos_x) <= threshold:
        return False
    threshold_pos = threshold + last_width
    pos_difference = pos_x - last_pos
    if abs(pos_difference) > threshold_pos:
        return True
    if pos_x < 0 and -threshold_pos > pos_difference:
        return True
    return pos_difference > this_width + last_width


def _page_chars(textpage) -> list[dict]:
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out = []
    buf = (ctypes.c_char * 256)()
    flags = ctypes.c_int()
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
        fn = R.FPDFText_GetFontInfo(raw, i, buf, 256, ctypes.byref(flags))
        font = bytes(buf[: max(fn - 1, 0)]).decode("utf-8", "replace") if fn > 0 else ""
        out.append(
            {
                "cp": cp,
                "gen": R.FPDFText_IsGenerated(raw, i) == 1,
                "x0": left.value,
                "x1": right.value,
                "ox": ox.value,
                "oy": oy.value,
                "size": R.FPDFText_GetFontSize(raw, i) * scale,
                "font": font,
                # mat.e / mat.f are the TEXT-OBJECT origin, shared by every character of
                # one object. `pdfium_native.py` already reads mat.f as the baseline and
                # discards mat.e, so this is a fact the contract sees and drops.
                "obj": (round(mat.e, 4), round(mat.f, 4)),
            }
        )
    return out


def estimate_advances_em(all_chars: list[dict], pct: int = 5) -> dict[tuple[str, int], float]:
    """Advance per (font, codepoint) in EM units, estimated from the glyph stream alone.

    For two characters set tight against one another on a baseline, the difference of
    their pen origins is the first one's advance. Word gaps and TJ kerning only make that
    delta larger, so a low percentile recovers the advance without consulting the label.

    KNOWN LIMIT, and it is why `estimator_coverage` is reported: a character that never
    occurs word-internally has no tight observation, so its estimate stays inflated by a
    space width. Digits in a margin-number column are the clearest instance.
    """
    deltas: dict[tuple[str, int], list[float]] = defaultdict(list)
    prev = None
    for c in all_chars:
        if c["cp"] in (10, 13):
            prev = None
            continue
        if c["cp"] == 32 or c["gen"]:
            # A space's own origin is not a glyph advance; including it made the first
            # version of this estimator read `Y` as 0.25 pt wide.
            continue
        if prev is not None and abs(c["oy"] - prev["oy"]) <= BASELINE_TOL and prev["size"] > 0:
            d = (c["ox"] - prev["ox"]) / prev["size"]
            if d > 0:
                deltas[(prev["font"].split("+")[-1], prev["cp"])].append(d)
        prev = c
    out = {}
    for k, v in deltas.items():
        if len(v) < 5:
            continue
        v.sort()
        out[k] = v[max(0, (len(v) * pct) // 100)]
    return out


def true_advances_em(path: Path, pages: int) -> dict[tuple[str, int], float]:
    """Advance per (font, codepoint) in EM units, read from the font program via pdfminer.

    pdfminer builds each `LTChar` with `bbox = (0, descent+rise, adv, descent+rise+size)`
    before transforming it, so after transform `width / height` is the advance expressed
    in ems -- independent of both the font size and any text-matrix scale. Joining on that
    rather than on points is what fixes the units mismatch noted in the module docstring.
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    acc: dict[tuple[str, int], list[float]] = defaultdict(list)
    for pg in extract_pages(str(path), page_numbers=list(range(pages)), laparams=LAParams()):
        for o in walk(pg):
            if not isinstance(o, LTChar):
                continue
            t = o.get_text()
            if len(t) != 1 or o.height <= 0:
                continue
            acc[((o.fontname or "").split("+")[-1], ord(t))].append(abs(o.width) / o.height)
    return {k: statistics.median(v) for k, v in acc.items() if v}


def pairs_for_page(chars: list[dict]) -> list[dict]:
    """Adjacent ink pairs on one printed line, carrying pen origins and text-object ids."""
    ink: list[dict] = []
    sep: dict[int, bool] = {}
    gen_sep: dict[int, bool] = {}
    prev = None
    saw_space = False
    saw_generated_space = False
    for c in chars:
        if c["cp"] in (10, 13):
            prev, saw_space, saw_generated_space = None, False, False
            continue
        if c["cp"] == 32:
            saw_space = True
            saw_generated_space = saw_generated_space or c["gen"]
            continue
        ink.append(c)
        if prev is not None:
            sep[len(ink) - 1] = saw_space
            gen_sep[len(ink) - 1] = saw_generated_space
        prev = len(ink) - 1
        saw_space = False
        saw_generated_space = False

    out = []
    for j in range(1, len(ink)):
        if j not in sep:
            continue
        a, b = ink[j - 1], ink[j]
        if abs(b["oy"] - a["oy"]) > BASELINE_TOL or b["size"] <= 0:
            continue
        out.append(
            {
                "a": a,
                "b": b,
                "label": sep[j],
                # Provenance of the label, and the whole reason this probe can be trusted.
                # An EXPLICIT space occupies an advance width of its own, so recovering it
                # from pen origins is close to tautological -- the gap simply IS the space
                # glyph. The load-bearing subset is the GENERATED spaces, where no such
                # glyph exists in the content stream and the engine inferred the boundary.
                "generated": gen_sep.get(j, False),
                "obj_change": (abs(a["obj"][0] - b["obj"][0]) > _OBJ_EPS or abs(a["obj"][1] - b["obj"][1]) > _OBJ_EPS),
            }
        )
    return out


def g0_object_boundary(pairs: list[dict]) -> dict:
    """Do PDFium's word spaces line up with text-object boundaries?

    If every boundary sits at an object change, the gate is necessary and the glyph
    contract's loss of `mat.e` matters. If word boundaries occur freely inside an object,
    the gate is not what is doing the work.
    """
    b_change = sum(1 for p in pairs if p["label"] and p["obj_change"])
    b_same = sum(1 for p in pairs if p["label"] and not p["obj_change"])
    i_change = sum(1 for p in pairs if not p["label"] and p["obj_change"])
    i_same = sum(1 for p in pairs if not p["label"] and not p["obj_change"])
    return {
        "boundary_at_object_change": b_change,
        "boundary_inside_one_object": b_same,
        "intra_word_at_object_change": i_change,
        "intra_word_inside_one_object": i_same,
        "object_change_alone_errors": b_same + i_change,
        "object_change_alone_error_rate": (round((b_same + i_change) / len(pairs), 6) if pairs else None),
    }


def _score(pairs, predict) -> dict:
    tp = fp = tn = fn = 0
    unavailable = 0
    # Broken out by label provenance: the generated subset is the one that carries the
    # claim, because explicit spaces are recoverable from an advance almost by definition.
    gen_tp = gen_fn = exp_tp = exp_fn = 0
    samples: list[dict] = []
    for p in pairs:
        pred = predict(p)
        if pred is None:
            unavailable += 1
            continue
        if pred and p["label"]:
            tp += 1
            if p["generated"]:
                gen_tp += 1
            else:
                exp_tp += 1
        elif pred and not p["label"]:
            fp += 1
            if len(samples) < 10:
                samples.append({"kind": "spurious", "prev": chr(p["a"]["cp"]), "next": chr(p["b"]["cp"])})
        elif not pred and p["label"]:
            fn += 1
            if p["generated"]:
                gen_fn += 1
            else:
                exp_fn += 1
            if len(samples) < 10:
                samples.append(
                    {
                        "kind": "missed",
                        "generated": p["generated"],
                        "prev": chr(p["a"]["cp"]),
                        "next": chr(p["b"]["cp"]),
                    }
                )
        else:
            tn += 1
    scored = tp + fp + tn + fn
    return {
        "pairs_scored": scored,
        "pairs_unavailable": unavailable,
        "missed": fn,
        "spurious": fp,
        "errors": fp + fn,
        "error_rate": round((fp + fn) / scored, 6) if scored else None,
        "boundary_recall": round(tp / (tp + fn), 6) if (tp + fn) else None,
        "generated_boundaries": gen_tp + gen_fn,
        "generated_recall": round(gen_tp / (gen_tp + gen_fn), 6) if (gen_tp + gen_fn) else None,
        "explicit_boundaries": exp_tp + exp_fn,
        "explicit_recall": round(exp_tp / (exp_tp + exp_fn), 6) if (exp_tp + exp_fn) else None,
        "samples": samples,
    }


def _pdfium_predictor(adv: dict[tuple[str, int], float], gate: bool):
    def predict(p):
        a, b = p["a"], p["b"]
        la_em = adv.get((a["font"].split("+")[-1], a["cp"]))
        ta_em = adv.get((b["font"].split("+")[-1], b["cp"]))
        if la_em is None or ta_em is None:
            return None
        if gate and not p["obj_change"]:
            # Inside one text object PDFium never calls ProcessInsertObject, so it cannot
            # generate a space there; any space present was read from the stream.
            return False
        n_last = la_em * 1000.0
        n_this = ta_em * 1000.0
        thr = normalize_threshold(max(n_last, n_this))
        thr *= a["size"] if n_last >= n_this else b["size"]
        thr /= 1000.0
        return generate_space(b["ox"], a["ox"], ta_em * b["size"], la_em * a["size"], thr)

    return predict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "v03_pdfium_rule_from_glyphs.json")
    args = ap.parse_args()

    results: dict = {
        "pdfium_rule_source": "core/fpdftext/cpdf_textpage.cpp @ main (GenerateSpace + NormalizeThreshold)",
        "advance_units": "em (advance / font size), so a text-matrix scale cannot desynchronise the two sources",
        "documents": {},
    }
    for spec in args.pdfs:
        path = Path(spec) if Path(spec).is_absolute() else REPO / spec
        doc = pdfium.PdfDocument(str(path))
        chars_all: list[dict] = []
        pairs: list[dict] = []
        try:
            n = min(args.pages, len(doc))
            for p in range(n):
                pg = doc[p]
                tpg = pg.get_textpage()
                try:
                    cs = _page_chars(tpg)
                    chars_all.extend(cs)
                    pairs.extend(pairs_for_page(cs))
                finally:
                    tpg.close()
                    pg.close()
        finally:
            doc.close()

        est = estimate_advances_em(chars_all)
        try:
            tru = true_advances_em(path, n)
            tru_err = None
        except Exception as exc:  # noqa: BLE001
            tru, tru_err = {}, f"{type(exc).__name__}: {exc}"

        def shipped(p):
            return (p["b"]["x0"] - p["a"]["x1"]) > SHIPPED_FACTOR * p["b"]["size"]

        key = str(path.relative_to(REPO))
        results["documents"][key] = {
            "pages": n,
            "pairs": len(pairs),
            "word_boundaries": sum(1 for p in pairs if p["label"]),
            "advance_keys_estimated": len(est),
            "advance_keys_from_font": len(tru),
            "true_advance_error": tru_err,
            "G0_object_boundary": g0_object_boundary(pairs),
            "G1_shipped_ink_gap_0.25": _score(pairs, shipped),
            "G2_pdfium_rule_estimated_advances": _score(pairs, _pdfium_predictor(est, gate=True)),
            "G3_pdfium_rule_true_advances": _score(pairs, _pdfium_predictor(tru, gate=True)) if tru else None,
            "G4_pdfium_rule_true_advances_no_gate": _score(pairs, _pdfium_predictor(tru, gate=False)) if tru else None,
            # Negative control. If G4 scores near zero because the rule is somehow
            # tautological rather than because the advances are right, then corrupting the
            # advances by 25 % will not hurt it. A check that has never produced a
            # negative result cannot distinguish a real fit from a degenerate one.
            "G5_negative_control_advances_x1.25": (
                _score(pairs, _pdfium_predictor({k: v * 1.25 for k, v in tru.items()}, gate=False)) if tru else None
            ),
            "G6_negative_control_advances_x0.75": (
                _score(pairs, _pdfium_predictor({k: v * 0.75 for k, v in tru.items()}, gate=False)) if tru else None
            ),
        }
        d = results["documents"][key]
        print(f"\n## {key}  (pages={n}, pairs={d['pairs']}, boundaries={d['word_boundaries']})")
        g0 = d["G0_object_boundary"]
        print(
            f"   G0 text-object gate: boundaries at an object change "
            f"{g0['boundary_at_object_change']}, inside one object {g0['boundary_inside_one_object']}; "
            f"gate-alone errors {g0['object_change_alone_errors']} ({g0['object_change_alone_error_rate']})"
        )
        for rk in (
            "G1_shipped_ink_gap_0.25",
            "G2_pdfium_rule_estimated_advances",
            "G3_pdfium_rule_true_advances",
            "G4_pdfium_rule_true_advances_no_gate",
            "G5_negative_control_advances_x1.25",
            "G6_negative_control_advances_x0.75",
        ):
            r = d[rk]
            if not r:
                print(f"   {rk:<40} unavailable")
                continue
            print(
                f"   {rk:<40} errors={r['errors']:<6} rate={r['error_rate']} "
                f"missed={r['missed']} spurious={r['spurious']} "
                f"recall(all)={r['boundary_recall']} "
                f"recall(GENERATED n={r['generated_boundaries']})={r['generated_recall']}"
            )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
