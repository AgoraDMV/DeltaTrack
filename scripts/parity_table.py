"""Emit the PDF↔XML change-parity table (#109, slice G of the #54 epic).

A reporting tool, NOT a gate — the same split as ``heading_precision.py``. The gate
is ``tests/test_pipeline_parity.py``, which asserts each bill's per-pipeline totals
stay inside its attributed band. This script recomputes those totals and prints the
human-readable snapshot recorded in
``docs/decisions/0014-leveled-heading-tree-scope.md``.

The table used to be a pytest case (``test_pipeline_change_parity_table``). It
asserted nothing, and it recomputed for all four bills what the parametrized per-bill
test had already computed — one monolithic case that ``pytest-xdist`` distributes
whole, so it was a hard floor on the suite's wall clock (#350). Reporting that
asserts nothing belongs in a script; the bands stay in the test.

This module owns the inputs (``PARITY_BILLS``, ``v1_v2``, ``totals``) and the test
imports them, so the bill list has one home. The test additionally asserts its band
table covers exactly ``PARITY_BILLS``, so the two cannot drift apart.

Exact cross-pipeline parity is not expected; only ``118-hr-8752`` matches. See the
test's module docstring and ADR 0014 for the attributed causes.

Usage:
  .venv/bin/python scripts/parity_table.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from deltatrack.compare.pdf import compare_pdfs  # noqa: E402
from deltatrack.compare.xml import compare_xml  # noqa: E402
from tests.corpus_paths import FIXTURES_DIR  # noqa: E402

# The four evidence bills, v1→v2 (reported→engrossed). Order is the table's order.
# Every one is committed in both formats under tests/corpus/, so this runs on any
# checkout with no fetch.
PARITY_BILLS: tuple[str, ...] = (
    "118-hr-8752",
    "118-hr-8774",
    "117-hr-4502",
    "115-hr-5895",
)


def v1_v2(bill: str) -> tuple[Path, Path]:
    """The first two version PDFs (and their paired XML) for ``bill``.

    Returns ``(v1_pdf, v2_pdf)``; callers derive the XML via ``with_suffix``.
    Fails rather than skipping when a file is missing: all four evidence bills are
    committed in both formats, so an absent one is a broken checkout (#326).
    """
    bill_dir = FIXTURES_DIR / bill
    pdfs = sorted(bill_dir.glob("[0-9]*_*.pdf"))
    assert len(pdfs) >= 2, f"{bill}: committed fixture needs two version PDFs, found {[p.name for p in pdfs]}"
    v1, v2 = pdfs[0], pdfs[1]
    absent = [str(p.with_suffix(".xml")) for p in (v1, v2) if not p.with_suffix(".xml").exists()]
    assert not absent, f"{bill}: committed paired XML absent from checkout: {absent}"
    return v1, v2


def totals(canonical: dict) -> Counter:
    """Per-change_type totals for a canonical diff document."""
    return Counter(c.get("change_type") for c in canonical.get("changes", []))


def parity_row(bill: str) -> tuple[Counter, Counter]:
    """Run both pipelines on ``bill``'s v1→v2 pair; return ``(xml_totals, pdf_totals)``."""
    v1_pdf, v2_pdf = v1_v2(bill)
    xc = compare_xml(v1_pdf.with_suffix(".xml").read_bytes(), v2_pdf.with_suffix(".xml").read_bytes())
    pc = compare_pdfs(v1_pdf.read_bytes(), v2_pdf.read_bytes())
    return totals(xc), totals(pc)


def render(rows: list[tuple[str, Counter, Counter]]) -> str:
    """Format the parity table. Pure, so its shape is testable without the pipelines."""
    out = [
        "\nPDF↔XML change parity (v1→v2, reported→engrossed)",
        f"{'bill':<14}{'pipe':>5}{'modified':>10}{'added':>8}{'removed':>9}{'moved':>7}{'total':>7}",
    ]
    for bill, xn, pn in rows:
        for label, n in (("XML", xn), ("PDF", pn)):
            out.append(
                f"{bill if label == 'XML' else '':<14}{label:>5}"
                f"{n.get('modified', 0):>10}{n.get('added', 0):>8}"
                f"{n.get('removed', 0):>9}{n.get('moved', 0):>7}{sum(n.values()):>7}"
            )
    return "\n".join(out)


def main() -> None:
    rows = [(bill, *parity_row(bill)) for bill in PARITY_BILLS]
    print(render(rows))


if __name__ == "__main__":
    main()
