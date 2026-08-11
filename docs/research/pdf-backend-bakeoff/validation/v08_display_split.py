"""V8 - does PDFium's generated-space decision split DISPLAY type at corpus scale?

The blinded sample found PDFium extracting the letter-spaced word REPORT as
'R E P O R T' on the committee-report cover, an error the glyph rule does not make.
Headings are the financial data contract (ADR 0012/0014), and display type is where
GPO sets headings, so the question is whether this signature reaches heading-sized
lines across the corpus rather than one cover page.

Detected on the ENGINE'S OWN TEXT, so no reconstruction layer can mask or manufacture
it: a run of 3+ single-character tokens on one line. Reported with the line's median
glyph size against the document's body size, because a split on a body line is a typo
and a split on a heading line is a corrupted account name.
"""

import ctypes
import json
import math
import re
import statistics
import sys
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as R

REPO = Path("/Users/williamhea/Documents/Code/civictech/appropriations_bills/.claude/worktrees/pdf-bakeoff")
SPLIT = re.compile(r"(?:(?<=^)|(?<= ))(?:[A-Z] ){3,}[A-Z](?=$| )")


def scan(path, pages):
    doc = pdfium.PdfDocument(str(path))
    hits, body_sizes, lines_seen = [], [], 0
    try:
        n = min(pages, len(doc))
        for p in range(n):
            pg = doc[p]
            tp = pg.get_textpage()
            try:
                raw = tp.raw
                cnt = R.FPDFText_CountChars(raw)
                rows = {}
                for i in range(max(cnt, 0)):
                    cp = R.FPDFText_GetUnicode(raw, i)
                    if cp in (10, 13):
                        continue
                    oy = ctypes.c_double()
                    ox = ctypes.c_double()
                    if not R.FPDFText_GetCharOrigin(raw, i, ctypes.byref(ox), ctypes.byref(oy)):
                        continue
                    mat = R.FS_MATRIX()
                    if not R.FPDFText_GetMatrix(raw, i, ctypes.byref(mat)):
                        continue
                    sc = math.sqrt(mat.a * mat.a + mat.b * mat.b)
                    size = R.FPDFText_GetFontSize(raw, i) * sc
                    if size > 1.0:
                        body_sizes.append(size)
                    rows.setdefault(round(oy.value, 1), []).append((ox.value, cp, size))
                for y, cs in rows.items():
                    cs.sort()
                    text = "".join(chr(c) for _x, c, _s in cs)
                    lines_seen += 1
                    m = SPLIT.search(text)
                    if m:
                        sz = [s for _x, _c, s in cs if s > 1.0]
                        hits.append(
                            {
                                "page": p + 1,
                                "text": text.strip()[:70],
                                "match": m.group(0),
                                "line_size": round(statistics.median(sz), 1) if sz else None,
                            }
                        )
            finally:
                tp.close()
                pg.close()
    finally:
        doc.close()
    body = round(statistics.median(body_sizes), 1) if body_sizes else 0.0
    for h in hits:
        h["is_display"] = bool(h["line_size"] and body and h["line_size"] > body * 1.15)
    return {
        "pages": n,
        "lines": lines_seen,
        "body_size": body,
        "hits": len(hits),
        "display_hits": sum(1 for h in hits if h["is_display"]),
        "samples": hits[:8],
    }


out = {}
docs = sys.argv[1:]
for rel in docs:
    p = REPO / rel
    if not p.exists():
        continue
    out[rel] = scan(p, 40)
    d = out[rel]
    print(
        f"{rel:<58} lines={d['lines']:<6} body={d['body_size']:<5} hits={d['hits']:<4} display_hits={d['display_hits']}"
    )
    for s in d["samples"][:3]:
        print(f"    p{s['page']} size={s['line_size']} display={s['is_display']}  {s['text']!r}")
json.dump(
    out, open(REPO / "docs/research/pdf-backend-bakeoff/validation/results/v08_display_split.json", "w"), indent=1
)
