"""Which candidate backends can satisfy the hybrid contract, and how do they mark a
synthesised space?

This exists because the first draft of the portability assessment asserted, from the
shape of each library's API, that the hybrid contract would narrow the candidate set. The
assertion was wrong on the first backend checked, so the question is measured instead.

Two things are asked of each backend, on a boundary the glyph seam is known to lose
(`NATIONAL CEMETERY ADMINISTRATION`, where the gap is 2.40 pt against a 3.50 pt threshold):

  1. Does the backend's OWN text output carry the word space? This is the half of the
     hybrid contract that fixes the defect.
  2. What form does the synthesised character take, and is it distinguishable from a
     space read out of the content stream? This is what decides whether an adapter can
     avoid consuming placeholder geometry.

Reported per backend rather than pooled: the answers differ in kind, not in degree, and a
single "supported / unsupported" column would hide that.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/probe_backend_spacing.py
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

PROBE_TEXT = "CEMETERY ADMINISTRATION"
PROBE_JOINED = PROBE_TEXT.replace(" ", "")


def probe_pdfium(pdf: Path, page: int) -> dict:
    import pypdfium2 as pdfium
    import pypdfium2.raw as R

    doc = pdfium.PdfDocument(str(pdf))
    try:
        pg = doc[page - 1]
        tp = pg.get_textpage()
        raw = tp.raw
        n = R.FPDFText_CountChars(raw)
        seq = "".join(chr(R.FPDFText_GetUnicode(raw, i)) for i in range(n))
        k = seq.find(PROBE_TEXT)
        marker = None
        if k >= 0:
            i = k + PROBE_TEXT.index(" ")
            left, right, bottom, top = (ctypes.c_double() for _ in range(4))
            R.FPDFText_GetCharBox(raw, i, *(ctypes.byref(v) for v in (left, right, bottom, top)))
            marker = {
                "generated_flag": R.FPDFText_IsGenerated(raw, i) == 1,
                "box_area": round((right.value - left.value) * (top.value - bottom.value), 6),
            }
        tp.close()
        pg.close()
    finally:
        doc.close()
    return {
        "recovers_space": k >= 0,
        "produces_joined_form": PROBE_JOINED in seq,
        "generated_marker": "FPDFText_IsGenerated flag; zero-area box, origin only",
        "detail": marker,
    }


def probe_pdfminer(pdf: Path, page: int) -> dict:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTAnno, LTChar

    def walk(o):
        for c in getattr(o, "_objs", []):
            yield c
            yield from walk(c)

    pg = next(iter(extract_pages(str(pdf), page_numbers=[page - 1], laparams=LAParams())))
    seq_objs = [o for o in walk(pg) if isinstance(o, (LTChar, LTAnno))]
    seq = "".join(o.get_text() for o in seq_objs)
    k = seq.find(PROBE_TEXT)
    marker = None
    if k >= 0:
        o = seq_objs[k + PROBE_TEXT.index(" ")]
        marker = {"class": type(o).__name__, "has_bbox": hasattr(o, "bbox")}
    return {
        "recovers_space": k >= 0,
        "produces_joined_form": PROBE_JOINED in seq,
        "generated_marker": "LTAnno object (distinct class, carries no bbox at all)",
        "detail": marker,
    }


def probe_pymupdf(pdf: Path, page: int) -> dict:
    import pymupdf

    d = pymupdf.open(str(pdf))
    try:
        raw = d[page - 1].get_text("rawdict")
        chars = [c for b in raw["blocks"] for ln in b.get("lines", []) for s in ln.get("spans", []) for c in s["chars"]]
        seq = "".join(c["c"] for c in chars)
        k = seq.find(PROBE_TEXT)
        marker = None
        if k >= 0:
            c = chars[k + PROBE_TEXT.index(" ")]
            x0, y0, x1, y1 = c["bbox"]
            marker = {"box_area": round((x1 - x0) * (y1 - y0), 4)}
    finally:
        d.close()
    return {
        "recovers_space": k >= 0,
        "produces_joined_form": PROBE_JOINED in seq,
        "generated_marker": "NONE - synthesised spaces get a real box and are indistinguishable",
        "detail": marker,
    }


_PDFJS = """
import { readFileSync } from "node:fs";
const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(process.argv[2])) }).promise;
const tc = await (await doc.getPage(parseInt(process.argv[3], 10))).getTextContent();
const joined = tc.items.map(i => i.str).join("");
let opp = 0, lost = 0;
for (let i = 1; i < tc.items.length; i++) {
  const a = tc.items[i-1], b = tc.items[i];
  if (!a.str || !b.str || a.hasEOL || a.fontName === b.fontName) continue;
  if (Math.abs(a.transform[5] - b.transform[5]) > 0.6) continue;
  opp++;
  if (!a.str.endsWith(" ") && !b.str.startsWith(" ") && b.transform[4] - (a.transform[4] + a.width) > 1.0) lost++;
}
console.log(JSON.stringify({ items: tc.items.length, chars_per_item: +(joined.length/tc.items.length).toFixed(1),
  recovers_space: joined.includes(process.argv[4]), produces_joined_form: joined.includes(process.argv[5]),
  font_boundary_adjacencies: opp, font_boundary_spaces_lost: lost }));
"""


def probe_pdfjs(pdf: Path, page: int) -> dict:
    script = PROBES / "js" / "_probe_backend_spacing.mjs"
    script.write_text(_PDFJS)
    try:
        r = subprocess.run(
            ["node", str(script), str(pdf.resolve()), str(page), PROBE_TEXT, PROBE_JOINED],
            capture_output=True,
            text=True,
            cwd=str(script.parent),
        )
        if r.returncode != 0:
            return {"error": r.stderr[-400:]}
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        script.unlink(missing_ok=True)
    return {
        "recovers_space": d["recovers_space"],
        "produces_joined_form": d["produces_joined_form"],
        "generated_marker": "NONE - text-item granularity, no per-character box at all",
        "detail": d,
    }


BACKENDS = {
    "pdfium": probe_pdfium,
    "pdfminer.six": probe_pdfminer,
    "pymupdf": probe_pymupdf,
    "pdf.js": probe_pdfjs,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf")
    ap.add_argument("--page", type=int, default=99)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = {"pdf": str(args.pdf.relative_to(REPO)), "page": args.page, "probe_text": PROBE_TEXT, "backends": {}}
    print(f"# {PROBE_TEXT!r} on {args.pdf.name} page {args.page}")
    print(f"  (the neutral glyph layer produces {PROBE_JOINED!r} here from PDFium's geometry)\n")
    for name, fn in BACKENDS.items():
        try:
            out["backends"][name] = fn(args.pdf, args.page)
        except Exception as exc:  # noqa: BLE001
            out["backends"][name] = {"error": f"{type(exc).__name__}: {exc}"}
        r = out["backends"][name]
        print(
            f"  {name:<14} own text keeps the space: {str(r.get('recovers_space')):<5}  "
            f"joined form present: {str(r.get('produces_joined_form')):<5}"
        )
        print(f"                 synthesised-char marker: {r.get('generated_marker', r.get('error'))}")
        if r.get("detail"):
            print(f"                 {r['detail']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=1))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
