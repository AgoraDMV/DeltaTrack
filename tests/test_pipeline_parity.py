"""Cross-pipeline change-parity + Senate size-band validation (#109, slice G).

The closing slice of the #54 leveled-heading-tree epic. It adds **no engine
code** — it validates the now-merged A–F output along the two axes slice G owns:

1. **Senate size-band-vs-XML-heading ratio** on the #89 residual pair
   ``118-s-4795`` (reported-in-Senate). ``scripts/heading_precision.py`` is the
   named acceptance tool; we reuse its ``measure`` oracle so the check tracks the
   tool, not a re-implementation. The ratio is PDF ``account`` anchors / XML leaf
   headings — recovery is "in range" when it sits near 1.0.

2. **Change parity** (MODIFIED/ADDED/REMOVED/MOVED totals per pipeline) across
   the four evidence bills, v1→v2 (reported→engrossed).

Exact cross-pipeline parity is **not** the invariant. Only the clean bill
(118-hr-8752, no prose-leading agencies) matches exactly; the others diverge by
design — the count-convergence framing was retired in #107 (the gap is PDF
segmentation granularity + division-collapse, not a bug). So the gate records the
observed per-pipeline totals as **attributed bands** (each carrying its cause),
asserts the totals stay inside them, and pins the clean bill to exact parity. The
bands are guardrail constants: a snug lower bound catches a silent collapse to
zero (``feedback_property_tests_fail_open`` — the fail-open trap), an upper bound
catches a regression. The human-readable snapshot + attribution live in
``docs/decisions/0014-leveled-heading-tree-scope.md``; regenerate with
``pytest -k parity -s``.

``bills/`` is gitignored (fetched via ``fetch_bills.py``) and the Senate PDF is
fetched via ``scripts/fetch_test_assets.py``, so every case skips cleanly on a
clean clone / in CI and gates on a full local run.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from scripts.heading_precision import measure
from server.pdf_compare import compare_pdfs
from server.xml_compare import compare_xml

pytestmark = pytest.mark.slow

ROOT = Path(__file__).parent.parent
BILLS_DIR = ROOT / "bills"

# The canonical-diff change_type vocabulary (formatters/canonical.py). "unchanged"
# is not emitted as a change; the parity totals count only real changes.
_VALID_OPS = {"modified", "added", "removed", "moved"}

# --- Attributed parity bands (the #109 table, as code guardrails) ---------------
# Per evidence bill, v1→v2: the observed (min, max) total-change count each pipeline
# emits, plus the attributed cause of any XML↔PDF gap. Snapshot 2026-06-29. Exact
# parity is NOT expected (see module docstring / #107) — only 118-hr-8752 is exact.
# A total outside its band is either a regression or an engine improvement: trips
# the gate so the number + the ADR snapshot get recalibrated together.
_PARITY: dict[str, tuple[tuple[int, int], tuple[int, int], str]] = {
    # bill:          xml_band,      pdf_band,        attributed cause of the gap
    "118-hr-8752": ((37, 37), (37, 37), "clean: no prose-leading agencies → exact parity"),
    "118-hr-8774": ((30, 33), (31, 36), "PDF over-segments a few blocks (segmentation granularity)"),
    "117-hr-4502": ((1090, 1130), (1430, 1500), "PDF over-segments a large added block"),
    "115-hr-5895": ((240, 255), (310, 335), "division-collapse + segmentation (#107 reframe)"),
}

# Senate #89 residual: size-band ratio is "in range" when account-anchor recovery
# sits near 1.0 against the XML leaf-heading count. Observed 1.02 (2026-06-29).
_SENATE_PDF = ROOT / "test_data" / "BILLS-118s4795rs.pdf"
_SENATE_XML = BILLS_DIR / "118-s-4795" / "1_reported-in-senate.xml"
_SENATE_RATIO_BAND = (0.95, 1.10)


def _v1_v2(bill: str) -> tuple[Path, Path] | None:
    """The first two version PDFs (and their paired XML) for ``bill``, or None.

    Returns ``(v1_pdf, v2_pdf)``; callers derive the XML via ``with_suffix``.
    Skips (returns None) when the bill is unfetched or a paired XML is missing.
    """
    bill_dir = BILLS_DIR / bill
    pdfs = sorted(bill_dir.glob("[0-9]*_*.pdf"))
    if len(pdfs) < 2:
        return None
    v1, v2 = pdfs[0], pdfs[1]
    if not (v1.with_suffix(".xml").exists() and v2.with_suffix(".xml").exists()):
        return None
    return v1, v2


def _totals(canonical: dict) -> Counter:
    """Per-change_type totals for a canonical diff document."""
    return Counter(c.get("change_type") for c in canonical.get("changes", []))


@pytest.mark.parametrize("bill", list(_PARITY))
def test_pipeline_change_parity(bill: str) -> None:
    """Both pipelines emit valid changes; totals sit in their attributed bands."""
    pair = _v1_v2(bill)
    if pair is None:
        pytest.skip(f"{bill} v1/v2 not fetched locally")
    v1_pdf, v2_pdf = pair

    xc = compare_xml(v1_pdf.with_suffix(".xml").read_bytes(), v2_pdf.with_suffix(".xml").read_bytes())
    pc = compare_pdfs(v1_pdf.read_bytes(), v2_pdf.read_bytes())

    xn, pn = _totals(xc), _totals(pc)
    # Genuinely-true invariants (not fail-open): both pipelines emit changes, and
    # every change_type is a real op.
    assert set(xn) <= _VALID_OPS, f"{bill} XML emitted unknown ops: {set(xn) - _VALID_OPS}"
    assert set(pn) <= _VALID_OPS, f"{bill} PDF emitted unknown ops: {set(pn) - _VALID_OPS}"

    xml_total, pdf_total = sum(xn.values()), sum(pn.values())
    (xlo, xhi), (plo, phi), cause = _PARITY[bill]
    assert xlo <= xml_total <= xhi, (
        f"{bill} XML total {xml_total} outside [{xlo},{xhi}] — recalibrate band + ADR 0014 snapshot, "
        f"or investigate regression. Gap cause on record: {cause}"
    )
    assert plo <= pdf_total <= phi, (
        f"{bill} PDF total {pdf_total} outside [{plo},{phi}] — recalibrate band + ADR 0014 snapshot, "
        f"or investigate regression. Gap cause on record: {cause}"
    )


def test_pipeline_change_parity_table(capsys) -> None:
    """Emit the human-readable parity table (`pytest -k parity -s` regenerates it)."""
    rows = []
    for bill in _PARITY:
        pair = _v1_v2(bill)
        if pair is None:
            continue
        v1_pdf, v2_pdf = pair
        xc = compare_xml(v1_pdf.with_suffix(".xml").read_bytes(), v2_pdf.with_suffix(".xml").read_bytes())
        pc = compare_pdfs(v1_pdf.read_bytes(), v2_pdf.read_bytes())
        xn, pn = _totals(xc), _totals(pc)
        rows.append((bill, xn, pn))

    if not rows:
        pytest.skip("no evidence bills fetched locally")

    with capsys.disabled():
        print("\nPDF↔XML change parity (v1→v2, reported→engrossed)")
        hdr = f"{'bill':<14}{'pipe':>5}{'modified':>10}{'added':>8}{'removed':>9}{'moved':>7}{'total':>7}"
        print(hdr)
        for bill, xn, pn in rows:
            for label, n in (("XML", xn), ("PDF", pn)):
                print(
                    f"{bill if label == 'XML' else '':<14}{label:>5}"
                    f"{n.get('modified', 0):>10}{n.get('added', 0):>8}"
                    f"{n.get('removed', 0):>9}{n.get('moved', 0):>7}{sum(n.values()):>7}"
                )


def test_senate_size_band_ratio() -> None:
    """118-s-4795 (#89 residual): PDF size-band recovery ratio is in range."""
    if not _SENATE_PDF.exists():
        pytest.skip("118-s-4795 PDF not fetched (scripts/fetch_test_assets.py)")
    if not _SENATE_XML.exists():
        pytest.skip("118-s-4795 XML not present")

    m = measure(_SENATE_PDF, _SENATE_XML)
    ratio = m["count_ratio"]
    lo, hi = _SENATE_RATIO_BAND
    assert ratio is not None and lo <= ratio <= hi, (
        f"118-s-4795 size-band ratio {ratio} outside [{lo},{hi}] — the #89 residual "
        f"recovery regressed or the band needs recalibration + ADR 0014 update"
    )
