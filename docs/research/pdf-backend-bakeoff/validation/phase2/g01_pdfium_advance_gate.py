"""G1 — can PDFium supply its OWN advance widths through public API?

`validation/FINDINGS.md` §1 showed PDFium's word-space rule is pure geometry over pen
origins and font advance widths, and that a port of it reproduces the engine's decisions.
But that probe took the advance widths from **pdfminer**, which is a borrowed fact: it
proves the rule is recoverable *in principle*, not that a PDFium-backed extended-glyph
contract can be built. This probe removes the borrowing.

THE API PATH, and its one dangerous step:

    FPDFText_GetTextObject(text_page, i)   -> FPDF_PAGEOBJECT      [Experimental]
    FPDFTextObj_GetFont(obj)               -> FPDF_FONT            [Experimental]
    FPDFFont_GetGlyphWidth(font, g, sz, &w)                        [Experimental]

`FPDFFont_GetGlyphWidth`'s `glyph` parameter is documented only as "the glyph". The
implementation (`fpdfsdk/fpdf_edittext.cpp`) is:

    uint32_t charcode = pFont->CharCodeFromUnicode(static_cast<wchar_t>(glyph));
    ...
    *width = pFont->GetCharWidth(charcode) * font_size / 1000.f;

So the caller supplies a **Unicode codepoint**, and PDFium reverse-maps it to a charcode.
PDFium's own spacing rule does NOT do that -- `ProcessInsertObject` uses
`GetCharWidth(item.char_code_, font)`, the charcode straight from the content stream.

That asymmetry is the gate. A reverse map can fail or land on a different charcode for
subset fonts, symbolic encodings, and any glyph whose Unicode value is not what the stream
encoded -- and GPO's soft hyphen is exactly such a case, reported as U+0002 by the glyph
API. If the round trip is lossy, an extended-glyph contract cannot get PDFium's advances
from PDFium, and the design fails the gate on its own terms rather than on a score.

MEASURED HERE

  A  coverage: for how many characters does the whole chain return a width at all?
  B  the round-trip: which codepoints lose their width, and are they concentrated?
  C  agreement with the empirical advance visible in the glyph stream itself
     (low-percentile pen-origin delta), as a sanity check that the number is an ADVANCE
     and not something else. This is a cross-check, not a source.
  D  functional: does a port of GenerateSpace fed by THESE advances reproduce PDFium's own
     decisions as well as FINDINGS.md's version fed by pdfminer's? This is the test that
     decides the gate, because it is the thing the contract would have to do.
  E  cost: wall-clock against the plain glyph extraction, since the chain runs per
     character and `FPDFText_GetTextObject` is not a cheap accessor.

Read-only. Writes JSON only under `validation/phase2/results/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(HERE.parents[0]))

from v03_pdfium_rule_from_glyphs import generate_space, normalize_threshold  # noqa: E402

BASELINE_TOL = 0.6


def _page_records(textpage) -> list[dict]:
    """Per-character facts, INCLUDING the advance fetched through PDFium's own chain.

    The font handle is cached per text object: `FPDFText_GetTextObject` returns the same
    object for every character of a run, and re-walking it per character is the bulk of
    the cost measured in E.
    """
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out: list[dict] = []
    obj_font: dict[int, tuple] = {}
    width_cache: dict[tuple[int, int], float | None] = {}
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)
        ox, oy = ctypes.c_double(), ctypes.c_double()
        if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
            continue
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        R.FPDFText_GetCharBox(raw, i, ctypes.byref(left), ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top))
        mat = R.FS_MATRIX()
        if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
        eff_size = R.FPDFText_GetFontSize(raw, i) * scale

        obj = R.FPDFText_GetTextObject(raw, i)
        obj_key = ctypes.cast(obj, ctypes.c_void_p).value if obj else 0
        font_handle = None
        font_key = 0
        if obj_key:
            if obj_key not in obj_font:
                # The handle itself is cached, not its address: FPDFFont_GetGlyphWidth
                # takes an FPDF_FONT, and round-tripping it through c_void_p loses the
                # ctypes type. The address is kept only as a cache key.
                f = R.FPDFTextObj_GetFont(obj)
                obj_font[obj_key] = (ctypes.cast(f, ctypes.c_void_p).value if f else 0, f)
            font_key, font_handle = obj_font[obj_key]

        em_adv = None
        if font_key:
            ck = (font_key, cp)
            if ck not in width_cache:
                # font_size = 1000 makes the returned width the raw 1/1000-em advance,
                # i.e. GetCharWidth(charcode) itself, with no size arithmetic in between.
                w = ctypes.c_float()
                ok = R.FPDFFont_GetGlyphWidth(font_handle, cp, 1000.0, ctypes.byref(w))
                width_cache[ck] = (w.value / 1000.0) if ok else None
            em_adv = width_cache[ck]

        out.append(
            {
                "cp": cp,
                "gen": R.FPDFText_IsGenerated(raw, i) == 1,
                "ox": ox.value,
                "oy": oy.value,
                "x0": left.value,
                "x1": right.value,
                "size": eff_size,
                "em_adv": em_adv,
                "has_obj": bool(obj_key),
                "has_font": bool(font_key),
            }
        )
    return out


def _empirical_em_adv(pages: list[list[dict]], pct: int = 5) -> dict[int, float]:
    """C's cross-check: the tightest observed pen-origin delta per codepoint, in ems.

    Deliberately keyed on codepoint alone and pooled across fonts -- it exists only to
    answer "is the API returning an advance-shaped number", not to supply one.
    """
    d: dict[int, list[float]] = defaultdict(list)
    for chars in pages:
        prev = None
        for c in chars:
            if c["cp"] in (10, 13) or c["cp"] == 32 or c["gen"]:
                continue
            if prev is not None and abs(c["oy"] - prev["oy"]) <= BASELINE_TOL and prev["size"] > 0:
                v = (c["ox"] - prev["ox"]) / prev["size"]
                if v > 0:
                    d[prev["cp"]].append(v)
            prev = c
    out = {}
    for k, v in d.items():
        if len(v) >= 8:
            v.sort()
            out[k] = v[(len(v) * pct) // 100]
    return out


def _pairs(chars: list[dict]) -> list[dict]:
    ink, sep, gen = [], {}, {}
    prev, saw, saw_gen = None, False, False
    for c in chars:
        if c["cp"] in (10, 13):
            prev, saw, saw_gen = None, False, False
            continue
        if c["cp"] == 32:
            saw = True
            saw_gen = saw_gen or c["gen"]
            continue
        ink.append(c)
        if prev is not None:
            sep[len(ink) - 1] = saw
            gen[len(ink) - 1] = saw_gen
        prev = len(ink) - 1
        saw = saw_gen = False
    out = []
    for j in range(1, len(ink)):
        if j not in sep:
            continue
        a, b = ink[j - 1], ink[j]
        if abs(b["oy"] - a["oy"]) > BASELINE_TOL or b["size"] <= 0:
            continue
        out.append({"a": a, "b": b, "label": sep[j], "generated": gen[j]})
    return out


def _scale(v: float | None, k: float) -> float | None:
    """Perturb one advance for the negative control, preserving a missing value."""
    return None if v is None else v * k


def _score_rule(pairs: list[dict]) -> dict:
    """D: the GenerateSpace port, fed only by advances PDFium supplied about itself."""
    tp = fp = tn = fn = 0
    gen_tp = gen_fn = 0
    unavailable = 0
    for p in pairs:
        a, b = p["a"], p["b"]
        if a["em_adv"] is None or b["em_adv"] is None:
            unavailable += 1
            continue
        n_last, n_this = a["em_adv"] * 1000.0, b["em_adv"] * 1000.0
        thr = normalize_threshold(max(n_last, n_this))
        thr *= a["size"] if n_last >= n_this else b["size"]
        thr /= 1000.0
        pred = generate_space(b["ox"], a["ox"], b["em_adv"] * b["size"], a["em_adv"] * a["size"], thr)
        if pred and p["label"]:
            tp += 1
            gen_tp += 1 if p["generated"] else 0
        elif pred:
            fp += 1
        elif p["label"]:
            fn += 1
            gen_fn += 1 if p["generated"] else 0
        else:
            tn += 1
    n = tp + fp + tn + fn
    return {
        "pairs_scored": n,
        "pairs_unavailable": unavailable,
        "missed": fn,
        "spurious": fp,
        "errors": fp + fn,
        "error_rate": round((fp + fn) / n, 6) if n else None,
        "boundary_recall": round(tp / (tp + fn), 6) if (tp + fn) else None,
        "generated_recall": round(gen_tp / (gen_tp + gen_fn), 6) if (gen_tp + gen_fn) else None,
        "generated_boundaries": gen_tp + gen_fn,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "g01_pdfium_advance_gate.json")
    args = ap.parse_args()

    out: dict = {
        "api_path": [
            "FPDFText_GetTextObject (Experimental)",
            "FPDFTextObj_GetFont (Experimental)",
            "FPDFFont_GetGlyphWidth (Experimental)",
        ],
        "glyph_param_semantics": (
            "Unicode codepoint, reverse-mapped by CharCodeFromUnicode; PDFium's own spacing "
            "rule instead uses the content stream's charcode directly"
        ),
        "documents": {},
    }
    for spec in args.pdfs:
        path = Path(spec) if Path(spec).is_absolute() else REPO / spec
        doc = pdfium.PdfDocument(str(path))
        pages: list[list[dict]] = []
        t0 = time.perf_counter()
        try:
            n = min(args.pages, len(doc))
            for p in range(n):
                pg = doc[p]
                tpg = pg.get_textpage()
                try:
                    pages.append(_page_records(tpg))
                finally:
                    tpg.close()
                    pg.close()
        finally:
            doc.close()
        t_ext = time.perf_counter() - t0

        # E: the same pages without the advance chain, for the cost comparison.
        doc = pdfium.PdfDocument(str(path))
        t0 = time.perf_counter()
        try:
            for p in range(n):
                pg = doc[p]
                tpg = pg.get_textpage()
                try:
                    raw = tpg.raw
                    m = R.FPDFText_CountChars(raw)
                    for i in range(max(m, 0)):
                        R.FPDFText_GetUnicode(raw, i)
                        ox, oy = ctypes.c_double(), ctypes.c_double()
                        R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy))
                        mat = R.FS_MATRIX()
                        R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat))
                finally:
                    tpg.close()
                    pg.close()
        finally:
            doc.close()
        t_base = time.perf_counter() - t0

        all_chars = [c for pg in pages for c in pg]
        ink = [c for c in all_chars if c["cp"] not in (10, 13) and not c["gen"]]
        missing = [c for c in ink if c["em_adv"] is None]
        emp = _empirical_em_adv(pages)
        agree = [(c["em_adv"], emp[c["cp"]]) for c in ink if c["em_adv"] is not None and c["cp"] in emp]
        close = sum(1 for a, e in agree if abs(a - e) <= 0.06)

        pairs = [p for pg in pages for p in _pairs(pg)]
        key = str(path.relative_to(REPO))
        out["documents"][key] = {
            "pages": n,
            "A_ink_chars": len(ink),
            "A_with_text_object": sum(1 for c in ink if c["has_obj"]),
            "A_with_font": sum(1 for c in ink if c["has_font"]),
            "A_with_advance": len(ink) - len(missing),
            "A_advance_coverage": round((len(ink) - len(missing)) / len(ink), 6) if ink else None,
            "B_missing_by_codepoint": dict(Counter(hex(c["cp"]) for c in missing).most_common(12)),
            # A returned TRUE is not a returned ADVANCE. CharCodeFromUnicode yields 0 on a
            # failed reverse map and GetCharWidth(0) still answers, so a silent zero or a
            # default width would pass the coverage check above while carrying no
            # information. Counted explicitly, with the codepoints named.
            "B_zero_advance": sum(1 for c in ink if c["em_adv"] == 0.0),
            "B_zero_advance_codepoints": dict(Counter(hex(c["cp"]) for c in ink if c["em_adv"] == 0.0).most_common(12)),
            "B_implausible_advance": sum(
                1 for c in ink if c["em_adv"] is not None and not (0.05 <= c["em_adv"] <= 3.0)
            ),
            "C_compared_against_empirical": len(agree),
            "C_within_0.06_em": close,
            "C_agreement_rate": round(close / len(agree), 4) if agree else None,
            "D_generate_space_port": _score_rule(pairs),
            # Negative control, same as FINDINGS.md §1 used: if D scores near zero because
            # the rule is somehow degenerate rather than because these advances are right,
            # corrupting them will not hurt it.
            "D_negative_control_x1.25": _score_rule(
                [
                    {
                        **p,
                        "a": {**p["a"], "em_adv": _scale(p["a"]["em_adv"], 1.25)},
                        "b": {**p["b"], "em_adv": _scale(p["b"]["em_adv"], 1.25)},
                    }
                    for p in pairs
                ]
            ),
            "D_negative_control_x0.75": _score_rule(
                [
                    {
                        **p,
                        "a": {**p["a"], "em_adv": _scale(p["a"]["em_adv"], 0.75)},
                        "b": {**p["b"], "em_adv": _scale(p["b"]["em_adv"], 0.75)},
                    }
                    for p in pairs
                ]
            ),
            "E_extract_ms_with_advances": round(t_ext * 1000),
            "E_extract_ms_baseline": round(t_base * 1000),
            "E_cost_multiplier": round(t_ext / t_base, 2) if t_base else None,
        }
        d = out["documents"][key]
        print(f"\n## {key} ({n} pages)")
        print(
            f"   A coverage: {d['A_with_advance']}/{d['A_ink_chars']} ink chars have an advance "
            f"({d['A_advance_coverage']})   text_object={d['A_with_text_object']} font={d['A_with_font']}"
        )
        if d["B_missing_by_codepoint"]:
            print(f"   B missing by codepoint: {d['B_missing_by_codepoint']}")
        print(
            f"   B zero-advance={d['B_zero_advance']} {d['B_zero_advance_codepoints']} "
            f"implausible={d['B_implausible_advance']}"
        )
        print(
            f"   C advance-shaped: {d['C_within_0.06_em']}/{d['C_compared_against_empirical']} "
            f"({d['C_agreement_rate']})"
        )
        r = d["D_generate_space_port"]
        print(
            f"   D port on PDFium's OWN advances: errors={r['errors']} rate={r['error_rate']} "
            f"missed={r['missed']} spurious={r['spurious']} "
            f"recall={r['boundary_recall']} generated_recall={r['generated_recall']} "
            f"(unavailable {r['pairs_unavailable']})"
        )
        for tag in ("D_negative_control_x1.25", "D_negative_control_x0.75"):
            nc = d[tag]
            print(f"   {tag}: errors={nc['errors']} rate={nc['error_rate']}")
        print(
            f"   E cost: {d['E_extract_ms_with_advances']} ms vs "
            f"{d['E_extract_ms_baseline']} ms baseline = {d['E_cost_multiplier']}x"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
