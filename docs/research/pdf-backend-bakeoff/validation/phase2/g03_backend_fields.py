"""G3 — can the other backends supply pen origin X and advance width FROM THEIR OWN API?

The extended-glyph design is only worth considering if it keeps the bake-off's neutrality
property: every candidate backend must be able to emit the contract from its own facts. If
only PDFium can, the design has the same backend-narrowing cost as the hybrid and loses its
main advantage over it.

The review's instruction is the operative one here: **do not claim neutrality from field
names**. `adv`, `origin` and `width` appear in three of these libraries and mean different
things. So each is checked by VALUE against a property only a real advance has:

    for two characters set tight on one baseline, origin_x(next) - origin_x(prev) is the
    previous character's advance.

That identity is what PDFium's own spacing rule relies on, and a field that does not
satisfy it cannot substitute, whatever it is called. Reported as the fraction of
consecutive same-line pairs where the claimed advance predicts the observed origin delta
to within 0.5 pt.

WHAT COUNTS AS A FAILURE. A backend that exposes neither field fails outright. A backend
that exposes them only at coarser granularity than one character (PDF.js, whose text items
average ~13 characters) fails for this contract even though its text is fine, and that is
the same limitation ADR 0003 already recorded against it.

Read-only. Writes JSON only under `validation/phase2/results/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]

TOL_PT = 0.5
BASELINE_TOL = 0.6


def _consistency(records: list[dict]) -> dict:
    """Does advance predict the next character's pen origin on the same line?"""
    ok = bad = 0
    samples = []
    for a, b in zip(records, records[1:]):
        if a["origin_x"] is None or b["origin_x"] is None or a["adv"] is None:
            continue
        if abs(a["origin_y"] - b["origin_y"]) > BASELINE_TOL:
            continue
        delta = b["origin_x"] - a["origin_x"]
        if delta <= 0:
            continue
        # Only tight settings test the identity: a word gap legitimately makes the delta
        # larger than the advance, so those are not evidence either way.
        if delta > a["adv"] + 1.5:
            continue
        if abs(delta - a["adv"]) <= TOL_PT:
            ok += 1
        else:
            bad += 1
            if len(samples) < 6:
                samples.append({"ch": a["ch"], "adv": round(a["adv"], 3), "observed_delta": round(delta, 3)})
    n = ok + bad
    return {
        "tight_pairs_tested": n,
        "advance_predicts_origin_delta": ok,
        "rate": round(ok / n, 4) if n else None,
        "mismatch_samples": samples,
    }


def probe_pdfium(path: Path, page: int) -> dict:
    """FPDFText_GetCharOrigin + the FPDFText_GetTextObject/GetFont/GetGlyphWidth chain."""
    import ctypes
    import math

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
                        cache[ck] = (w.value / 1000.0) if okc else None
                    adv = None if cache[ck] is None else cache[ck] * size
            recs.append({"ch": chr(cp), "origin_x": ox.value, "origin_y": oy.value, "adv": adv})
        tp.close()
        pg.close()
    finally:
        doc.close()
    return {
        "origin_api": "FPDFText_GetCharOrigin",
        "advance_api": "FPDFText_GetTextObject -> FPDFTextObj_GetFont -> FPDFFont_GetGlyphWidth",
        "per_character": True,
        "chars": len(recs),
        "with_advance": sum(1 for r in recs if r["adv"] is not None),
        **_consistency(recs),
    }


