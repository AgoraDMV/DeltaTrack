"""x06 -- DESIGN MATERIAL. Can M6 be adjudicated inside a 6-10 line region?

NOT CONFIRMATORY. DEVELOPMENT documents only. No holdout document is opened.

PRE-REGISTRATION.md section 6 defines M6 as:

    "for each dollar amount in a C-region, emitted nearest heading-ish ancestor vs
     adjudicated"

and section 5.3 fixes the adjudicated unit as a region "spanning 6-10 printed lines", with
the adjudicator seeing ONLY that region's rendered image.

Those two clauses are in tension, and the tension is measurable rather than arguable: an
appropriations account heading governs a long run of prose, so most amounts sit many lines
below the heading that owns them. If the governing heading is outside the rendered region,
the adjudicator cannot state the amount's account from the evidence it is shown, and M6 has
no oracle for that amount.

WHAT THIS MEASURES, AND WHAT IT DOES NOT. The reference here is the nearest preceding
account/agency anchor that PRODUCTION's `extract_anchors` emits from the HYBRID
reconstruction. That is an architecture-derived reference, NOT independent truth. So this
probe measures:

    the distance from each amount to the nearest preceding HYBRID-PRODUCED anchor

and NOT:

    the distance from each amount to its TRUE governing account heading.

The distinction matters: if hybrid misses a heading, the measured distance to the next one
back is too large; if hybrid invents one, too small. The measurement is still decisive for
the design question -- a 6-10 line viewport is far too small for a claim about long-range
attribution -- but it does not establish the true distance distribution, and A17 must not
be worded as though it does.

Uses the hybrid path only: the question is about the PROTOCOL's geometry, not about a
difference between architectures, and both arms see the same headings here.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
BAKE = EV.parents[1]
REPO = BAKE.parents[2]

sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(BAKE / "probes"))
sys.path.insert(0, str(BAKE / "probes" / "backends"))

import pdfium_hybrid  # noqa: E402
import reconstruct_hybrid  # noqa: E402

from deltatrack.parsers.pdf_anchors import extract_anchors  # noqa: E402

OUT = EV / "results" / "x06_m6_feasibility.json"
AMOUNT_RE = re.compile(r"\$[\d,]+(?:\.\d+)?")
HEADING_KINDS = ("account", "agency")
REGION_SIZES = (6, 8, 10, 15, 25, 50)

DOCS = [
    ("114-hr-2029/4", REPO / "tests/corpus/114-hr-2029/4_reported-in-senate.pdf"),
    ("118-hr-4366/5", REPO / "tests/corpus/118-hr-4366/5_engrossed-amendment-house.pdf"),
    ("118-s-4795/1", REPO / "tests/corpus/118-s-4795/1_reported-in-senate.pdf"),
]


def main(limit: int = 30) -> int:
    per_doc = []
    all_distances: list[int] = []

    for name, path in DOCS:
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            continue
        pages, _ = pdfium_hybrid.extract(path, limit=limit)
        recon, _ = reconstruct_hybrid.reconstruct(pages)
        anchors = extract_anchors(recon)

        # Flatten to a document-order line stream, and mark which lines are headings.
        flat: list[tuple[int, int | None, str]] = []
        for p in recon:
            for ln in p.lines:
                flat.append((p.page_number, ln.line_number, ln.text))
        heading_at = {(a.page_number, a.line_number) for a in anchors if a.kind in HEADING_KINDS}

        distances: list[int] = []
        unattributable = 0
        for idx, (page, lineno, text) in enumerate(flat):
            if not AMOUNT_RE.search(text):
                continue
            for amount in AMOUNT_RE.findall(text):
                del amount
                # Walk back to the nearest preceding account/agency heading.
                d = None
                for back in range(idx, -1, -1):
                    if (flat[back][0], flat[back][1]) in heading_at:
                        d = idx - back
                        break
                if d is None:
                    unattributable += 1
                else:
                    distances.append(d)
        all_distances.extend(distances)

        share = {
            str(n): round(sum(1 for d in distances if d < n) / len(distances), 4) if distances else None
            for n in REGION_SIZES
        }
        per_doc.append(
            {
                "document": name,
                "pages_scored": limit,
                "amounts_found": len(distances) + unattributable,
                "amounts_with_a_preceding_heading": len(distances),
                "amounts_with_NO_preceding_heading_in_document": unattributable,
                "median_lines_to_governing_heading": sorted(distances)[len(distances) // 2] if distances else None,
                "max_lines_to_governing_heading": max(distances) if distances else None,
                "share_answerable_within_region_of_N_lines": share,
            }
        )
        print(
            f"{name:16} amounts={len(distances) + unattributable:5} "
            f"median_dist={sorted(distances)[len(distances) // 2] if distances else '-':>4} "
            f"max={max(distances) if distances else '-':>4} "
            f"answerable@10={share.get('10')}",
            flush=True,
        )

    pooled = {
        str(n): round(sum(1 for d in all_distances if d < n) / len(all_distances), 4) if all_distances else None
        for n in REGION_SIZES
    }
    # DESCRIPTIVE, not a pass/fail. A first version of this probe applied a >50 % threshold
    # and printed "may be implementable as frozen" at 57 %, which is far too lenient: it
    # would license a metric whose oracle is silently absent for two amounts in five. The
    # judgement belongs in the amendment, next to the number, not in a canned string here.
    verdict = (
        f"On three development documents, the nearest preceding HYBRID-PRODUCED "
        f"account/agency anchor lies within 6 reconstructed lines for {pooled.get('6')} of "
        f"observed amounts and within 10 for {pooled.get('10')}; a 50-line span reaches "
        f"{pooled.get('50')}. The reference is architecture-derived, so this is NOT the "
        f"share of amounts whose TRUE governing heading is in range. It does show that a "
        f"6-10 line viewport cannot support a long-range attribution claim. "
        f"See PRE-EXECUTION-AMENDMENTS.md A17."
    )
    doc = {
        "population": "DEVELOPMENT -- not a holdout",
        "question": "can M6's amount->account attribution be adjudicated inside a 6-10 printed-line region?",
        "reference_is_architecture_derived": (
            "distances are to the nearest preceding anchor emitted by production "
            "extract_anchors over the HYBRID reconstruction, not to independent truth"
        ),
        "protocol_region_size": "6-10 printed lines (PRE-REGISTRATION.md 5.3)",
        "pooled_share_answerable_within_region_of_N_lines": pooled,
        "amounts_total": len(all_distances),
        "verdict": verdict,
        "documents": per_doc,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"\npooled share answerable by region size: {json.dumps(pooled)}")
    print(f"\n{verdict}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
