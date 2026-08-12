"""V7 — is the selective abstraction boundary justified?

The hybrid design trusts the engine for character order, spaces and hyphen metadata, and
does NOT trust it for line breaks; lines are reconstructed geometrically. `RESULTS-HYBRID`
§7 treats that split as vindicated by one instance -- a WASM/native reading-order
disagreement on the committee report that "cannot reach the output because the hybrid
layer assigns lines by baseline and discards the engine's break characters outright".

One instance is not a justification for a boundary. This probe compares the two sources
against a third, per line class:

    A   ENGINE lines      -- split PDFium's char stream on its generated CR/LF
    B   GEOMETRIC lines   -- cluster on the text-matrix origin at _BASELINE_TOL, exactly
                             what reconstruct_hybrid.cluster_lines does
    C   PRINTED truth     -- the set of distinct ink baselines on the page, which is what
                             "a printed line" means on a page of set type

C is the referee and it is deliberately crude: it says how many printed lines there are,
not what is on them.

THE HALF OF THIS COMPARISON THAT IS CIRCULAR, said before the numbers rather than after.
B and C are nearly the same computation -- both cluster baselines at the same tolerance,
B over kept characters and C over ink. So B scoring 0 error against C is close to
definitional and is NOT evidence that geometric line assignment is right. It is reported
only to show the two agree.

The A-versus-C comparison is not circular, and it is the one that carries the finding:
the engine's break characters have no influence on where ink sits, so counting how far
its rows depart from the ink baselines is a real measurement. A result there is evidence
about the ENGINE, whichever way it falls.

Line classes are separated because the report's argument is class-dependent -- it claims
geometry wins on page chrome and reading order, and the engine wins on nothing above the
word. Measured per class:

    numbered_body   GPO's margin-numbered body lines
    display_caps    lines whose median size exceeds the body size (headings, cover type)
    chrome          lines matching reconstruct's own chrome patterns
    tabular         lines carrying a dot leader or 3+ runs of 2+ spaces
    rotated         lines with any non-upright glyph (the left-gutter watermark)
    other

Read-only. Writes JSON only under `validation/results/`.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]

BASELINE_TOL = 0.6
_CHROME = (
    re.compile(r"^\d{1,4}$"),
    re.compile(r"^•\s*(?:HR|S|H|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\b.*$"),
    re.compile(r"^(?:H|S|HR|HRES|SRES|HJRES|SJRES|HCONRES|SCONRES)\s+\d+\s+[A-Z]{2,4}$"),
    re.compile(r"^VerDate\b"),
    re.compile(r"\bon DSK\S*\s*(?:PROD|with)\b"),
    re.compile(r"^\S+ on DSK"),
)
_NUMBERED = re.compile(r"^\d{1,2} ")
_LEADER = re.compile(r"\.{4,}|․{4,}")


def _page_chars(textpage):
    raw = textpage.raw
    n = R.FPDFText_CountChars(raw)
    out = []
    for i in range(max(n, 0)):
        cp = R.FPDFText_GetUnicode(raw, i)
        ox, oy = ctypes.c_double(), ctypes.c_double()
        if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
            continue
        mat = R.FS_MATRIX()
        if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        scale = math.sqrt(mat.a * mat.a + mat.b * mat.b)
        out.append(
            {
                "cp": cp,
                "gen": R.FPDFText_IsGenerated(raw, i) == 1,
                "oy": oy.value,
                "ox": ox.value,
                "size": R.FPDFText_GetFontSize(raw, i) * scale,
                "upright": abs(mat.b) < 1e-6 and mat.a > 0,
            }
        )
    return out


def engine_lines(chars) -> list[list[dict]]:
    """A -- split on the engine's own break characters, exactly as a string pipeline would."""
    rows, cur = [], []
    for c in chars:
        if c["cp"] in (10, 13):
            if cur:
                rows.append(cur)
                cur = []
            continue
        cur.append(c)
    if cur:
        rows.append(cur)
    return rows


def geometric_lines(chars) -> list[list[dict]]:
    """B -- cluster on baseline, the same rule reconstruct_hybrid.cluster_lines applies."""
    kept = [c for c in chars if c["cp"] not in (10, 13) and (c["gen"] or (c["size"] > 1.0 and c["upright"]))]
    if not kept:
        return []
    rows, cur, anchor = [], [], None
    for c in sorted(kept, key=lambda c: -c["oy"]):
        if anchor is None or abs(c["oy"] - anchor) <= BASELINE_TOL:
            cur.append(c)
            if anchor is None:
                anchor = c["oy"]
        else:
            rows.append(cur)
            cur, anchor = [c], c["oy"]
    if cur:
        rows.append(cur)
    return rows


def printed_lines(chars) -> list[float]:
    """C -- the distinct ink baselines on the page, clustered at the same tolerance.

    Uses INK only: a generated character's baseline is copied from its neighbours, so
    including them could not add a printed line and could only mask a missing one.
    """
    ys = sorted((c["oy"] for c in chars if not c["gen"] and c["size"] > 1.0 and c["upright"]), reverse=True)
    out: list[float] = []
    for y in ys:
        if not out or abs(y - out[-1]) > BASELINE_TOL:
            out.append(y)
    return out


