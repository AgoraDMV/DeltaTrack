"""x02 -- DESIGN MATERIAL. Is the XML reference actually disqualified as a heading oracle?

NOT CONFIRMATORY. Runs on the DEVELOPMENT corpus only.

Phases 1-3 all list "a valid heading-level oracle" as blocking, and all three give the
same reason: the XML reference comes from a parser known to drop `<quoted-block>`
(DeltaTrack#11), so a heading GPO printed can be absent from the reference and a PDF path
that finds it is scored wrong for being right.

That reason is inherited rather than measured, and a pre-registration may not build on an
inherited reason. Two things are checked here:

  1. DeltaTrack#11's state. It is CLOSED (2026-06-26, COMPLETED): a section's
     quoted-block TEXT now reaches the section body.
  2. What the structure tree still drops, and whether it is the class that matters.
     `bill_tree._node_subsections` keeps quoted-block subsections OUT of the tree by
     design -- "amendment payload ... not this bill's structure". So the question is not
     whether quoted-block content is dropped (some is, deliberately) but whether any
     APPROPRIATIONS heading is among it.

The distinction is the whole point. If appropriations headings live inside quoted blocks,
the XML cannot referee the metric the study cares about. If they never do, the XML is
disqualified for OTHER reasons -- which the pre-registration must then state honestly
instead of citing this one.
"""

from __future__ import annotations

import collections
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve()
EV = HERE.parents[1]
REPO = EV.parents[4]
CORPUS = REPO / "tests" / "corpus"
OUT = EV / "results" / "x02_oracle_reference_defects.json"

# The tags that carry appropriations heading structure -- the level the financial data
# contract is built on, and the only level whose absence would disqualify the reference.
APPROPS_TAGS = {
    "appropriations-major",
    "appropriations-intermediate",
    "appropriations-small",
    "appropriations",
}


def inside(el, parent: dict, tag: str) -> bool:
    cur = parent.get(el)
    while cur is not None:
        if cur.tag == tag:
            return True
        cur = parent.get(cur)
    return False


def main() -> int:
    rows = []
    totals: collections.Counter = collections.Counter()
    for xml in sorted(CORPUS.glob("*/*.xml")):
        try:
            root = ET.parse(xml).getroot()
        except ET.ParseError:
            continue
        parent = {c: p for p in root.iter() for c in p}

        n_qb = sum(1 for _ in root.iter("quoted-block"))
        approps_total = approps_in_qb = headers_in_qb = 0
        for el in root.iter():
            if el.tag in APPROPS_TAGS:
                approps_total += 1
                approps_in_qb += inside(el, parent, "quoted-block")
            elif el.tag == "header":
                headers_in_qb += inside(el, parent, "quoted-block")

        totals["documents"] += 1
        totals["documents_with_a_quoted_block"] += 1 if n_qb else 0
        totals["documents_with_approps_inside_a_quoted_block"] += 1 if approps_in_qb else 0
        totals["quoted_blocks"] += n_qb
        totals["appropriations_elements"] += approps_total
        totals["appropriations_elements_inside_a_quoted_block"] += approps_in_qb
        totals["headers_inside_a_quoted_block"] += headers_in_qb
        if n_qb or approps_in_qb:
            rows.append(
                {
                    "document": str(xml.relative_to(CORPUS)),
                    "quoted_blocks": n_qb,
                    "appropriations_elements": approps_total,
                    "appropriations_inside_quoted_block": approps_in_qb,
                    "headers_inside_quoted_block": headers_in_qb,
                }
            )

    # COMPLETENESS FLOOR. The verdict below is an assertion of ABSENCE, and an absence is
    # satisfied vacuously by a scan that read nothing. The first version of this probe
    # pointed REPO one directory too high, globbed an empty tree, and printed the "no
    # instances" verdict over totals of {} -- certifying a corpus it never opened. The
    # floor is deliberately a hard failure, not a warning.
    if totals["documents"] < 40 or totals["appropriations_elements"] < 10_000:
        print(
            f"FATAL: scan is too thin to support an absence claim -- "
            f"{totals['documents']} documents, {totals['appropriations_elements']} appropriations elements. "
            f"Expected the full development corpus at {CORPUS}.",
            file=sys.stderr,
        )
        return 2

    verdict = (
        "The mechanism has NO instances on this corpus: no appropriations heading element "
        "sits inside a <quoted-block>. The reference is therefore NOT disqualified as a "
        "heading oracle by DeltaTrack#11, and any protocol citing that reason is citing an "
        "inherited claim. Non-appropriations <header> elements ARE dropped in quantity, so "
        "the mechanism is real for general legislation and irrelevant for appropriations."
        if totals["appropriations_elements_inside_a_quoted_block"] == 0
        else "The mechanism HAS instances: appropriations headings sit inside quoted blocks."
    )

    doc = {
        "population": "DEVELOPMENT corpus (tests/corpus) -- not a holdout",
        "deltatrack_11": "CLOSED 2026-06-26 (COMPLETED); quoted-block TEXT now reaches the section body",
        "what_the_tree_still_drops_by_design": (
            "bill_tree._node_subsections: quoted-block subsections are amendment payload, not this bill's structure"
        ),
        "totals": dict(totals),
        "verdict": verdict,
        "documents": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))

    for k, v in sorted(totals.items()):
        print(f"{k:52} {v}")
    print(f"\n{verdict}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
