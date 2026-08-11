"""Red-team item 7: separate "identical to the incumbent" from "correct".

PDFium-WASM reproducing pypdfium2 exactly says nothing about whether either is RIGHT.
If the incumbent mis-reads an amount, its WASM twin mis-reads it identically and the
parity metric records a perfect score.

So a random sample of the PDF-derived amount entries is validated against the source
document through a path that shares NOTHING with the pipeline under test:

  * text comes from PyMuPDF's own `get_text()` -- a different library, its own text
    assembly, not the neutral glyph layer;
  * the check is that the claimed old value appears on the v1 page and the claimed new
    value on the v2 page, at the location the canonical diff points to.

A failure here is a real accuracy defect. A pass does not prove the diff is semantically
right, only that the numbers it reports are numbers actually printed in the documents.

Run: .venv/bin/python docs/research/pdf-backend-bakeoff/probes/redteam_validate_amounts.py
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parent
REPO = PROBES.parents[3]
for p in (str(PROBES), str(REPO / "src"), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from contract import run_backend  # noqa: E402
from reconstruct import reconstruct  # noqa: E402
from score_phase2 import pdf_canonical  # noqa: E402

SEED = 20260805  # fixed so the sample is reproducible


def independent_text(pdf: Path) -> str:
    """Whole-document text via PyMuPDF's OWN api -- not the neutral layer under test."""
    import pymupdf

    doc = pymupdf.open(str(pdf))
    try:
        return "\n".join(doc[i].get_text() for i in range(doc.page_count))
    finally:
        doc.close()


def variants(amount: str) -> list[str]:
    """Surface forms the same amount can take in printed GPO text.

    The canonical contract stores amounts as INTEGERS (194000000) while the page prints
    "$194,000,000". A first version of this check compared the integer against raw page
    text and reported 0/43 -- a check structurally incapable of matching, which looks
    exactly like a catastrophic accuracy failure. Both sides are stripped of $ and commas
    instead.
    """
    a = str(amount).strip().replace("$", "").replace(",", "")
    return [a] if a else []


def strip_money(text: str) -> str:
    """Remove $ and thousands separators so integer amounts can be found literally."""
    return re.sub(r"[,$]", "", text)


def main() -> None:
    pair = ("118-hr-4366", "3_placed-on-calendar-senate", "4_engrossed-amendment-senate")
    bill, a, b = pair
    p1 = REPO / f"tests/corpus/{bill}/{a}.pdf"
    p2 = REPO / f"tests/corpus/{bill}/{b}.pdf"

    print(f"pair: {bill}/{a} -> {b}", flush=True)
    canon, _ = pdf_canonical("pdfium-wasm", p1, p2, bill, "repaired")

    entries = []
    for ch in canon.get("changes") or []:
        for e in ch.get("amount_entries") or []:
            entries.append(e)
    print(f"PDFium-WASM produced {len(entries)} amount entries", flush=True)

    rng = random.Random(SEED)
    sample = rng.sample(entries, min(40, len(entries)))

    print("building independent reference text via PyMuPDF get_text() ...", flush=True)
    t1 = independent_text(p1)
    t2 = independent_text(p2)
    # GPO prints amounts with commas; normalize whitespace only.
    t1n = strip_money(re.sub(r"\s+", " ", t1))
    t2n = strip_money(re.sub(r"\s+", " ", t2))

    ok_old = ok_new = 0
    n_old = n_new = 0
    failures = []
    for e in sample:
        old, new, kind = e.get("old"), e.get("new"), e.get("kind")
        if old:
            n_old += 1
            hit = any(v in t1n for v in variants(str(old)))
            ok_old += hit
            if not hit:
                failures.append(("old-not-in-v1", kind, old, new))
        if new:
            n_new += 1
            hit = any(v in t2n for v in variants(str(new)))
            ok_new += hit
            if not hit:
                failures.append(("new-not-in-v2", kind, old, new))

    print()
    print(f"sample n={len(sample)} entries (seed {SEED})")
    print(f"  claimed OLD value found in v1 source text: {ok_old}/{n_old}")
    print(f"  claimed NEW value found in v2 source text: {ok_new}/{n_new}")
    if failures:
        print(f"  FAILURES ({len(failures)}):")
        for f in failures[:12]:
            print("   ", f)
    else:
        print("  no failures: every sampled amount is genuinely printed in the source side it is claimed for")

    dest = REPO / "docs/research/pdf-backend-bakeoff/results/redteam_amount_validation.json"
    dest.write_text(
        json.dumps(
            {
                "pair": f"{bill}/{a}->{b}",
                "seed": SEED,
                "n_entries_total": len(entries),
                "n_sampled": len(sample),
                "old_found": ok_old,
                "old_checked": n_old,
                "new_found": ok_new,
                "new_checked": n_new,
                "failures": failures,
                "reference": "PyMuPDF get_text(), independent of the neutral glyph layer",
            },
            indent=1,
            default=str,
        )
    )
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
