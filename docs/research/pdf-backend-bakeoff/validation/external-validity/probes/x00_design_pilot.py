"""x00 -- DESIGN MATERIAL. How far apart are the two seams, once both are fed by PDFium?

NOT CONFIRMATORY. This runs on the DEVELOPMENT documents phases 1-3 already used and
touches no holdout. It exists to set the sample-size and power argument in
PRE-REGISTRATION.md, which needs to know whether the comparison can fire at all before
committing an adjudication budget to it.

    hybrid (H)              engine characters + the engine's own word spaces
    corrected extended (X)  engine characters with EVERY U+0020 dropped, word spaces
                            re-decided above the seam from pen origins + advances

THREE THINGS THIS PROBE LEARNED THE HARD WAY, all of them now protocol clauses:

1. MODE PARITY. `reconstruct_hybrid._line_text` renders GPO's soft hyphen as ASCII "-"
   unconditionally; `reconstruct_extended` only does so under `repaired=True`. The first
   pass compared the default modes and read 98 differing lines of 424 on one document --
   every one of them a line truncated at a U+FFFD carrier. That is a measurement of the
   MODE, not of the seam. Both sides are now run repaired.

2. THE DENOMINATOR MUST NOT BE MARGIN-NUMBERED LINES. Keyed on (page, printed line
   number), the enrolled bill `116-hr-1865/6` contributes 7 comparable lines, because an
   enrolled bill has almost no margin numbers. Comparison is by page-and-ordinal over ALL
   reconstructed lines, which gives that document 1,180.

3. A COMPARATOR REPORTING ZERO IS INDISTINGUISHABLE FROM ONE THAT CANNOT SEE. S1 scales
   the extended advances by 1.25 and requires the difference count to rise. It is reported
   next to every primary count, and a primary count without it is not evidence.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]

sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))
sys.path.insert(0, str(BAKE / "validation" / "phase2"))

import pdfium_extended  # noqa: E402
import pdfium_hybrid  # noqa: E402
import reconstruct_extended  # noqa: E402
import reconstruct_hybrid  # noqa: E402
from contract_extended import ADVANCE, ExtPdfPage  # noqa: E402
from contract_extended import CP as ECP  # noqa: E402

from deltatrack.parsers.pdf_anchors import derive_size_bands, extract_anchors  # noqa: E402

OUT = EV / "results" / "x00_design_pilot.json"
SABOTAGE_SCALE = 1.25

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-hr-4366/5", REPO / "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf"),
    ("116-hr-1865/6", REPO / "tests/corpus/116-hr-1865/6_enrolled-bill.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
    ("CRPT-118srpt198", REPO / "tests/data/CRPT-118srpt198.pdf"),
]
HEADING_KINDS = ("account", "agency", "grouping")


def corrected(pages: list[ExtPdfPage], advance_scale: float = 1.0) -> list[ExtPdfPage]:
    """The CORRECTED extended contract: no U+0020 ever enters it.

    `advance_scale` is the S1 handle and is 1.0 for every scored run.
    """
    out = []
    for p in pages:
        glyphs = []
        for g in p.glyphs:
            if g[ECP] == 32:
                continue
            if advance_scale != 1.0 and g[ADVANCE] is not None:
                g = (*g[:ADVANCE], round(g[ADVANCE] * advance_scale, 4))
            glyphs.append(g)
        out.append(ExtPdfPage(p.page_number, p.width, p.height, glyphs))
    return out


def all_lines(pages) -> list[tuple[int, int, str]]:
    """Every reconstructed printed line, keyed by (page, ordinal), so an unnumbered
    enrolled layout is scored rather than skipped."""
    return [(p.page_number, i, ln.text) for p in pages for i, ln in enumerate(p.lines)]


def compare(hp, ep) -> dict:
    h, e = all_lines(hp), all_lines(ep)
    n = min(len(h), len(e))
    rows = [(h[i], e[i]) for i in range(n) if h[i][2] != e[i][2]]
    return {"h_lines": len(h), "e_lines": len(e), "aligned": n, "differ": len(rows), "rows": rows}


def headings(pages) -> set[str]:
    return {a.text for a in extract_anchors(pages) if a.kind in HEADING_KINDS}


def main(limit: int = 24) -> int:
    out = []
    for name, path in DOCS:
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            continue
        hpages, _ = pdfium_hybrid.extract(path, limit=limit)
        hp, _ = reconstruct_hybrid.reconstruct(hpages)

        epages, _ = pdfium_extended.extract(path, limit=limit)
        ep, _ = reconstruct_extended.reconstruct(corrected(epages), repaired=True)
        sp, _ = reconstruct_extended.reconstruct(corrected(epages, SABOTAGE_SCALE), repaired=True)

        primary, sab = compare(hp, ep), compare(hp, sp)
        hh, eh = headings(hp), headings(ep)
        bands = derive_size_bands(hp)

        rec = {
            "document": name,
            "pages_scored": limit,
            "aligned_printed_lines": primary["aligned"],
            "line_count_hybrid": primary["h_lines"],
            "line_count_extended": primary["e_lines"],
            "printed_lines_differing": primary["differ"],
            f"S1_advances_x{SABOTAGE_SCALE}_differing": sab["differ"],
            "S1_fires": sab["differ"] > primary["differ"],
            "headings_hybrid": len(hh),
            "headings_extended": len(eh),
            "heading_symmetric_difference": sorted(hh ^ eh),
            "size_bands": None if bands is None else [bands.body, bands.heading_lo, bands.heading_hi],
            "differing_lines": [
                {"page": a[0], "ordinal": a[1], "hybrid": a[2], "extended": b[2]} for a, b in primary["rows"]
            ],
        }
        out.append(rec)
        print(
            f"{name:18} aligned={primary['aligned']:6} differ={primary['differ']:3} "
            f"S1={sab['differ']:5} fires={rec['S1_fires']!s:5} "
            f"headings h={len(hh):3} x={len(eh):3} symdiff={len(hh ^ eh):2}",
            flush=True,
        )

    totals = {
        "documents": len(out),
        "aligned_printed_lines": sum(r["aligned_printed_lines"] for r in out),
        "printed_lines_differing": sum(r["printed_lines_differing"] for r in out),
        f"S1_advances_x{SABOTAGE_SCALE}_differing": sum(r[f"S1_advances_x{SABOTAGE_SCALE}_differing"] for r in out),
        "S1_fires_on_every_document": all(r["S1_fires"] for r in out),
        "heading_occurrences_hybrid": sum(r["headings_hybrid"] for r in out),
        "heading_occurrences_differing": sum(len(r["heading_symmetric_difference"]) for r in out),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"population": "DEVELOPMENT -- not a holdout", "totals": totals, "documents": out}, indent=1)
    )
    print(f"\n{json.dumps(totals, indent=1)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 24))
