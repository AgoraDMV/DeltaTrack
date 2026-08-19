"""Per-line TRACKING: the raw inter-glyph geometry `pdf_text` discards.

`LineGeom` keeps only the left edge, the right edge and the first word's right edge, so
whether a line was set at normal, loose or CONDENSED tracking is unrecoverable
downstream. The #501 near-full container is the case where that matters: if GPO squeezed
a complete heading onto one line to make it fit, the fit was manufactured, and the
squeeze is observable even though the resulting fullness is not.

    tracking = mean over adjacent intra-word glyph pairs of (next.left - prev.right) / size

Negative means condensed. Emitted per (bill, version, page, line).

**Contract discipline.** The walk duplicates `pdf_text._page_glyph_sizes`; it re-emits
that function's `(size, LineGeom)` and is asserted equal to production for every line of
every page before any number is reported.

    uv run python docs/research/pdf-heading-identity/nearfull/tracking.py
"""
from __future__ import annotations
import ctypes, json, math, statistics, sys
from collections import Counter
from pathlib import Path
import pypdfium2 as pdfium, pypdfium2.raw as praw

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from deltatrack.parsers import pdf_text as PT  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = Path(__file__).resolve().parents[1] / "results" / "tracking.jsonl"
CORPUS = ROOT / "tests" / "corpus"
HOLDOUT = ROOT / "bills" / "_holdout524"


def page_tracking(tp, page_text):
    raw = tp.raw
    n = praw.FPDFText_CountChars(raw)
    if n <= 0:
        return {}
    bulk = len(page_text) == n
    fast = None
    chars = []
    for i in range(n):
        cp = ord(page_text[i]) if bulk else praw.FPDFText_GetUnicode(raw, i)
        if cp < 0x20:
            continue
        box = PT._char_box(raw, i)
        if box is None:
            continue
        mat = praw.FS_MATRIX()
        if not praw.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
            continue
        if fast is None:
            fast = abs(praw.FPDFText_GetFontSize(raw, i) - 1.0) <= PT._FONTSIZE_EPS
        sc = math.sqrt(mat.a * mat.a + mat.b * mat.b)
        if not fast:
            sc *= praw.FPDFText_GetFontSize(raw, i)
        if sc <= PT._SIZE_FLOOR:
            continue
        left, right, bottom, _t = box
        chars.append((bottom, left, right, cp, sc))
    if not chars:
        return {}
    out, ambiguous = {}, set()
    for cluster in PT._cluster_baselines(chars):
        med = statistics.median([c[4] for c in cluster])
        kept = [c for c in cluster if c[4] >= 0.6 * med]
        if not kept:
            continue
        text = PT._line_text(kept)
        m = PT._NUMBERED_LINE.match(text)
        if not m:
            continue
        ln = int(m.group(1))
        content = m.group(2)
        n_margin = len(m.group(1))
        cg = sorted(kept, key=lambda c: c[1])[n_margin:]
        sizes = [c[4] for c in cg]
        sizes = sizes[: len(content.replace(" ", ""))] or sizes
        if not sizes:
            continue
        printed = [c for c in cg if c[3] != 32]
        if not printed:
            continue
        geom = PT.LineGeom(printed[0][1], max(c[2] for c in printed), PT._first_word_right(cg))
        if ln in out or ln in ambiguous:
            ambiguous.add(ln)
            out.pop(ln, None)
            continue
        gaps, prev = [], None
        for c in cg:
            if c[3] == 32:
                prev = None
                continue
            if prev is not None:
                gaps.append((c[1] - prev[2]) / c[4])
            prev = c
        out[ln] = {
            "prod_size": round(statistics.median(sizes), 1),
            "prod_geom": geom,
            "tracking_mean": round(statistics.mean(gaps), 5) if gaps else None,
            "tracking_med": round(statistics.median(gaps), 5) if gaps else None,
            "n_gaps": len(gaps),
        }
    return out


def documents():
    pop = json.loads((HERE / "population.json").read_text())["rows"]
    want = sorted({(r["bill"], r["version"]) for r in pop})
    for bill, version in want:
        for base in (CORPUS / bill, HOLDOUT / bill):
            pdf = base / f"{version}.pdf"
            if pdf.exists():
                yield bill, version, pdf
                break


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows, checked, bad = [], 0, 0
    for bill, version, pdf in documents():
        doc = pdfium.PdfDocument(str(pdf))
        try:
            for pi in range(len(doc)):
                page = doc[pi]
                tp = page.get_textpage()
                try:
                    raw_text = tp.get_text_range()
                    mine = page_tracking(tp, raw_text)
                    prod = PT._page_glyph_sizes(tp, raw_text)
                finally:
                    tp.close()
                    page.close()
                checked += 1
                if set(mine) != set(prod):
                    bad += 1
                else:
                    for ln, v in mine.items():
                        ps, pg = prod[ln]
                        if v["prod_size"] != ps or v["prod_geom"] != pg:
                            bad += 1
                            break
                for ln, v in mine.items():
                    rows.append({"bill": bill, "version": version, "page": pi + 1, "line": ln,
                                 "tracking_mean": v["tracking_mean"], "tracking_med": v["tracking_med"],
                                 "n_gaps": v["n_gaps"]})
        finally:
            doc.close()
        print(f"  {bill}/{version}: rows={len(rows)}")
    print(f"\nCONTRACT CHECK: pages={checked} mismatched={bad}")
    if bad:
        raise SystemExit("tracking walk diverged from production; measurements void")
    OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"wrote {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main()