def probe_pdfminer(path: Path, page: int) -> dict:
    """LTChar carries both natively: its bbox is built at the pen with width = adv."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    pg = next(iter(extract_pages(str(path), page_numbers=[page - 1], laparams=LAParams())))
    recs = []
    for o in walk(pg):
        if not isinstance(o, LTChar):
            continue
        t = o.get_text()
        if not t.strip():
            continue
        # CORRECTION, found by measuring rather than reading the attribute name:
        # LTChar.adv is in EM units (0.519 for '9' at 14 pt), not points. pdfminer builds
        # the bbox as (0, descent+rise, adv, ...) and then transforms it, so after
        # transform x0 IS the pen origin and the bbox WIDTH is the advance in points.
        # Using .adv directly made every pair fail the tight-pair filter by a factor of
        # ~14 and reported 0 testable pairs, which is what a units error looks like.
        recs.append({"ch": t, "origin_x": o.x0, "origin_y": o.y0, "adv": abs(o.width)})
    return {
        "origin_api": "LTChar.x0 (bbox built at the pen position)",
        "advance_api": "LTChar.width (= LTChar.adv x size; .adv alone is in em units)",
        "per_character": True,
        "chars": len(recs),
        "with_advance": sum(1 for r in recs if r["adv"] is not None),
        **_consistency(recs),
    }


def probe_pymupdf(path: Path, page: int) -> dict:
    """`get_texttrace()` gives per-character origin and advance box, with no Font lookup.

    CORRECTION, recorded because the first version of this probe failed for the wrong
    reason: going via `pymupdf.Font(fontname=span["font"])` cannot instantiate GPO's
    embedded faces (DeVinne, NewCenturySchlbk-Bold) and covered only 36 of 987 characters.
    That would have been reported as PyMuPDF lacking the field. It does not lack it --
    `get_texttrace()` emits (unicode, glyph_id, origin, bbox) per character, where the
    bbox is the ADVANCE box, so bbox[2] - origin[0] is the advance in points.
    """
    import pymupdf

    d = pymupdf.open(str(path))
    recs = []
    try:
        for span in d[page - 1].get_texttrace():
            for ch in span.get("chars", []):
                ucs, _glyph, origin, bbox = ch[0], ch[1], ch[2], ch[3]
                if not chr(ucs).strip():
                    continue
                recs.append(
                    {
                        "ch": chr(ucs),
                        "origin_x": origin[0],
                        "origin_y": origin[1],
                        "adv": bbox[2] - origin[0],
                    }
                )
    finally:
        d.close()
    return {
        "origin_api": "get_texttrace() char origin",
        "advance_api": "get_texttrace() char advance box: bbox[2] - origin[0]",
        "per_character": True,
        "chars": len(recs),
        "with_advance": sum(1 for r in recs if r["adv"] is not None),
        **_consistency(recs),
    }


_PDFJS = """
import { readFileSync } from "node:fs";
const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(process.argv[2])) }).promise;
const tc = await (await doc.getPage(parseInt(process.argv[3], 10))).getTextContent();
let chars = 0;
for (const it of tc.items) chars += (it.str || "").length;
// PDF.js exposes transform[4] (an item origin) and width (of the WHOLE item). There is no
// per-character origin or advance at this granularity, which is the point being tested.
console.log(JSON.stringify({
  items: tc.items.length,
  chars,
  chars_per_item: +(chars / Math.max(tc.items.length, 1)).toFixed(1),
  has_per_item_origin: tc.items.every(i => Array.isArray(i.transform)),
  has_per_item_width: tc.items.every(i => typeof i.width === "number"),
  has_per_character_anything: false,
}));
"""


def probe_pdfjs(path: Path, page: int) -> dict:
    import subprocess

    script = REPO / "docs/research/pdf-backend-bakeoff/probes/js" / "_g03.mjs"
    script.write_text(_PDFJS)
    try:
        r = subprocess.run(
            ["node", str(script), str(path.resolve()), str(page)],
            capture_output=True,
            text=True,
            cwd=str(script.parent),
        )
        if r.returncode != 0:
            return {"error": r.stderr[-300:]}
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        script.unlink(missing_ok=True)
    return {
        "origin_api": "textItem.transform[4] — per ITEM, not per character",
        "advance_api": "none — textItem.width is the whole item's width",
        "per_character": False,
        "chars": d["chars"],
        "with_advance": 0,
        "detail": d,
        "tight_pairs_tested": 0,
        "advance_predicts_origin_delta": 0,
        "rate": None,
        "mismatch_samples": [],
    }


BACKENDS = {"pdfium": probe_pdfium, "pdfminer.six": probe_pdfminer, "pymupdf": probe_pymupdf, "pdf.js": probe_pdfjs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf")
    ap.add_argument("--page", type=int, default=99)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "g03_backend_fields.json")
    args = ap.parse_args()

    out: dict = {
        "pdf": str(args.pdf.relative_to(REPO)),
        "page": args.page,
        "test": (
            "advance must predict the next character's pen-origin delta on the same "
            "baseline to within 0.5 pt, on tight settings only"
        ),
        "backends": {},
    }
    for name, fn in BACKENDS.items():
        try:
            out["backends"][name] = fn(args.pdf, args.page)
        except Exception as exc:  # noqa: BLE001
            out["backends"][name] = {"error": f"{type(exc).__name__}: {exc}"}
        r = out["backends"][name]
        print(f"\n## {name}")
        if "error" in r:
            print(f"   ERROR {r['error']}")
            continue
        print(f"   origin:  {r['origin_api']}")
        print(f"   advance: {r['advance_api']}")
        print(f"   per-character: {r['per_character']}   chars={r['chars']} with_advance={r['with_advance']}")
        print(
            f"   advance predicts origin delta: {r['advance_predicts_origin_delta']}"
            f"/{r['tight_pairs_tested']} ({r['rate']})"
        )
        if r.get("fonts_not_instantiable"):
            print(f"   fonts not instantiable: {r['fonts_not_instantiable']}")
        if r.get("mismatch_samples"):
            print(f"   mismatches: {r['mismatch_samples']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