def classify(row: list[dict], body_size: float) -> str:
    text = "".join(chr(c["cp"]) for c in row if c["cp"] >= 32).strip()
    if any(not c["upright"] for c in row):
        return "rotated"
    if any(p.search(text) for p in _CHROME):
        return "chrome"
    if _LEADER.search(text) or len(re.findall(r"  +", text)) >= 3:
        return "tabular"
    if _NUMBERED.match(text):
        return "numbered_body"
    sizes = [c["size"] for c in row if c["size"] > 1.0]
    if sizes and body_size and statistics.median(sizes) > body_size * 1.15:
        return "display_caps"
    return "other"


def analyse(chars) -> dict:
    a_rows = engine_lines(chars)
    b_rows = geometric_lines(chars)
    c_lines = printed_lines(chars)
    sizes = [c["size"] for c in chars if c["size"] > 1.0]
    body = statistics.median(sizes) if sizes else 0.0

    # For each candidate, how many of its rows sit on more than one printed baseline?
    def straddles(rows):
        n = 0
        for row in rows:
            ys = sorted({round(c["oy"], 3) for c in row if not c["gen"]})
            if not ys:
                continue
            clusters = 1
            for p, q in zip(ys, ys[1:]):
                if abs(q - p) > BASELINE_TOL:
                    clusters += 1
            if clusters > 1:
                n += 1
        return n

    per_class_a: Counter = Counter()
    per_class_b: Counter = Counter()
    for row in a_rows:
        per_class_a[classify(row, body)] += 1
    for row in b_rows:
        per_class_b[classify(row, body)] += 1

    straddle_class_a: Counter = Counter()
    for row in a_rows:
        ys = sorted({round(c["oy"], 3) for c in row if not c["gen"]})
        if len(ys) > 1 and max(ys) - min(ys) > BASELINE_TOL:
            straddle_class_a[classify(row, body)] += 1

    return {
        "printed_lines": len(c_lines),
        "engine_lines": len(a_rows),
        "geometric_lines": len(b_rows),
        "engine_minus_printed": len(a_rows) - len(c_lines),
        "geometric_minus_printed": len(b_rows) - len(c_lines),
        "engine_rows_straddling_printed_lines": straddles(a_rows),
        "geometric_rows_straddling_printed_lines": straddles(b_rows),
        "engine_straddles_by_class": dict(straddle_class_a),
        "engine_rows_by_class": dict(per_class_a),
        "geometric_rows_by_class": dict(per_class_b),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--pages", type=int, default=30)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "v07_line_seam.json")
    args = ap.parse_args()

    out: dict = {
        "note": (
            "C counts distinct ink baselines. B (geometric) is nearly the same computation, "
            "so B's error against C is DEFINITIONAL and is not evidence. Only the A (engine) "
            "rows against C are an independent measurement. A candidate matching C exactly can "
            "still put the wrong characters on a line."
        ),
        "baseline_tol": BASELINE_TOL,
        "documents": {},
    }
    for spec in args.pdfs:
        path = Path(spec) if Path(spec).is_absolute() else REPO / spec
        doc = pdfium.PdfDocument(str(path))
        agg = Counter()
        by_class_straddle = Counter()
        eng_class = Counter()
        try:
            n = min(args.pages, len(doc))
            for p in range(n):
                pg = doc[p]
                tpg = pg.get_textpage()
                try:
                    r = analyse(_page_chars(tpg))
                finally:
                    tpg.close()
                    pg.close()
                for k in (
                    "printed_lines",
                    "engine_lines",
                    "geometric_lines",
                    "engine_rows_straddling_printed_lines",
                    "geometric_rows_straddling_printed_lines",
                ):
                    agg[k] += r[k]
                by_class_straddle.update(r["engine_straddles_by_class"])
                eng_class.update(r["engine_rows_by_class"])
        finally:
            doc.close()

        key = str(path.relative_to(REPO))
        out["documents"][key] = {
            "pages": n,
            **dict(agg),
            "engine_line_count_error": agg["engine_lines"] - agg["printed_lines"],
            "geometric_line_count_error": agg["geometric_lines"] - agg["printed_lines"],
            "engine_straddles_by_class": dict(by_class_straddle),
            "engine_rows_by_class": dict(eng_class),
            "engine_straddle_rate_by_class": {
                k: round(by_class_straddle.get(k, 0) / v, 4) for k, v in eng_class.items() if v
            },
        }
        d = out["documents"][key]
        print(f"\n## {key} ({n} pages)")
        print(
            f"   printed={d['printed_lines']}  engine={d['engine_lines']} "
            f"(err {d['engine_line_count_error']:+})  geometric={d['geometric_lines']} "
            f"(err {d['geometric_line_count_error']:+})"
        )
        print(
            f"   rows straddling >1 printed line:  engine={d['engine_rows_straddling_printed_lines']}  "
            f"geometric={d['geometric_rows_straddling_printed_lines']}"
        )
        print(f"   engine straddle rate by class: {d['engine_straddle_rate_by_class']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
